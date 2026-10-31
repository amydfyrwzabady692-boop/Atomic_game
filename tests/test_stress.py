"""فشار هم‌زمان روی پول و مسابقه‌ها در یک گروه (PostgreSQL واقعی، چند thread و async):

- چند لابی هم‌زمان در یک گروه؛ هر کاربر هم‌زمان در چند لابی شرکت می‌کند و در همان حال سکه منتقل می‌کند و
  درخواست فروش می‌دهد؛ مدیرها هم‌زمان روی همان رسیدها و درخواست‌های فروش تصمیم می‌گیرند؛ بعد همه‌ی مسابقه‌ها
  هم‌زمان (و دوبار) تمام یا لغو می‌شوند.
- چند نفر با هم «شرکت» را روی همان لابی در ربات می‌زنند.

بعد از همه: هیچ موجودی منفی نیست، ظرفیت لابی‌ها رعایت شده و حسابرسی کامل (ledger، مسابقه‌ها، رسیدها) تمیز است.
"""

import random
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from asgiref.sync import sync_to_async
from django.db import connections

from core.models import TelegramGroup, TelegramUser
from games.engine import services
from games.engine.payout import Standing
from games.engine.services import MatchError
from games.models import Match, MatchStatus
from wallet import services as wallet
from wallet.management.commands.audit_wallets import full_audit
from wallet.models import CoinTransaction, SellRequest, TopUpRequest, TxType
from wallet.services import InsufficientFunds, WalletError

from .conftest import requires_postgres

EXPECTED = (MatchError, InsufficientFunds, WalletError)


def in_threads(jobs, workers=12):
    """هر کار در thread خودش؛ خطاهای پیش‌بینی‌شده (کم بودن سکه، پر بودن لابی) جمع می‌شوند."""
    errors = []
    lock = threading.Lock()

    def run(job):
        try:
            job()
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(run, jobs))
    return errors


def assert_clean():
    report = full_audit()
    assert report["wallets"] == [] and report["matches"] == [] and report["requests"] == [], report
    assert not TelegramUser.objects.filter(coins__lt=0).exists()


@requires_postgres
@pytest.mark.django_db(transaction=True)
def test_many_lobbies_in_one_group_with_money_moving_at_the_same_time(group, make_user):
    rng = random.Random(20261031)
    users = [make_user(coins=rng.choice([0, 30, 120, 400, 900])) for _ in range(24)]
    matches = [
        services.create_match(
            group, users[i], "quick_math", entry_fee=rng.choice([0, 20, 50]), prize_split=rng.choice([[100], [60, 40], [50, 30, 20]]),
            join_seconds=600, min_players=2, max_players=rng.choice([3, 6, 12]),
        )  # fmt: skip
        for i in range(8)
    ]
    # از قبل: رسیدهای شارژ و درخواست‌های فروش برای تصمیم هم‌زمان مدیرها
    topups = [wallet.create_topup_request(u, rng.choice([50, 200]), f"photo-{u.pk}") for u in users[:6]]
    sells = [wallet.create_sell_request(u, 100, "6037991234567893", "دارنده") for u in users if u.coins >= 400][:4]

    jobs = []
    for user in users:
        for match in rng.sample(matches, 3):
            jobs.append(lambda m=match.pk, u=user.pk: services.join_match(m, TelegramUser.objects.get(pk=u)))
            jobs.append(lambda m=match.pk, u=user.pk: services.join_match(m, TelegramUser.objects.get(pk=u)))  # دوبار زدن
    for i in range(40):
        a, b = rng.sample(users, 2)
        amount, key = rng.choice([5, 25, 80]), f"stress:t:{i}"
        jobs.append(lambda a=a.pk, b=b.pk, amount=amount, key=key: wallet.transfer_coins(
            TelegramUser.objects.get(pk=a), TelegramUser.objects.get(pk=b), amount, key))  # fmt: skip
        if i % 4 == 0:  # همان انتقال دوباره (دوبار زدن دکمه‌ی تأیید)
            jobs.append(lambda a=a.pk, b=b.pk, amount=amount, key=key: wallet.transfer_coins(
                TelegramUser.objects.get(pk=a), TelegramUser.objects.get(pk=b), amount, key))  # fmt: skip
    for user in rng.sample(users, 6):
        jobs.append(lambda u=user.pk: wallet.create_sell_request(TelegramUser.objects.get(pk=u), 100, "6037991234567893", "دارنده"))
    for req in topups:  # سه مدیر هم‌زمان روی همان رسید
        jobs += [lambda r=req.pk: wallet.approve_topup(r, 1), lambda r=req.pk: wallet.approve_topup(r, 2), lambda r=req.pk: wallet.reject_topup(r, 3)]
    for req in sells:  # «واریز شد» و «رد» هم‌زمان
        jobs += [lambda r=req.pk: wallet.mark_sell_paid(r, 1), lambda r=req.pk: wallet.reject_sell(r, 2), lambda r=req.pk: wallet.reject_sell(r, 3)]
    rng.shuffle(jobs)
    unexpected = [e for e in in_threads(jobs) if not isinstance(e, EXPECTED)]
    assert unexpected == [], unexpected

    for match in matches:
        match.refresh_from_db()
        joined = match.players.count()
        assert joined <= match.max_players and match.pot == match.entry_fee * joined
        assert match.players.values("user").distinct().count() == joined  # هیچ‌کس دو بار
    for req in topups:
        req.refresh_from_db()
        credited = CoinTransaction.objects.filter(idempotency_key=f"topup:{req.pk}").count()
        assert req.status != TopUpRequest.Status.PENDING and credited == (1 if req.status == TopUpRequest.Status.APPROVED else 0)
    for req in sells:
        req.refresh_from_db()
        refunds = CoinTransaction.objects.filter(idempotency_key=f"sell_refund:{req.pk}").count()
        assert req.status != SellRequest.Status.PENDING and refunds == (1 if req.status == SellRequest.Status.REJECTED else 0)
    assert_clean()

    # همه‌ی مسابقه‌ها هم‌زمان (و هر کدام دو بار) تمام یا لغو می‌شوند
    def settle(match_id):
        match = Match.objects.get(pk=match_id)
        if match.status != MatchStatus.LOBBY:
            return
        try:
            services.start_match(match_id)
        except MatchError:
            services.cancel_match(match_id, "manual")
            return
        local = random.Random(match_id)
        players = list(match.players.values_list("user_id", flat=True))
        services.finish_match(match_id, [Standing(uid, local.randint(0, 3), float(i)) for i, uid in enumerate(players)])

    finals = [lambda m=m.pk: settle(m) for m in matches] * 2
    unexpected = [e for e in in_threads(finals) if not isinstance(e, EXPECTED)]
    assert unexpected == [], unexpected
    assert not Match.objects.filter(status__in=[MatchStatus.LOBBY, MatchStatus.RUNNING]).exists()
    for match in Match.objects.filter(status=MatchStatus.FINISHED):
        prizes = CoinTransaction.objects.filter(ref_match=match, type=TxType.PRIZE)
        assert sum(t.amount for t in prizes) == match.pot
    assert_clean()


# ====================================================================== «شرکت» هم‌زمان در ربات
@pytest.fixture
def bot_app():
    from bot.runner import MatchManager

    from .fake_telegram import FakeApplication

    application = FakeApplication()
    application.bot_data["manager"] = MatchManager(application)
    return application


@requires_postgres
@pytest.mark.django_db(transaction=True)
async def test_many_players_press_join_on_the_same_lobby_at_once(bot_app, monkeypatch):
    import asyncio

    from bot.handlers import group
    from core.redis import reset_clients
    from games.catalog import get_info

    from .test_handlers import GROUP_ID, make_callback

    reset_clients()

    async def always(*args, **kwargs):
        return True

    monkeypatch.setattr("bot.ratelimit.allow", always)
    chat = await sync_to_async(TelegramGroup.objects.create)(chat_id=GROUP_ID, title="گروه")
    users = []
    for i in range(16):
        user = await sync_to_async(TelegramUser.objects.create)(tg_id=9100 + i, first_name=f"نفر{i}", started_bot=True)
        if i != 15:  # آخری سکه ندارد
            await sync_to_async(wallet.apply_transaction)(user, 100, TxType.ADMIN_GRANT, f"seed:{user.pk}")
        users.append(user)
    manager = bot_app.bot_data["manager"]
    active = await manager.create_lobby(chat, users[0], get_info("quick_math"), fee=40, split=[100], join_seconds=120, options={})
    match = await sync_to_async(Match.objects.get)(pk=active.match_id)
    await sync_to_async(Match.objects.filter(pk=match.pk).update)(max_players=10)

    async def press(user):
        update, context = make_callback(bot_app, user.tg_id, f"j:{match.pk}", 1)
        await group.join_callback(update, context)
        return update.answers

    answers = await asyncio.gather(*(press(u) for u in users + users[:5]))  # چند نفر دو بار هم می‌زنند
    assert all(a for a in answers)  # به هر کلیک جواب داده شد
    match = await sync_to_async(Match.objects.get)(pk=match.pk)
    players = await sync_to_async(lambda: list(match.players.values_list("user__tg_id", flat=True)))()
    assert len(players) == 10 and len(set(players)) == 10 and match.pot == 400
    assert 9115 not in players  # بی‌سکه نتوانست
    await sync_to_async(assert_clean)()
    await manager.cancel(active, "admin")
    await sync_to_async(assert_clean)()
    reset_clients()
