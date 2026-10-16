from datetime import timedelta

import pytest
from django.utils import timezone

from games.engine import services
from games.engine.payout import Standing
from games.engine.services import MatchError
from games.models import Match, MatchStatus
from wallet.management.commands.audit_wallets import find_mismatches
from wallet.models import CoinTransaction, TxType

pytestmark = pytest.mark.django_db


def new_match(group, creator, fee=100, split=(60, 30, 10), **kwargs):
    params = {
        "entry_fee": fee,
        "prize_split": list(split),
        "join_seconds": 60,
        "min_players": 2,
        "max_players": 10,
    }
    params.update(kwargs)
    return services.create_match(group, creator, "quick_math", **params)


def test_join_deducts_fee_and_grows_pot(group, make_user):
    a, b = make_user(500), make_user(500)
    match = new_match(group, a)
    services.join_match(match.pk, a)
    match = services.join_match(match.pk, b)
    a.refresh_from_db()
    assert a.coins == 400
    assert match.pot == 200
    tx = CoinTransaction.objects.get(idempotency_key=f"entry:{match.pk}:{a.pk}")
    assert tx.type == TxType.ENTRY_FEE and tx.amount == -100 and tx.ref_match_id == match.pk


def test_double_join_charges_once(group, make_user):
    a = make_user(500)
    match = new_match(group, a)
    services.join_match(match.pk, a)
    with pytest.raises(MatchError) as err:
        services.join_match(match.pk, a)
    assert err.value.code == "already_joined"
    a.refresh_from_db()
    assert a.coins == 400
    assert Match.objects.get(pk=match.pk).pot == 100


def test_join_without_enough_coins(group, make_user):
    a, poor = make_user(500), make_user(30)
    match = new_match(group, a)
    with pytest.raises(MatchError) as err:
        services.join_match(match.pk, poor)
    assert err.value.code == "not_enough_coins"
    poor.refresh_from_db()
    assert poor.coins == 30
    assert match.players.count() == 0


def test_join_requires_private_start_and_not_banned(group, make_user):
    a = make_user(500)
    stranger = make_user(500, started_bot=False)
    banned = make_user(500, is_banned=True)
    match = new_match(group, a)
    with pytest.raises(MatchError) as err:
        services.join_match(match.pk, stranger)
    assert err.value.code == "need_start"
    with pytest.raises(MatchError) as err:
        services.join_match(match.pk, banned)
    assert err.value.code == "banned"


def test_join_after_deadline_or_when_full(group, make_user):
    a, b, c = make_user(500), make_user(500), make_user(500)
    match = new_match(group, a, max_players=2)
    services.join_match(match.pk, a)
    services.join_match(match.pk, b)
    with pytest.raises(MatchError) as err:
        services.join_match(match.pk, c)
    assert err.value.code == "lobby_full"
    Match.objects.filter(pk=match.pk).update(join_deadline=timezone.now() - timedelta(seconds=1))
    with pytest.raises(MatchError) as err:
        services.join_match(match.pk, c)
    assert err.value.code == "lobby_closed"


def test_only_one_active_match_per_group(group, make_user):
    a = make_user(500)
    match = new_match(group, a)
    with pytest.raises(MatchError) as err:
        new_match(group, a)
    assert err.value.code == "active_match_exists"
    services.cancel_match(match.pk)
    new_match(group, a)


def test_fee_outside_group_limits_rejected(group, make_user):
    group.min_entry, group.max_entry = 50, 250
    group.save()
    a = make_user(5000)
    for fee in (0, 500):
        with pytest.raises(MatchError) as err:
            new_match(group, a, fee=fee)
        assert err.value.code == "fee_not_allowed"
    new_match(group, a, fee=250)


def test_cancel_refunds_everyone_exactly_once(group, make_user):
    a, b = make_user(500), make_user(300)
    match = new_match(group, a)
    services.join_match(match.pk, a)
    services.join_match(match.pk, b)
    match, refunded = services.cancel_match(match.pk, "manual")
    assert match.status == MatchStatus.CANCELLED and match.pot == 0
    assert len(refunded) == 2
    # لغو دوباره نباید دوباره پول برگرداند
    _, again = services.cancel_match(match.pk)
    assert again == []
    a.refresh_from_db()
    b.refresh_from_db()
    assert (a.coins, b.coins) == (500, 300)
    assert CoinTransaction.objects.filter(type=TxType.REFUND).count() == 2
    assert find_mismatches() == []


def test_start_with_too_few_players_then_cancel_refunds(group, make_user):
    a = make_user(500)
    match = new_match(group, a)
    services.join_match(match.pk, a)
    with pytest.raises(MatchError) as err:
        services.start_match(match.pk)
    assert err.value.code == "not_enough_players"
    services.cancel_match(match.pk, "not_enough_players")
    a.refresh_from_db()
    assert a.coins == 500


def test_finish_pays_prizes_and_updates_stats(group, make_user):
    users = [make_user(1000) for _ in range(4)]
    match = new_match(group, users[0], fee=250)
    for u in users:
        services.join_match(match.pk, u)
    services.start_match(match.pk)
    standings = [
        Standing(users[0].pk, 30, 9.0),
        Standing(users[1].pk, 50, 8.0),
        Standing(users[2].pk, 30, 4.0),
        Standing(users[3].pk, 0, None),
    ]
    result = services.finish_match(match.pk, standings)
    by_user = {r.user.pk: r for r in result.players}
    assert by_user[users[1].pk].rank == 1 and by_user[users[1].pk].prize == 600
    assert by_user[users[2].pk].rank == 2 and by_user[users[2].pk].prize == 300
    assert by_user[users[0].pk].rank == 3 and by_user[users[0].pk].prize == 100
    assert by_user[users[3].pk].rank == 4 and by_user[users[3].pk].prize == 0
    assert sum(r.prize for r in result.players) == 1000

    winner = users[1]
    winner.refresh_from_db()
    # ۱۰۰۰ - ۲۵۰ + ۶۰۰ + جایزه‌ی دستاوردهای «اولین بازی» و «اولین برد»
    assert winner.coins == 1000 - 250 + 600 + 50 + 100
    assert winner.wins == 1 and winner.games_played == 1
    assert winner.xp == 40
    assert {a.code for a in by_user[winner.pk].achievements} == {"first_game", "first_win"}
    assert Match.objects.get(pk=match.pk).status == MatchStatus.FINISHED
    assert find_mismatches() == []


def test_finish_is_idempotent(group, make_user):
    a, b = make_user(500), make_user(500)
    match = new_match(group, a, split=(100,))
    services.join_match(match.pk, a)
    services.join_match(match.pk, b)
    services.start_match(match.pk)
    standings = [Standing(a.pk, 5, 1.0), Standing(b.pk, 1, 2.0)]
    assert services.finish_match(match.pk, standings) is not None
    assert services.finish_match(match.pk, standings) is None
    assert CoinTransaction.objects.filter(type=TxType.PRIZE).count() == 1
    assert find_mismatches() == []


def test_finish_with_full_tie_returns_stakes(group, make_user):
    a, b = make_user(500), make_user(500)
    match = new_match(group, a, split=(100,))
    services.join_match(match.pk, a)
    services.join_match(match.pk, b)
    services.start_match(match.pk)
    result = services.finish_match(match.pk, [])
    assert [r.prize for r in result.players] == [100, 100]
    assert [r.rank for r in result.players] == [1, 1]


def test_free_match_gives_no_coins_xp_or_stats(group, make_user):
    a, b = make_user(0), make_user(0)
    match = new_match(group, a, fee=0)
    services.join_match(match.pk, a)
    services.join_match(match.pk, b)
    services.start_match(match.pk)
    result = services.finish_match(match.pk, [Standing(a.pk, 3, 1.0), Standing(b.pk, 1, 1.0)])
    assert all(r.prize == 0 for r in result.players)
    assert not CoinTransaction.objects.filter(type__in=[TxType.PRIZE, TxType.ENTRY_FEE]).exists()
    a.refresh_from_db()
    assert (a.xp, a.games_played, a.wins) == (0, 0, 0)
    assert all(r.xp == 0 and not r.won for r in result.players)


def test_cannot_cancel_finished_match(group, make_user):
    a, b = make_user(500), make_user(500)
    match = new_match(group, a)
    services.join_match(match.pk, a)
    services.join_match(match.pk, b)
    services.start_match(match.pk)
    services.finish_match(match.pk, [Standing(a.pk, 1, 1.0)])
    match, refunded = services.cancel_match(match.pk)
    assert match.status == MatchStatus.FINISHED and refunded == []
    assert not CoinTransaction.objects.filter(type=TxType.REFUND).exists()


def test_cancel_running_match_refunds(group, make_user):
    a, b = make_user(500), make_user(500)
    match = new_match(group, a)
    services.join_match(match.pk, a)
    services.join_match(match.pk, b)
    services.start_match(match.pk)
    services.cancel_match(match.pk, "restart")
    a.refresh_from_db()
    b.refresh_from_db()
    assert (a.coins, b.coins) == (500, 500)
    assert find_mismatches() == []


# ------------------------------------------------------------------ قانون جایزه: امتیاز صفر یعنی باخت
def _finished(group, make_user, scores, split=(60, 30, 10), fee=100):
    users = [make_user(coins=1000) for _ in scores]
    match = services.create_match(
        group, users[0], "quick_math", entry_fee=fee, prize_split=list(split), join_seconds=60, min_players=2, max_players=10
    )
    for user in users:
        services.join_match(match.pk, user)
    services.start_match(match.pk)
    standings = [Standing(u.pk, s, 100.0 + i if s else None) for i, (u, s) in enumerate(zip(users, scores, strict=True))]
    result = services.finish_match(match.pk, standings)
    return users, {r.user.pk: r for r in result.players}


def test_zero_score_players_get_no_prize(group, make_user):
    users, by_id = _finished(group, make_user, [7, 3, 0, 0])
    prizes = [by_id[u.pk].prize for u in users]
    # ۴۰۰ سکه فقط بین دو امتیازگیر به نسبت ۶۰:۳۰ (۲۶۶ + ۱ باقی‌مانده و ۱۳۳)
    assert prizes == [267, 133, 0, 0] and sum(prizes) == 400
    assert [by_id[u.pk].rank for u in users] == [1, 2, 3, 3]
    assert by_id[users[0].pk].won and not by_id[users[2].pk].won
    assert find_mismatches() == []


def test_single_scorer_takes_the_whole_pot(group, make_user):
    users, by_id = _finished(group, make_user, [0, 5, 0])
    assert [by_id[u.pk].prize for u in users] == [0, 300, 0]


def test_nobody_scoring_or_a_draw_splits_the_pot_equally(group, make_user):
    users, by_id = _finished(group, make_user, [0, 0, 0])
    assert [by_id[u.pk].prize for u in users] == [100, 100, 100]
    assert not any(r.won for r in by_id.values())


def test_tied_scorers_share_their_places(group, make_user):
    users = [make_user(coins=1000) for _ in range(3)]
    match = services.create_match(
        group, users[0], "quick_math", entry_fee=100, prize_split=[60, 30, 10], join_seconds=60, min_players=2, max_players=10
    )
    for user in users:
        services.join_match(match.pk, user)
    services.start_match(match.pk)
    # دو نفر اول هم امتیاز و هم زمان برابر دارند؛ جایگاه ۱ و ۲ (۹۰٪) را نصف می‌کنند
    result = services.finish_match(
        match.pk, [Standing(users[0].pk, 5, 10.0), Standing(users[1].pk, 5, 10.0), Standing(users[2].pk, 2, 5.0)]
    )
    prizes = {r.user.pk: r.prize for r in result.players}
    assert prizes[users[0].pk] + prizes[users[1].pk] == 270 and abs(prizes[users[0].pk] - prizes[users[1].pk]) <= 1
    assert prizes[users[2].pk] == 30
