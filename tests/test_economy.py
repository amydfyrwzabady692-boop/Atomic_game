from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings

from core.models import TelegramUser
from games.engine import services
from games.engine.payout import Standing
from leaderboard.progress import level_for_xp, xp_for_level
from wallet import economy
from wallet.management.commands.audit_wallets import find_mismatches
from wallet.models import CoinTransaction, TxType

pytestmark = pytest.mark.django_db
TEHRAN = ZoneInfo("Asia/Tehran")


def at(day, hour=12):
    return datetime(2026, 3, day, hour, 0, tzinfo=TEHRAN)


def test_signup_bonus_only_once(make_user):
    user = make_user()
    economy.grant_signup_bonus(user)
    economy.grant_signup_bonus(user)
    user.refresh_from_db()
    assert user.coins == settings.SIGNUP_BONUS


def test_daily_streak_grows_and_caps(make_user):
    user = make_user()
    first = economy.claim_daily(user, at(1))
    assert (first.claimed, first.amount, first.streak) == (True, 200, 1)
    second = economy.claim_daily(user, at(2))
    assert (second.amount, second.streak) == (250, 2)
    for day in range(3, 20):
        last = economy.claim_daily(user, at(day))
    assert last.amount == settings.DAILY_MAX
    assert find_mismatches() == []


def test_daily_cannot_be_claimed_twice_same_day(make_user):
    user = make_user()
    economy.claim_daily(user, at(1, 1))
    again = economy.claim_daily(user, at(1, 23))
    assert again.claimed is False and again.amount == 0
    user.refresh_from_db()
    assert user.coins == 200


def test_daily_streak_resets_after_missed_day(make_user):
    user = make_user()
    economy.claim_daily(user, at(1))
    economy.claim_daily(user, at(2))
    result = economy.claim_daily(user, at(4))
    assert (result.streak, result.amount) == (1, 200)


def test_day_boundary_uses_tehran_time(make_user):
    user = make_user()
    economy.claim_daily(user, at(1, 23))
    result = economy.claim_daily(user, at(2, 0) + timedelta(minutes=5))
    assert result.claimed and result.streak == 2


def test_rescue_only_when_broke_and_once_a_day(make_user):
    rich = make_user(coins=5)
    assert economy.claim_rescue(rich, at(1)) == 0
    broke = make_user()
    assert economy.claim_rescue(broke, at(1)) == settings.RESCUE_AMOUNT
    TelegramUser.objects.filter(pk=broke.pk).update(coins=0)
    assert economy.claim_rescue(broke, at(1, 20)) == 0
    assert economy.claim_rescue(broke, at(2)) == settings.RESCUE_AMOUNT


def test_daily_gives_rescue_when_already_claimed_and_broke(make_user):
    user = make_user()
    economy.claim_daily(user, at(1))
    from wallet.services import apply_transaction

    apply_transaction(user, -200, TxType.ENTRY_FEE, "spend-all")
    result = economy.claim_daily(user, at(1, 15))
    assert result.claimed is False and result.rescue == settings.RESCUE_AMOUNT
    assert find_mismatches() == []


def _play_one_match(group, users):
    match = services.create_match(
        group, users[0], "quick_math", entry_fee=0, prize_split=[100], join_seconds=60, min_players=2, max_players=5
    )
    for u in users:
        services.join_match(match.pk, u)
    services.start_match(match.pk)
    return services.finish_match(match.pk, [Standing(users[0].pk, 1, 1.0)])


def test_referral_paid_after_first_game_and_account_age(group, make_user):
    referrer = make_user()
    invitee = make_user(referred_by=referrer)
    other = make_user()
    # حساب تازه است: هنوز جایزه‌ای نیست
    result = _play_one_match(group, [invitee, other])
    assert result.referral_rewards == []
    assert not CoinTransaction.objects.filter(type=TxType.REFERRAL).exists()

    old = invitee.created_at - timedelta(hours=settings.REFERRAL_MIN_ACCOUNT_AGE_HOURS + 1)
    TelegramUser.objects.filter(pk=invitee.pk).update(created_at=old)
    result = _play_one_match(group, [invitee, other])
    assert [(a.pk, b.pk) for a, b in result.referral_rewards] == [(referrer.pk, invitee.pk)]
    referrer.refresh_from_db()
    assert referrer.coins == settings.REFERRAL_REWARD
    # فقط یک بار
    _play_one_match(group, [invitee, other])
    assert CoinTransaction.objects.filter(type=TxType.REFERRAL).count() == 1


def test_referral_not_paid_before_any_game(make_user):
    referrer = make_user()
    invitee = make_user(referred_by=referrer)
    old = invitee.created_at - timedelta(days=3)
    TelegramUser.objects.filter(pk=invitee.pk).update(created_at=old)
    assert economy.try_reward_referral(invitee) is None


def test_level_formula_is_progressive():
    assert [xp_for_level(n) for n in range(1, 6)] == [0, 100, 300, 600, 1000]
    assert level_for_xp(0) == 1
    assert level_for_xp(99) == 1
    assert level_for_xp(100) == 2
    assert level_for_xp(299) == 2
    assert level_for_xp(1000) == 5
