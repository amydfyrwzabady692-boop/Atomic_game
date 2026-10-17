"""تنها نقطه‌ی مجاز برای تغییر موجودی سکه."""

import uuid
from django.db import transaction

from core.models import TelegramUser

from .models import CoinTransaction, TxType


class InsufficientFunds(Exception):
    def __init__(self, balance: int, needed: int):
        super().__init__(f"balance={balance} needed={needed}")
        self.balance = balance
        self.needed = needed


class IdempotencyConflict(Exception):
    """کلید یکتا قبلاً برای کاربر/مقدار/نوع دیگری ثبت شده است (باگ در ساخت کلید)."""


def apply_transaction(user, amount: int, type: str, idempotency_key: str, match=None) -> CoinTransaction:
    """موجودی کاربر را به‌اندازه‌ی ``amount`` (مثبت یا منفی) تغییر می‌دهد و در ledger ثبت می‌کند.

    - اتمیک و با قفل ردیف کاربر (``select_for_update``)
    - موجودی هرگز منفی نمی‌شود (``InsufficientFunds``)
    - اگر ``idempotency_key`` قبلاً ثبت شده باشد همان تراکنش برگردانده می‌شود و موجودی
      دوباره تغییر نمی‌کند؛ در این حالت ``tx.duplicate`` برابر ``True`` است.
    - اگر همان کلید قبلاً برای کاربر، مقدار یا نوع دیگری ثبت شده باشد ``IdempotencyConflict``
      می‌دهد؛ وگرنه یک تراکنش واقعی بی‌صدا نادیده گرفته می‌شد.
    """
    user_id = user.pk if isinstance(user, TelegramUser) else int(user)
    amount = int(amount)
    with transaction.atomic():
        locked = TelegramUser.objects.select_for_update().get(pk=user_id)
        existing = CoinTransaction.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            if (existing.user_id, existing.amount, existing.type) != (user_id, amount, type):
                raise IdempotencyConflict(idempotency_key)
            existing.duplicate = True
            tx = existing
        else:
            new_balance = locked.coins + amount
            if new_balance < 0:
                raise InsufficientFunds(locked.coins, -amount)
            locked.coins = new_balance
            locked.save(update_fields=["coins"])
            tx = CoinTransaction.objects.create(
                user_id=user_id,
                amount=amount,
                balance_after=new_balance,
                type=type,
                ref_match=match,
                idempotency_key=idempotency_key,
            )
            tx.duplicate = False
        balance = locked.coins
    if isinstance(user, TelegramUser):
        user.coins = balance
    return tx


def transfer_coins(from_user, to_user, amount: int) -> tuple[CoinTransaction, CoinTransaction]:
    """انتقال مستقیم سکه از یک کاربر به کاربر دیگر با قفل ردیف و تراکنش اتمیک."""
    amount = int(amount)
    if amount <= 0:
        raise ValueError("مقدار انتقال باید بیشتر از صفر باشد.")
    from_id = from_user.pk if isinstance(from_user, TelegramUser) else int(from_user)
    to_id = to_user.pk if isinstance(to_user, TelegramUser) else int(to_user)
    if from_id == to_id:
        raise ValueError("انتقال به خودتان امکان‌پذیر نیست.")

    idempotency_base = f"transfer:{uuid.uuid4().hex[:16]}"

    with transaction.atomic():
        first_id, second_id = sorted([from_id, to_id])
        locked_users = {u.pk: u for u in TelegramUser.objects.select_for_update().filter(pk__in=[first_id, second_id])}
        sender = locked_users[from_id]
        receiver = locked_users[to_id]

        if sender.coins < amount:
            raise InsufficientFunds(sender.coins, amount)

        sender.coins -= amount
        sender.save(update_fields=["coins"])
        tx_out = CoinTransaction.objects.create(
            user_id=from_id,
            amount=-amount,
            balance_after=sender.coins,
            type=TxType.TRANSFER_OUT,
            idempotency_key=f"{idempotency_base}:out",
        )

        receiver.coins += amount
        receiver.save(update_fields=["coins"])
        tx_in = CoinTransaction.objects.create(
            user_id=to_id,
            amount=amount,
            balance_after=receiver.coins,
            type=TxType.TRANSFER_IN,
            idempotency_key=f"{idempotency_base}:in",
        )

    if isinstance(from_user, TelegramUser):
        from_user.coins = sender.coins
    if isinstance(to_user, TelegramUser):
        to_user.coins = receiver.coins

    return tx_out, tx_in
