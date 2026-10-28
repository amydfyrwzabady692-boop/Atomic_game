import threading

import pytest
from django.db import connections

from wallet import services
from wallet.management.commands.audit_wallets import find_mismatches
from wallet.models import CoinTransaction, EconomySettings, SellRequest, TopUpRequest, TxType
from wallet.services import IdempotencyConflict, InsufficientFunds, WalletError, transfer_coins

from .conftest import requires_postgres

pytestmark = pytest.mark.django_db


def test_economy_settings_defaults():
    eco = EconomySettings.load()
    assert eco.coin_price_toman == 1000
    assert eco.topup_fee_percent == 10
    assert eco.min_sell_coins == 100
    assert eco.coin_sell_price_toman == 1000


def test_transfer_coins_success(make_user):
    sender = make_user(coins=250)
    receiver = make_user(coins=50)

    out_tx, in_tx = transfer_coins(sender, receiver, 100)
    sender.refresh_from_db()
    receiver.refresh_from_db()

    assert sender.coins == 150
    assert receiver.coins == 150
    assert out_tx.type == TxType.TRANSFER_OUT
    assert out_tx.amount == -100
    assert in_tx.type == TxType.TRANSFER_IN
    assert in_tx.amount == 100


def test_transfer_coins_insufficient_funds(make_user):
    sender = make_user(coins=30)
    receiver = make_user(coins=10)

    with pytest.raises(InsufficientFunds):
        transfer_coins(sender, receiver, 50)

    sender.refresh_from_db()
    receiver.refresh_from_db()
    assert sender.coins == 30
    assert receiver.coins == 10


def test_transfer_coins_invalid_amount_or_self(make_user):
    user = make_user(coins=100)
    other = make_user(coins=10)

    with pytest.raises(ValueError):
        transfer_coins(user, user, 50)

    with pytest.raises(ValueError):
        transfer_coins(user, other, 0)

    with pytest.raises(ValueError):
        transfer_coins(user, other, -10)


def test_topup_and_sell_models(make_user):
    user = make_user(coins=200)

    topup = TopUpRequest.objects.create(
        user=user,
        coins=100,
        amount_toman=100000,
        fee_toman=10000,
        total_toman=110000,
        receipt_photo_id="photo_123",
    )
    assert topup.status == TopUpRequest.Status.PENDING
    assert topup.total_toman == 110000

    sell = SellRequest.objects.create(
        user=user,
        coins=100,
        amount_toman=100000,
        card_number="6037991234567890",
        card_holder="User Test",
    )
    assert sell.status == SellRequest.Status.PENDING
    assert sell.coins == 100


def _run_threads(target, count):
    errors = []

    def wrapper(i):
        try:
            target(i)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=wrapper, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    return errors


# ---------------------------------------------------------------------- انتقال: بدون دوبار حساب شدن
def test_transfer_with_the_same_key_moves_coins_only_once(make_user):
    sender, receiver = make_user(coins=500), make_user(coins=0)
    first = transfer_coins(sender, receiver, 120, idempotency_key="transfer:tok1")
    again = transfer_coins(sender, receiver, 120, idempotency_key="transfer:tok1")
    sender.refresh_from_db()
    receiver.refresh_from_db()
    assert (sender.coins, receiver.coins) == (380, 120)
    assert not first[0].duplicate and again[0].duplicate and again[1].duplicate
    assert CoinTransaction.objects.filter(idempotency_key__startswith="transfer:tok1").count() == 2
    assert find_mismatches() == []


def test_transfer_key_reused_for_another_amount_is_rejected(make_user):
    sender, receiver = make_user(coins=500), make_user()
    transfer_coins(sender, receiver, 100, idempotency_key="transfer:tok2")
    with pytest.raises(IdempotencyConflict):
        transfer_coins(sender, receiver, 200, idempotency_key="transfer:tok2")
    sender.refresh_from_db()
    assert sender.coins == 400


def test_transfer_to_a_banned_user_is_refused(make_user):
    sender, receiver = make_user(coins=500), make_user(is_banned=True)
    with pytest.raises(WalletError) as err:
        transfer_coins(sender, receiver, 100)
    assert err.value.code == "banned"
    sender.refresh_from_db()
    assert sender.coins == 500


@requires_postgres
@pytest.mark.django_db(transaction=True)
def test_crossing_transfers_never_deadlock_or_lose_coins(make_user):
    a, b = make_user(coins=1000), make_user(coins=1000)

    def run(i):
        if i % 2:
            transfer_coins(a.pk, b.pk, 10)
        else:
            transfer_coins(b.pk, a.pk, 10)

    errors = _run_threads(run, 16)
    assert errors == []
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.coins + b.coins == 2000 and (a.coins, b.coins) == (1000, 1000)
    assert find_mismatches() == []


# ---------------------------------------------------------------------- شارژ و فروش: یک بار رسیدگی
def test_topup_is_credited_once_even_if_two_admins_click(make_user):
    user = make_user()
    req = services.create_topup_request(user, 150, "photo-file-id")
    assert (req.amount_toman, req.fee_toman, req.total_toman) == (150_000, 15_000, 165_000)
    first = services.approve_topup(req.pk, 1, "ادمین یک")
    second = services.approve_topup(req.pk, 2, "ادمین دو")
    late_reject = services.reject_topup(req.pk, 3, "ادمین سه")
    user.refresh_from_db()
    assert first.changed and not second.changed and not late_reject.changed
    assert user.coins == 150 and first.balance == 150
    req.refresh_from_db()
    assert req.status == TopUpRequest.Status.APPROVED and "ادمین یک" in req.admin_note
    assert CoinTransaction.objects.filter(type=TxType.TOPUP).count() == 1
    assert find_mismatches() == []


def test_rejected_topup_cannot_be_approved_later(make_user):
    user = make_user()
    req = services.create_topup_request(user, 50, "photo")
    assert services.reject_topup(req.pk, 1).changed
    assert not services.approve_topup(req.pk, 2).changed
    user.refresh_from_db()
    assert user.coins == 0


def test_topup_amount_limits(make_user):
    user = make_user()
    for bad in (0, -5, services.MAX_REQUEST_COINS + 1, True, "10"):
        with pytest.raises(WalletError):
            services.create_topup_request(user, bad, "photo")


def test_sell_request_debits_and_creates_the_request_together(make_user):
    user = make_user(coins=300)
    req = services.create_sell_request(user, 200, "6037991234567893", "علی محمدی")
    user.refresh_from_db()
    assert user.coins == 100 and req.amount_toman == 200_000 and req.status == SellRequest.Status.PENDING
    assert CoinTransaction.objects.get(idempotency_key=f"sell:{req.pk}").amount == -200
    # موجودی کافی نیست: نه سکه‌ای کم می‌شود و نه درخواستی ثبت می‌شود
    with pytest.raises(InsufficientFunds):
        services.create_sell_request(user, 150, "6037991234567893", "علی محمدی")
    assert SellRequest.objects.count() == 1
    with pytest.raises(WalletError):
        services.create_sell_request(user, 50, "6037991234567893", "علی محمدی")  # کمتر از حداقل فروش
    assert find_mismatches() == []


def test_sell_is_paid_or_refunded_but_never_both(make_user):
    user = make_user(coins=400)
    paid = services.create_sell_request(user, 100, "6037991234567893", "علی")
    refunded = services.create_sell_request(user, 100, "6037991234567893", "علی")
    assert services.mark_sell_paid(paid.pk, 1).changed
    assert not services.reject_sell(paid.pk, 2).changed  # بعد از واریز دیگر سکه برنمی‌گردد
    review = services.reject_sell(refunded.pk, 1)
    assert review.changed and review.balance == 300
    assert not services.reject_sell(refunded.pk, 1).changed
    assert not services.mark_sell_paid(refunded.pk, 2).changed
    user.refresh_from_db()
    assert user.coins == 300
    assert CoinTransaction.objects.filter(type=TxType.REFUND).count() == 1
    assert find_mismatches() == []


@pytest.mark.parametrize(
    "text, expected",
    [
        ("6037991234567893 علی محمدی", ("6037991234567893", "علی محمدی")),
        ("۶۰۳۷-۹۹۱۲-۳۴۵۶-۷۸۹۳  به نام علی محمدی", ("6037991234567893", "به نام علی محمدی")),
        ("Ali Rezaei 6037 9912 3456 7893", ("6037991234567893", "Ali Rezaei")),
        ("IR12 3456 7890 1234 5678 9012 34 مریم", ("IR123456789012345678901234", "مریم")),
    ],
)
def test_bank_account_parsing(text, expected):
    assert services.parse_bank_account(text) == expected


@pytest.mark.parametrize("text, code", [("6037991234567890 علی", "bad_card"), ("1234 علی", "bad_card"), ("6037991234567893", "no_holder")])
def test_bank_account_parsing_rejects_typos(text, code):
    with pytest.raises(WalletError) as err:
        services.parse_bank_account(text)
    assert err.value.code == code


@requires_postgres
@pytest.mark.django_db(transaction=True)
def test_simultaneous_approve_and_reject_only_one_wins(make_user):
    user = make_user()
    req = services.create_topup_request(user, 100, "photo")
    results = []

    def run(i):
        action = services.approve_topup if i % 2 else services.reject_topup
        results.append(action(req.pk, i).changed)

    assert _run_threads(run, 8) == []
    assert results.count(True) == 1
    req.refresh_from_db()
    user.refresh_from_db()
    assert user.coins == (100 if req.status == TopUpRequest.Status.APPROVED else 0)
    assert find_mismatches() == []
