"""تنها نقطه‌ی مجاز برای تغییر موجودی سکه.

سکه فقط ارز مجازی تفریحی است: خرید با پول واقعی، برداشت و انتقال بین کاربران
وجود ندارد و نباید اضافه شود.
"""

from django.db import transaction

from core.models import TelegramUser

from .models import CoinTransaction


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
