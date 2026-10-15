"""مسابقه‌ی آرکید در لایه‌ی ربات: لابی ← پنجره‌ی بازی ← جدول زنده ← پرداخت."""

import random
from datetime import timedelta

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone

from arcade import services as arcade_services
from arcade.models import ArcadeSession
from arcade.sim import get_simulator
from arcade.sim.autoplay import autoplay
from bot.runner import MatchManager
from core.models import TelegramGroup, TelegramUser
from core.redis import reset_clients
from games.catalog import catalog, get_info
from games.engine import services
from games.models import Match, MatchStatus
from leaderboard.models import UserAchievement
from wallet.management.commands.audit_wallets import find_mismatches
from wallet.models import TxType
from wallet.services import apply_transaction

from .fake_telegram import FakeApplication

pytestmark = pytest.mark.django_db(transaction=True)
CHAT_ID = -100999


@pytest.fixture(autouse=True)
def _fresh_redis():
    reset_clients()
    yield
    reset_clients()


@sync_to_async
def setup_world(n_users=3):
    group = TelegramGroup.objects.create(chat_id=CHAT_ID, title="آرکید")
    users = []
    for i in range(n_users):
        user = TelegramUser.objects.create(tg_id=7000 + i, first_name=f"گیمر{i}", started_bot=True)
        apply_transaction(user, 1000, TxType.ADMIN_GRANT, f"seed:{user.pk}")
        users.append(user)
    return group, users


@sync_to_async
def play_attempt(user, token, max_ms):
    """یک تلاش کامل: صدور session، بازی خودکار و ثبت (با عقب بردن زمان شروع به‌جای صبر واقعی)."""
    session, _ = arcade_services.start_session(user, None, token)
    sim = get_simulator(session.game_key)
    inputs, duration = autoplay(sim, session.seed, sim.demo_policy(random.Random(3), 100), max_ms)
    ArcadeSession.objects.filter(pk=session.pk).update(
        started_at=timezone.now() - timedelta(milliseconds=duration + 500)
    )
    return arcade_services.submit_session(user, str(session.pk), inputs, duration).verified_score


@sync_to_async
def coins_of(users):
    return [TelegramUser.objects.get(pk=u.pk).coins for u in users]


@sync_to_async
def match_row(match_id):
    return Match.objects.get(pk=match_id)


async def open_arcade(manager, group, users, attempts=3, fee=100):
    active = await manager.create_lobby(
        group,
        users[0],
        get_info("arcade_pins"),
        fee=fee,
        split=[60, 30, 10],
        join_seconds=60,
        options={"window_minutes": 3, "attempts": attempts},
    )
    for user in users:
        await manager.join(active, user)
    return active


def test_all_fourteen_arcade_games_in_catalog_with_categories():
    games = {k: g for k, g in catalog().items() if g.is_arcade}
    assert len(games) == 14
    assert {g.category for g in games.values()} == {"speed", "skill", "stage"}
    for info in games.values():
        assert info.title_fa and info.description_fa and info.suggested_minutes in (3, 5, 10)
    assert games["arcade_tiles"].variants.keys() == {"endless", "fifty"}


async def test_arcade_match_window_live_board_and_payout():
    group, users = await setup_world()
    app = FakeApplication()
    manager = MatchManager(app)
    active = await open_arcade(manager, group, users)
    await app.job_queue.fire("lobby_close")

    match = await match_row(active.match_id)
    assert match.status == MatchStatus.RUNNING
    remaining = (match.play_deadline - timezone.now()).total_seconds()
    assert 170 < remaining <= 180
    board = app.bot.sent[-1]
    assert "مسابقه در جریان است" in board["text"]
    url = board["reply_markup"].inline_keyboard[0][0].url
    # در گروه دکمه‌ی web_app کار نمی‌کند؛ لینک مستقیم مینی‌اپ با توکن مسابقه
    assert url == f"https://t.me/test_bot/arcade?startapp={match.token}"
    assert app.job_queue.pending("arcade_end") and app.job_queue.pending("arcade_poll")

    low = await play_attempt(users[1], match.token, 3000)
    await app.job_queue.fire("arcade_poll")
    high = await play_attempt(users[0], match.token, 9000)
    assert high > low > 0
    await app.job_queue.fire("arcade_poll")
    assert active.leader == (users[0].pk, high)
    assert "رکورد زد" in active.flash

    await app.job_queue.fire("arcade_end")
    assert active.phase == "done" and CHAT_ID not in manager.active
    assert (await match_row(active.match_id)).status == MatchStatus.FINISHED
    result = app.bot.sent[-1]["text"]
    assert "پایان سیخ‌زن" in result and "گیمر0" in result
    # ۳۰۰ سکه بین دو نفری که امتیاز گرفتند به نسبت ۶۰:۳۰ = ۲۰۰ / ۱۰۰؛ نفر سوم بازی نکرد و سهمی ندارد
    # نفر اول دستاوردهای «اولین بازی»، «اولین برد» و «آرکیدباز» را هم می‌گیرد
    assert await coins_of(users) == [900 + 200 + 50 + 100 + 150, 900 + 100 + 50, 900 + 50]
    assert await sync_to_async(
        UserAchievement.objects.filter(user=users[0], achievement__code="arcade_first").exists
    )()
    assert await sync_to_async(find_mismatches)() == []
    assert not app.job_queue.pending("arcade_poll")


async def test_arcade_match_ends_early_when_all_attempts_used():
    group, users = await setup_world(n_users=2)
    app = FakeApplication()
    manager = MatchManager(app)
    active = await open_arcade(manager, group, users, attempts=1)
    await app.job_queue.fire("lobby_close")
    match = await match_row(active.match_id)
    await play_attempt(users[0], match.token, 4000)
    await app.job_queue.fire("arcade_poll")
    assert active.phase == "running"
    await play_attempt(users[1], match.token, 2000)
    await app.job_queue.fire("arcade_poll")
    assert active.phase == "done"
    assert (await match_row(active.match_id)).status == MatchStatus.FINISHED


async def test_arcade_match_nobody_played_returns_stakes():
    group, users = await setup_world(n_users=2)
    app = FakeApplication()
    manager = MatchManager(app)
    await open_arcade(manager, group, users)
    await app.job_queue.fire("lobby_close")
    await app.job_queue.fire("arcade_end")
    # همه صفر = مساوی کامل ⇒ pot مساوی تقسیم می‌شود (۶۶+۳۳ هر نفر و باقیمانده به نفر اول).
    # چون کسی امتیازی نگرفته «برد» حساب نمی‌شود و فقط دستاورد «اولین بازی» داده می‌شود.
    assert await coins_of(users) == [900 + 101 + 50, 900 + 99 + 50]

    @sync_to_async
    def wins():
        return list(TelegramUser.objects.order_by("pk").values_list("wins", "games_played"))

    assert await wins() == [(0, 1), (0, 1)]
    assert await sync_to_async(find_mismatches)() == []


async def test_running_arcade_match_survives_restart():
    group, users = await setup_world(n_users=2)

    @sync_to_async
    def prepare():
        match = services.create_match(
            group,
            users[0],
            "arcade_pins",
            entry_fee=100,
            prize_split=[100],
            join_seconds=60,
            min_players=2,
            max_players=10,
            options={"window_minutes": 3, "attempts": 3},
        )
        for user in users:
            services.join_match(match.pk, user)
        return services.start_match(match.pk, 180)

    match = await prepare()
    score = await play_attempt(users[1], match.token, 5000)

    app = FakeApplication()
    manager = MatchManager(app)
    await manager.recover()
    active = manager.active[CHAT_ID]
    assert active.phase == "running" and active.info.is_arcade
    assert app.job_queue.pending("arcade_end")
    # امتیاز ثبت‌شده‌ی قبل از ری‌استارت حفظ شده و مسابقه عادی تمام می‌شود
    await app.job_queue.fire("arcade_end")
    assert (await match_row(match.pk)).status == MatchStatus.FINISHED
    assert score > 0
    coins = await coins_of(users)
    assert coins[1] > coins[0]
    assert await sync_to_async(find_mismatches)() == []


async def test_expired_arcade_match_is_settled_on_recover():
    group, users = await setup_world(n_users=2)

    @sync_to_async
    def prepare():
        match = services.create_match(
            group, users[0], "arcade_pins", entry_fee=50, prize_split=[100], join_seconds=60, min_players=2, max_players=5
        )
        for user in users:
            services.join_match(match.pk, user)
        services.start_match(match.pk, 180)
        Match.objects.filter(pk=match.pk).update(play_deadline=timezone.now() - timedelta(seconds=5))
        return match

    match = await prepare()
    manager = MatchManager(FakeApplication())
    await manager.recover()
    assert (await match_row(match.pk)).status == MatchStatus.FINISHED
    assert CHAT_ID not in manager.active
