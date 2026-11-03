import itertools

import pytest

from games.engine.payout import Standing, compute_payouts, proportional_payouts, rank_standings

SPLITS = [[100], [70, 30], [60, 30, 10], [50, 30, 20]]
SIZES = [(1,), (1, 1), (1, 1, 1), (1, 1, 1, 1, 1), (2, 1), (1, 2), (3,), (1, 3, 1), (2, 2, 2)]


def groups_of(*sizes):
    ids = itertools.count(1)
    return [[next(ids) for _ in range(size)] for size in sizes]


@pytest.mark.parametrize("split", SPLITS)
@pytest.mark.parametrize("pot", [0, 1, 7, 100, 999, 1000, 12345])
@pytest.mark.parametrize("sizes", SIZES)
def test_total_paid_always_equals_pot(split, pot, sizes):
    groups = groups_of(*sizes)
    payouts = compute_payouts(pot, split, groups)
    assert sum(payouts.values()) == pot
    assert all(v >= 0 for v in payouts.values())
    assert set(payouts) == {uid for g in groups for uid in g}


def test_winner_takes_all():
    assert compute_payouts(300, [100], groups_of(1, 1, 1)) == {1: 300, 2: 0, 3: 0}


def test_60_30_10():
    assert compute_payouts(1000, [60, 30, 10], groups_of(1, 1, 1, 1)) == {1: 600, 2: 300, 3: 100, 4: 0}


def test_fewer_players_than_shares_redistributes_extra_shares():
    # ۶۰-۳۰-۱۰ با دو بازیکن: سهم سوم به نسبت ۶۰:۳۰ بین دو نفر پخش می‌شود
    assert compute_payouts(900, [60, 30, 10], groups_of(1, 1)) == {1: 600, 2: 300}
    assert compute_payouts(500, [50, 30, 20], groups_of(1)) == {1: 500}


def test_rounding_goes_down_and_remainder_to_first():
    assert compute_payouts(101, [70, 30], groups_of(1, 1)) == {1: 71, 2: 30}
    assert compute_payouts(10, [60, 30, 10], groups_of(1, 1, 1)) == {1: 6, 2: 3, 3: 1}
    assert compute_payouts(7, [60, 30, 10], groups_of(1, 1, 1)) == {1: 5, 2: 2, 3: 0}


def test_tie_for_first_splits_combined_shares():
    # دو نفر اول مساوی: (۶۰+۳۰)/۲ برای هر کدام
    assert compute_payouts(1000, [60, 30, 10], groups_of(2, 1)) == {1: 450, 2: 450, 3: 100}


def test_tie_for_last_paid_place():
    assert compute_payouts(1000, [70, 30], groups_of(1, 2)) == {1: 700, 2: 150, 3: 150}


def test_everyone_tied_gets_equal_share():
    assert compute_payouts(300, [100], groups_of(3)) == {1: 100, 2: 100, 3: 100}
    assert compute_payouts(100, [100], groups_of(3)) == {1: 34, 2: 33, 3: 33}


def test_rank_by_score_then_time():
    groups = rank_standings([Standing(1, 10, 5.0), Standing(2, 30, 9.0), Standing(3, 10, 2.0), Standing(4, 0, None)])
    assert [[s.user_id for s in g] for g in groups] == [[2], [3], [1], [4]]


def test_rank_true_tie_when_score_and_time_equal():
    groups = rank_standings([Standing(1, 10, 3.0), Standing(2, 10, 3.0), Standing(3, 0), Standing(4, 0)])
    assert [[s.user_id for s in g] for g in groups] == [[1, 2], [3, 4]]


# ---------------------------------------------------------------- میز نقدی پوکر: سهم به اندازه‌ی ژتون
@pytest.mark.parametrize("pot", [0, 1, 7, 100, 285, 999, 12345])
@pytest.mark.parametrize("chips", [(1000, 1000), (980, 1020), (0, 3000, 0), (1, 1, 1), (2999, 1, 0, 0), (0, 0)])
def test_proportional_payouts_always_pay_the_whole_pot(pot, chips):
    stacks = dict(enumerate(chips, start=1))
    payouts = proportional_payouts(pot, stacks)
    assert sum(payouts.values()) == pot and set(payouts) == set(stacks)
    assert all(v >= 0 for v in payouts.values())
    total = sum(chips)
    for uid, c in stacks.items():
        if total:
            # هیچ‌کس بیش از یک سکه با سهم دقیقش فاصله ندارد و بی‌ژتون چیزی نمی‌برد
            assert abs(payouts[uid] - pot * c / total) < 1 + 1e-9
            assert c or payouts[uid] == 0


def test_proportional_payouts_follow_the_chips():
    assert proportional_payouts(300, {1: 1000, 2: 1000, 3: 1000}) == {1: 100, 2: 100, 3: 100}
    assert proportional_payouts(300, {1: 1500, 2: 0, 3: 1500}) == {1: 150, 2: 0, 3: 150}
    # باقیمانده به بزرگ‌ترین پشته (و در تساوی به شناسه‌ی کوچک‌تر) می‌رسد
    assert proportional_payouts(100, {1: 1000, 2: 2000}) == {1: 33, 2: 67}
    assert proportional_payouts(10, {}) == {}
