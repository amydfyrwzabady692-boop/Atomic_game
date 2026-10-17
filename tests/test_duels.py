import time
from datetime import timedelta

import pytest
from django.utils import timezone

from arcade import board
from games import duels, gridlive
from games.duels import DuelError
from games.models import Duel, DuelTicket, Match, MatchStatus
from wallet.management.commands.audit_wallets import find_mismatches
from wallet.models import CoinTransaction, TxType

pytestmark = pytest.mark.django_db


def test_search_without_partner_waits_in_queue(make_user):
    a = make_user(500)
    ticket = duels.search(a, "tictactoe", 100)
    assert isinstance(ticket, DuelTicket) and ticket.status == DuelTicket.Status.SEARCHING
    # جستجوی دوباره جایگزین قبلی می‌شود
    again = duels.search(a, "tictactoe", 50)
    assert DuelTicket.objects.filter(user=a, status=DuelTicket.Status.SEARCHING).get().pk == again.pk


def test_same_stake_starts_immediately_and_takes_fees(make_user):
    a, b = make_user(500), make_user(500)
    duels.search(a, "tictactoe", 100)
    duel = duels.search(b, "tictactoe", 100)
    assert isinstance(duel, Duel) and duel.status == Duel.Status.PLAYING and duel.stake == 100
    match = duel.match
    assert match.status == MatchStatus.RUNNING and match.group is None and match.pot == 200
    assert board.live_match(match.token) is not None
    a.refresh_from_db()
    b.refresh_from_db()
    assert (a.coins, b.coins) == (400, 400)
    assert find_mismatches() == []


def test_different_stakes_do_not_match_but_flexible_does(make_user):
    a, b, c = make_user(500), make_user(500), make_user(500)
    duels.search(a, "chess", 100)
    assert isinstance(duels.search(b, "chess", 50), DuelTicket)
    duel = duels.search(c, "chess", None)  # «فرقی نمی‌کند» با قدیمی‌ترین منتظر جفت می‌شود
    assert isinstance(duel, Duel) and duel.status == Duel.Status.NEGOTIATING
    assert (duel.player_a_id, duel.offer_a, duel.offer_b) == (a.pk, 100, None)
    # بازی دیگر هم جفت نمی‌شود
    d = make_user(500)
    assert isinstance(duels.search(d, "poker", 50), DuelTicket)


def test_negotiation_until_both_agree(make_user):
    a, b = make_user(1000), make_user(1000)
    duels.search(a, "connect4", None)
    duel = duels.search(b, "connect4", None)
    assert duel.status == Duel.Status.NEGOTIATING and duel.offer_a is None and duel.offer_b is None
    with pytest.raises(DuelError, match="no_offer"):
        duels.accept(a, duel.pk)
    duel = duels.offer(a, duel.pk, 250)
    assert duel.status == Duel.Status.NEGOTIATING and duel.version == 2
    duel = duels.offer(b, duel.pk, 100)
    assert duel.status == Duel.Status.NEGOTIATING
    duel = duels.accept(a, duel.pk)  # الف پیشنهاد ب را قبول می‌کند
    assert duel.status == Duel.Status.PLAYING and duel.stake == 100
    with pytest.raises(DuelError, match="duel_closed"):
        duels.offer(b, duel.pk, 50)
    with pytest.raises(DuelError, match="already_in_duel"):
        duels.search(a, "chess", None)


def test_outsider_cannot_touch_a_duel(make_user):
    a, b, c = make_user(), make_user(), make_user()
    duels.search(a, "chess", None)
    duel = duels.search(b, "chess", None)
    with pytest.raises(DuelError, match="not_your_duel"):
        duels.offer(c, duel.pk, 0)


def test_not_enough_coins_cancels_without_taking_anything(make_user):
    a, b = make_user(1000), make_user(1000)
    duels.search(a, "tictactoe", None)
    duel = duels.search(b, "tictactoe", None)
    duels.offer(a, duel.pk, 500)
    # ب سکه‌اش را جای دیگری خرج کرده
    from wallet.services import apply_transaction

    apply_transaction(b, -900, TxType.SHOP, "spend")
    with pytest.raises(DuelError, match="not_enough_coins"):
        duels.offer(b, duel.pk, 500)
    # حتی اگر بررسی اولیه رد شود (مسابقه‌ی هم‌زمان)، شروع هیچ ورودی‌ای کم نمی‌کند
    Duel.objects.filter(pk=duel.pk).update(offer_b=500)
    duels._start(duel.pk)
    duel.refresh_from_db()
    assert duel.status == Duel.Status.CANCELLED and duel.cancel_reason == "coins"
    a.refresh_from_db()
    assert a.coins == 1000 and not Match.objects.exists()
    assert find_mismatches() == []


def test_search_needs_coins_and_valid_input(make_user):
    poor = make_user(10)
    with pytest.raises(DuelError, match="not_enough_coins"):
        duels.search(poor, "chess", 100)
    with pytest.raises(DuelError, match="bad_game"):
        duels.search(poor, "quiz", None)
    with pytest.raises(DuelError, match="bad_stake"):
        duels.search(poor, "chess", -5)
    stranger = make_user(started_bot=False)
    with pytest.raises(DuelError, match="need_start"):
        duels.search(stranger, "chess", None)


def test_cancel_and_expiry(make_user):
    a, b = make_user(), make_user()
    duels.search(a, "chess", None)
    duel = duels.search(b, "chess", None)
    duel = duels.cancel(b, duel.pk)
    assert duel.status == Duel.Status.CANCELLED and duel.cancel_reason == "left_b"

    c = make_user()
    duels.search(c, "poker", None)
    later = timezone.now() + timedelta(seconds=duels.SEARCH_SECONDS + 1)
    expired = duels.expire(later)
    assert [t.user_id for t in expired] == [c.pk]
    assert DuelTicket.objects.get(user=c).status == DuelTicket.Status.EXPIRED

    d, e = make_user(), make_user()
    duels.search(d, "chess", None)
    duel = duels.search(e, "chess", None)
    duels.expire(timezone.now() + timedelta(seconds=duels.NEGOTIATE_SECONDS + 1))
    duel.refresh_from_db()
    assert duel.status == Duel.Status.CANCELLED and duel.cancel_reason == "timeout"


def _win_tictactoe(match):
    state = Match.objects.get(pk=match.pk).state["board"]
    x, o = state["sides"]["X"], state["sides"]["O"]
    for user, cell in [(x, 0), (o, 3), (x, 1), (o, 4), (x, 2)]:
        board.update(match.pk, lambda s, user=user, cell=cell: gridlive.apply_move(s, user, cell, 0, "", time.time()))
    return x


def test_finished_duel_pays_the_whole_pot_to_the_winner(make_user):
    a, b = make_user(500), make_user(500)
    duels.search(a, "tictactoe", 100)
    duel = duels.search(b, "tictactoe", 100)
    assert duels.finish_if_over(duel.pk) is None  # هنوز در جریان
    winner = _win_tictactoe(duel.match)
    result = duels.finish_if_over(duel.pk)
    assert result is not None
    duel.refresh_from_db()
    assert duel.status == Duel.Status.FINISHED and duel.match.status == MatchStatus.FINISHED
    prize = CoinTransaction.objects.get(type=TxType.PRIZE)
    assert (prize.user_id, prize.amount) == (winner, 200)
    assert duels.finish_if_over(duel.pk) is None  # فقط یک بار
    assert find_mismatches() == []


def test_free_duel_has_no_coins_or_points(make_user):
    a, b = make_user(), make_user()
    duels.search(a, "tictactoe", 0)
    duel = duels.search(b, "tictactoe", 0)
    assert duel.status == Duel.Status.PLAYING and duel.stake == 0
    _win_tictactoe(duel.match)
    duels.finish_if_over(duel.pk)
    for user in (a, b):
        user.refresh_from_db()
        assert (user.coins, user.xp, user.wins) == (0, 0, 0)


def test_admin_cancelled_duel_match_closes_the_duel(make_user):
    from games.engine import services

    a, b = make_user(500), make_user(500)
    duels.search(a, "chess", 100)
    duel = duels.search(b, "chess", 100)
    services.cancel_match(duel.match.pk, "admin")
    assert duels.finish_if_over(duel.pk) is None
    duel.refresh_from_db()
    assert duel.status == Duel.Status.CANCELLED and duel.cancel_reason == "admin"
    a.refresh_from_db()
    assert a.coins == 500


def test_duel_resign_finishes_cleanly_without_outer_join_error(make_user):
    a, b = make_user(500), make_user(500)
    duels.search(a, "chess", 100)
    duel = duels.search(b, "chess", 100)
    assert duel.status == Duel.Status.PLAYING
    assert duel.match.group is None

    # Player a resigns / تسلیم
    board.update(duel.match.pk, lambda st: board.rules_for(st).resign(st, a.pk))
    result = duels.finish_if_over(duel.pk)
    assert result is not None
    duel.refresh_from_db()
    assert duel.status == Duel.Status.FINISHED
    assert duel.match.status == MatchStatus.FINISHED
    assert any(p.user_id == b.pk and p.won for p in result.players)
    b.refresh_from_db()
    assert b.coins == 600  # 500 - 100 + 200 pot
    assert find_mismatches() == []


