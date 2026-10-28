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


@pytest.fixture
def daily_on(economy_settings, monkeypatch):
    """جایزه‌ی روزانه روشن و گردونه قطعی (همیشه ۲ سکه) تا عددها قابل بررسی باشند."""
    economy_settings(daily_enabled=True)
    monkeypatch.setattr(economy, "roll_daily_reward", lambda: 2)


def at(day, hour=12):
    return datetime(2026, 3, day, hour, 0, tzinfo=TEHRAN)


def test_signup_bonus_is_off_by_default(make_user):
    user = make_user()
    assert economy.grant_signup_bonus(user) is None
    user.refresh_from_db()
    assert user.coins == 0 and not CoinTransaction.objects.filter(type=TxType.SIGNUP_BONUS).exists()


def test_signup_bonus_from_admin_settings_only_once(make_user, economy_settings):
    economy_settings(signup_bonus=50)
    user = make_user()
    economy.grant_signup_bonus(user)
    economy.grant_signup_bonus(user)
    user.refresh_from_db()
    assert user.coins == 50


def test_daily_is_on_by_default_and_can_be_turned_off(make_user, economy_settings):
    user = make_user()
    assert economy.get_settings().daily_enabled is True
    economy_settings(daily_enabled=False)
    result = economy.claim_daily(user, at(1))
    assert result.disabled and not result.claimed
    assert economy.claim_rescue(user, at(1)) == 0
    user.refresh_from_db()
    assert user.coins == 0


def test_daily_wheel_only_pays_the_advertised_amounts():
    """گردونه: ۶۹٪ پوچ، ۲۰٪ یک، ۱۰٪ دو و ۱٪ ده سکه."""
    import random

    random.seed(7)
    rolls = [economy.roll_daily_reward() for _ in range(20_000)]
    assert set(rolls) <= {0, 1, 2, 10}
    share = {value: rolls.count(value) / len(rolls) for value in (0, 1, 2, 10)}
    assert 0.66 < share[0] < 0.72 and 0.18 < share[1] < 0.22 and 0.08 < share[2] < 0.12 and share[10] < 0.02


def test_daily_streak_grows(make_user, daily_on):
    user = make_user()
    first = economy.claim_daily(user, at(1))
    assert (first.claimed, first.amount, first.streak) == (True, 2, 1)
    second = economy.claim_daily(user, at(2))
    assert (second.amount, second.streak) == (2, 2)
    user.refresh_from_db()
    assert user.coins == 4 and user.daily_streak == 2
    assert find_mismatches() == []


def test_empty_wheel_still_counts_the_day(make_user, daily_on, monkeypatch):
    monkeypatch.setattr(economy, "roll_daily_reward", lambda: 0)
    user = make_user()
    result = economy.claim_daily(user, at(1))
    assert (result.claimed, result.amount, result.streak) == (True, 0, 1)
    assert not CoinTransaction.objects.filter(type=TxType.DAILY).exists()
    assert economy.claim_daily(user, at(1, 20)).claimed is False


def test_daily_cannot_be_claimed_twice_same_day(make_user, daily_on):
    user = make_user()
    economy.claim_daily(user, at(1, 1))
    again = economy.claim_daily(user, at(1, 23))
    assert again.claimed is False and again.amount == 0
    user.refresh_from_db()
    assert user.coins == 2


def test_daily_streak_resets_after_missed_day(make_user, daily_on):
    user = make_user()
    economy.claim_daily(user, at(1))
    economy.claim_daily(user, at(2))
    result = economy.claim_daily(user, at(4))
    assert (result.streak, result.amount) == (1, 2)


def test_day_boundary_uses_tehran_time(make_user, daily_on):
    user = make_user()
    economy.claim_daily(user, at(1, 23))
    result = economy.claim_daily(user, at(2, 0) + timedelta(minutes=5))
    assert result.claimed and result.streak == 2


def test_rescue_only_when_broke_and_once_a_day(make_user, daily_on):
    rich = make_user(coins=5)
    assert economy.claim_rescue(rich, at(1)) == 0
    broke = make_user()
    assert economy.claim_rescue(broke, at(1)) == settings.RESCUE_AMOUNT
    TelegramUser.objects.filter(pk=broke.pk).update(coins=0)
    assert economy.claim_rescue(broke, at(1, 20)) == 0
    assert economy.claim_rescue(broke, at(2)) == settings.RESCUE_AMOUNT


def test_daily_gives_rescue_when_already_claimed_and_broke(make_user, daily_on):
    user = make_user()
    economy.claim_daily(user, at(1))
    from wallet.services import apply_transaction

    apply_transaction(user, -2, TxType.ENTRY_FEE, "spend-all")
    result = economy.claim_daily(user, at(1, 15))
    assert result.claimed is False and result.rescue == settings.RESCUE_AMOUNT
    assert find_mismatches() == []


def _play_one_match(group, users, fee=10):
    match = services.create_match(
        group, users[0], "quick_math", entry_fee=fee, prize_split=[100], join_seconds=60, min_players=2, max_players=5
    )
    for u in users:
        services.join_match(match.pk, u)
    services.start_match(match.pk)
    return services.finish_match(match.pk, [Standing(users[0].pk, 1, 1.0)])


def test_referral_reward_every_n_friends_on_join(make_user, economy_settings):
    """هر ۱۰ نفری که با لینک دعوت ربات را استارت کنند = ۳۰ سکه (مقادیر پیش‌فرض پنل ادمین)، هر دسته یک بار."""
    referrer = make_user()
    rewards = []
    for i in range(21):
        make_user(referred_by=referrer)
        result = economy.check_referral_reward_on_join(referrer)
        rewards.append(result.reward)
        assert result.count == i + 1 and result.every == 10 and result.next_reward == 30
    assert [i + 1 for i, r in enumerate(rewards) if r] == [10, 20]
    assert set(rewards) == {0, 30}
    # فراخوانی دوباره برای همان دسته چیزی نمی‌دهد
    assert economy.check_referral_reward_on_join(referrer).reward == 0
    referrer.refresh_from_db()
    assert referrer.coins == 60
    assert CoinTransaction.objects.filter(type=TxType.REFERRAL, user=referrer).count() == 2
    assert find_mismatches() == []


def test_referral_reward_can_be_turned_off(make_user, economy_settings):
    economy_settings(referral_every=1, referral_reward=0)
    referrer = make_user()
    make_user(referred_by=referrer)
    assert economy.check_referral_reward_on_join(referrer).reward == 0
    assert not CoinTransaction.objects.filter(type=TxType.REFERRAL).exists()


def test_matches_never_pay_referral_again(group, make_user, economy_settings):
    """جایزه‌ی دعوت فقط موقع استارت است؛ بازی کردن دعوت‌شده دوباره جایزه نمی‌دهد (قبلاً دوبار پرداخت می‌شد)."""
    economy_settings(referral_every=1, referral_reward=3)
    referrer = make_user()
    invitee = make_user(coins=100, referred_by=referrer)
    TelegramUser.objects.filter(pk=invitee.pk).update(created_at=invitee.created_at - timedelta(days=3))
    _play_one_match(group, [invitee, make_user(coins=100)])
    assert not CoinTransaction.objects.filter(type=TxType.REFERRAL).exists()


def test_free_game_gives_no_coins_xp_or_stats(group, make_user):
    a, b = make_user(), make_user()
    result = _play_one_match(group, [a, b], fee=0)
    assert all(p.prize == 0 and p.xp == 0 and not p.won and not p.achievements for p in result.players)
    for user in (a, b):
        user.refresh_from_db()
        assert (user.coins, user.xp, user.games_played, user.wins) == (0, 0, 0, 0)
    from leaderboard.queries import top_players

    assert top_players(group.pk) == []


def test_level_formula_is_progressive():
    assert [xp_for_level(n) for n in range(1, 6)] == [0, 100, 300, 600, 1000]
    assert level_for_xp(0) == 1
    assert level_for_xp(99) == 1
    assert level_for_xp(100) == 2
    assert level_for_xp(299) == 2
    assert level_for_xp(1000) == 5
