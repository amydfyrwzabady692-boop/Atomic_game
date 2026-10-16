import threading

import pytest
from django.core.management import call_command
from django.db import IntegrityError, connections, transaction

from core.models import TelegramUser
from wallet.management.commands.audit_wallets import find_mismatches
from wallet.models import CoinTransaction, LedgerImmutableError, TxType
from wallet.services import IdempotencyConflict, InsufficientFunds, apply_transaction

from .conftest import requires_postgres

pytestmark = pytest.mark.django_db


def test_credit_and_debit_update_balance_and_ledger(make_user):
    user = make_user()
    apply_transaction(user, 500, TxType.ADMIN_GRANT, "k1")
    tx = apply_transaction(user, -200, TxType.ENTRY_FEE, "k2")
    user.refresh_from_db()
    assert user.coins == 300
    assert tx.balance_after == 300
    assert list(user.transactions.order_by("id").values_list("amount", flat=True)) == [500, -200]


def test_balance_never_goes_negative(make_user):
    user = make_user(coins=100)
    with pytest.raises(InsufficientFunds) as err:
        apply_transaction(user, -101, TxType.ENTRY_FEE, "too-much")
    assert err.value.balance == 100
    user.refresh_from_db()
    assert user.coins == 100
    assert not CoinTransaction.objects.filter(idempotency_key="too-much").exists()


def test_idempotency_key_prevents_double_apply(make_user):
    user = make_user(coins=100)
    first = apply_transaction(user, -40, TxType.ENTRY_FEE, "same-key")
    second = apply_transaction(user, -40, TxType.ENTRY_FEE, "same-key")
    user.refresh_from_db()
    assert user.coins == 60
    assert first.pk == second.pk
    assert first.duplicate is False and second.duplicate is True
    assert CoinTransaction.objects.filter(idempotency_key="same-key").count() == 1


def test_reused_key_for_other_user_or_amount_is_rejected(make_user):
    a, b = make_user(coins=100), make_user(coins=100)
    apply_transaction(a, -10, TxType.ENTRY_FEE, "shared-key")
    with pytest.raises(IdempotencyConflict):
        apply_transaction(b, -10, TxType.ENTRY_FEE, "shared-key")
    with pytest.raises(IdempotencyConflict):
        apply_transaction(a, -20, TxType.ENTRY_FEE, "shared-key")
    a.refresh_from_db()
    b.refresh_from_db()
    assert (a.coins, b.coins) == (90, 100)


def test_db_check_constraint_blocks_negative_coins(make_user):
    user = make_user(coins=10)
    with pytest.raises(IntegrityError), transaction.atomic():
        TelegramUser.objects.filter(pk=user.pk).update(coins=-1)


def test_ledger_rows_are_immutable(make_user):
    user = make_user(coins=10)
    tx = user.transactions.get()
    tx.amount = 999
    with pytest.raises(LedgerImmutableError):
        tx.save()
    with pytest.raises(LedgerImmutableError):
        tx.delete()


def test_audit_detects_mismatch(make_user):
    good = make_user(coins=100)
    bad = make_user(coins=100)
    assert find_mismatches() == []
    call_command("audit_wallets")
    TelegramUser.objects.filter(pk=bad.pk).update(coins=150)
    assert [m[0] for m in find_mismatches()] == [bad.pk]
    with pytest.raises(SystemExit):
        call_command("audit_wallets")
    assert good.pk not in [m[0] for m in find_mismatches()]


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


@requires_postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_debits_never_overdraw(make_user):
    user = make_user(coins=100)
    errors = _run_threads(lambda i: apply_transaction(user.pk, -60, TxType.ENTRY_FEE, f"race:{i}"), 8)
    user.refresh_from_db()
    assert user.coins == 40
    assert len(errors) == 7 and all(isinstance(e, InsufficientFunds) for e in errors)
    assert find_mismatches() == []


@requires_postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_same_key_applies_once(make_user):
    user = make_user(coins=100)
    errors = _run_threads(lambda i: apply_transaction(user.pk, -10, TxType.ENTRY_FEE, "double-click"), 8)
    user.refresh_from_db()
    assert errors == []
    assert user.coins == 90
    assert CoinTransaction.objects.filter(idempotency_key="double-click").count() == 1


@requires_postgres
@pytest.mark.django_db(transaction=True)
def test_many_concurrent_mixed_transactions_keep_ledger_consistent(make_user):
    users = [make_user(coins=1000) for _ in range(3)]

    def work(i):
        apply_transaction(users[i % 3].pk, -7 if i % 2 else 5, TxType.ADMIN_GRANT, f"mix:{i}")

    assert _run_threads(work, 30) == []
    assert find_mismatches() == []
