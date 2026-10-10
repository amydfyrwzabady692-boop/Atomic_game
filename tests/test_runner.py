"""تست سرتاسری چرخه‌ی مسابقه در لایه‌ی ربات با تلگرام ساختگی و بازی «حساب سریع»."""

from datetime import timedelta

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone

from bot.runner import MatchManager
from core.models import TelegramGroup, TelegramUser
from core.redis import reset_clients
from games.catalog import get_info
from games.engine import services
from games.engine.services import MatchError
from games.models import Match, MatchStatus
from wallet.management.commands.audit_wallets import find_mismatches
from wallet.models import CoinTransaction, TxType
from wallet.services import apply_transaction

from .fake_telegram import FakeApplication

pytestmark = pytest.mark.django_db(transaction=True)

CHAT_ID = -100777


@pytest.fixture(autouse=True)
def _fresh_redis():
    reset_clients()
    yield
    reset_clients()


@sync_to_async
def setup_world(n_users=3, coins=1000):
    group = TelegramGroup.objects.create(chat_id=CHAT_ID, title="تست")
    users = []
    for i in range(n_users):
        user = TelegramUser.objects.create(tg_id=5000 + i, first_name=f"بازیکن{i}", started_bot=True)
        if coins:
            apply_transaction(user, coins, TxType.ADMIN_GRANT, f"seed:{user.pk}")
        users.append(user)
    return group, users


@sync_to_async
def coins_of(users):
    return [TelegramUser.objects.get(pk=u.pk).coins for u in users]


@sync_to_async
def match_status(match_id):
    return Match.objects.get(pk=match_id).status


async def open_lobby(manager, group, creator, fee=100, split=(60, 30, 10), rounds=2):
    return await manager.create_lobby(
        group,
        creator,
        get_info("quick_math"),
        fee=fee,
        split=list(split),
        join_seconds=60,
        options={"rounds": rounds},
    )


async def test_full_match_lifecycle_pays_winner():
    group, users = await setup_world()
    app = FakeApplication()
    manager = MatchManager(app)
    active = await open_lobby(manager, group, users[0])
    assert "حساب سریع" in app.bot.sent[0]["text"]
    for user in users:
        assert await manager.join(active, user)
    assert await coins_of(users) == [900, 900, 900]

    await app.job_queue.fire("lobby_close")
    assert active.phase == "running"
    assert await match_status(active.match_id) == MatchStatus.RUNNING
    assert "راند ۱ از ۲" in app.bot.sent[-1]["text"]

    # بازیکن ۰ هر دو راند را می‌برد
    for _ in range(2):
        answer = str(active.game.answer)
        await manager.on_message(active, active.players_by_tg[5000], answer, 1, timezone.now().timestamp())
        await app.job_queue.fire("game:gap")

    assert active.phase == "done"
    assert CHAT_ID not in manager.active
    assert await match_status(active.match_id) == MatchStatus.FINISHED
    result_text = app.bot.sent[-1]["text"]
    assert "پایان حساب سریع" in result_text and "🥇" in result_text
    # نفر اول ۶۰٪ از ۳۰۰ + دستاوردهای اولین بازی/برد؛ دو نفر دیگر مساوی (۳۰+۱۰)/۲
    assert await coins_of(users) == [900 + 180 + 150, 900 + 60 + 50, 900 + 60 + 50]
    assert await sync_to_async(find_mismatches)() == []
    assert not app.job_queue.pending(f"m{active.match_id}:game:round")


async def test_lobby_without_enough_players_is_cancelled_and_refunded():
    group, users = await setup_world()
    app = FakeApplication()
    manager = MatchManager(app)
    active = await open_lobby(manager, group, users[0])
    await manager.join(active, users[0])
    assert await coins_of(users) == [900, 1000, 1000]
    await app.job_queue.fire("lobby_close")
    assert await match_status(active.match_id) == MatchStatus.CANCELLED
    assert await coins_of(users) == [1000, 1000, 1000]
    assert "بازیکن کافی نیومد" in app.bot.all_text(CHAT_ID)
    assert CHAT_ID not in manager.active
    assert await sync_to_async(find_mismatches)() == []


async def test_only_one_active_match_per_group():
    group, users = await setup_world()
    manager = MatchManager(FakeApplication())
    await open_lobby(manager, group, users[0])
    with pytest.raises(MatchError) as err:
        await open_lobby(manager, group, users[1])
    assert err.value.code == "active_match_exists"


async def test_join_errors_surface_as_match_errors():
    group, users = await setup_world(coins=0)
    manager = MatchManager(FakeApplication())
    active = await open_lobby(manager, group, users[0])
    with pytest.raises(MatchError) as err:
        await manager.join(active, users[0])
    assert err.value.code == "not_enough_coins"


async def test_manual_cancel_while_running_refunds():
    group, users = await setup_world()
    app = FakeApplication()
    manager = MatchManager(app)
    active = await open_lobby(manager, group, users[0])
    for user in users:
        await manager.join(active, user)
    await app.job_queue.fire("lobby_close")
    await manager.cancel(active, "manual")
    assert await coins_of(users) == [1000, 1000, 1000]
    assert await match_status(active.match_id) == MatchStatus.CANCELLED
    assert not app.job_queue.pending("game:round")
    # پیام‌های بعد از لغو نادیده گرفته می‌شوند
    await manager.on_message(active, active.players_by_tg[5000], "1", 1, 0.0)
    assert await sync_to_async(find_mismatches)() == []


async def test_game_crash_cancels_and_refunds():
    group, users = await setup_world()
    app = FakeApplication()
    manager = MatchManager(app)
    active = await open_lobby(manager, group, users[0])
    for user in users:
        await manager.join(active, user)
    await app.job_queue.fire("lobby_close")

    async def boom(msg):
        raise RuntimeError("bug in plugin")

    active.game.on_message = boom
    await manager.on_message(active, active.players_by_tg[5000], "x", 1, 0.0)
    assert await match_status(active.match_id) == MatchStatus.CANCELLED
    assert await coins_of(users) == [1000, 1000, 1000]
    assert "خطای فنی" in app.bot.sent[-1]["text"]


async def test_lobby_full_starts_early():
    group, users = await setup_world(n_users=2)
    app = FakeApplication()
    manager = MatchManager(app)
    active = await open_lobby(manager, group, users[0])
    await sync_to_async(Match.objects.filter(pk=active.match_id).update)(max_players=2)
    await manager.join(active, users[0])
    await manager.join(active, users[1])
    # با پر شدن ظرفیت، بستن لابی جلو می‌افتد
    await app.job_queue.fire("lobby_close")
    assert active.phase == "running"


async def test_recover_resumes_lobby_and_refunds_running_text_game():
    group, users = await setup_world()

    @sync_to_async
    def prepare():
        other = TelegramGroup.objects.create(chat_id=-100888, title="دوم")
        lobby = services.create_match(
            group, users[0], "quick_math", entry_fee=100, prize_split=[100], join_seconds=60, min_players=2, max_players=5
        )
        services.join_match(lobby.pk, users[0])
        running = services.create_match(
            other, users[1], "quick_math", entry_fee=200, prize_split=[100], join_seconds=60, min_players=2, max_players=5
        )
        services.join_match(running.pk, users[1])
        services.join_match(running.pk, users[2])
        services.start_match(running.pk)
        return lobby, running

    lobby, running = await prepare()
    assert await coins_of(users) == [900, 800, 800]

    app = FakeApplication()
    manager = MatchManager(app)
    await manager.recover()

    # لابی ادامه پیدا می‌کند و تایمرش دوباره مسلح شده
    assert manager.active[CHAT_ID].match_id == lobby.pk
    assert app.job_queue.pending(f"m{lobby.pk}:lobby_close")
    # بازی متنیِ نیمه‌کاره لغو و ورودی‌ها برگشته
    assert await match_status(running.pk) == MatchStatus.CANCELLED
    assert await coins_of(users) == [900, 1000, 1000]
    assert "ری‌استارت" in app.bot.all_text(-100888)
    assert await sync_to_async(find_mismatches)() == []


async def test_recover_closes_expired_lobby():
    group, users = await setup_world()

    @sync_to_async
    def prepare():
        match = services.create_match(
            group, users[0], "quick_math", entry_fee=100, prize_split=[100], join_seconds=60, min_players=2, max_players=5
        )
        services.join_match(match.pk, users[0])
        Match.objects.filter(pk=match.pk).update(join_deadline=timezone.now() - timedelta(seconds=30))
        return match

    match = await prepare()
    manager = MatchManager(FakeApplication())
    await manager.recover()
    assert await match_status(match.pk) == MatchStatus.CANCELLED
    assert await coins_of(users) == [1000, 1000, 1000]
    assert CHAT_ID not in manager.active
    assert await sync_to_async(CoinTransaction.objects.filter(type=TxType.REFUND).count)() == 1


async def test_watchdog_stops_lobby_cancelled_from_admin_panel():
    group, users = await setup_world()
    app = FakeApplication()
    manager = MatchManager(app)
    active = await open_lobby(manager, group, users[0])
    await manager.join(active, users[0])
    await manager.join(active, users[1])
    # اکشن «لغو مسابقه و برگشت ورودی‌ها» در پنل ادمین، بیرون از پروسه‌ی ربات اجرا می‌شود
    await sync_to_async(services.cancel_match)(active.match_id, "admin")
    assert await coins_of(users) == [1000, 1000, 1000]

    await app.job_queue.fire("watchdog")
    assert active.phase == "done" and CHAT_ID not in manager.active
    assert not app.job_queue.pending("lobby_close")
    text = app.bot.all_text(CHAT_ID)
    assert "توسط مدیریت لغو شد" in text and "برگشت" in text
    # دوباره چیزی برنمی‌گردد
    assert await sync_to_async(CoinTransaction.objects.filter(type=TxType.REFUND).count)() == 2
