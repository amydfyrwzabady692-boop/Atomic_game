"""تنها نقطه‌ی مجاز برای تغییر موجودی سکه.

همه‌ی جابه‌جایی‌های سکه (ورودی و جایزه‌ی بازی، انتقال بین کاربران، شارژ با رسید و فروش سکه) از همین
ماژول می‌گذرند: اتمیک، با قفل ردیف کاربر و کلید یکتای ledger تا هیچ سکه‌ای گم یا دوبار حساب نشود.
"""

import re
import uuid
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from core.models import TelegramUser
from core.textutils import normalize_fa

from .models import CoinTransaction, EconomySettings, SellRequest, TopUpRequest, TxType

# سقف تعداد سکه‌ی هر درخواست شارژ/فروش (مبلغ تومانی در ستون ۶۴ بیتی ذخیره می‌شود)
MAX_REQUEST_COINS = 100_000


class InsufficientFunds(Exception):
    def __init__(self, balance: int, needed: int):
        super().__init__(f"balance={balance} needed={needed}")
        self.balance = balance
        self.needed = needed


class IdempotencyConflict(Exception):
    """کلید یکتا قبلاً برای کاربر/مقدار/نوع دیگری ثبت شده است (باگ در ساخت کلید)."""


class WalletError(ValueError):
    """خطای قابل‌نمایش کیف پول؛ ``code`` کلید متن در ``core.texts.WALLET_ERRORS`` است."""

    def __init__(self, code: str, **context):
        super().__init__(code)
        self.code = code
        self.context = context


def _user_id(user) -> int:
    return user.pk if isinstance(user, TelegramUser) else int(user)


def apply_transaction(user, amount: int, type: str, idempotency_key: str, match=None) -> CoinTransaction:
    """موجودی کاربر را به‌اندازه‌ی ``amount`` (مثبت یا منفی) تغییر می‌دهد و در ledger ثبت می‌کند.

    - اتمیک و با قفل ردیف کاربر (``select_for_update``)
    - موجودی هرگز منفی نمی‌شود (``InsufficientFunds``)
    - اگر ``idempotency_key`` قبلاً ثبت شده باشد همان تراکنش برگردانده می‌شود و موجودی
      دوباره تغییر نمی‌کند؛ در این حالت ``tx.duplicate`` برابر ``True`` است.
    - اگر همان کلید قبلاً برای کاربر، مقدار یا نوع دیگری ثبت شده باشد ``IdempotencyConflict``
      می‌دهد؛ وگرنه یک تراکنش واقعی بی‌صدا نادیده گرفته می‌شد.
    """
    user_id = _user_id(user)
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


# ------------------------------------------------------------------ انتقال بین کاربران
def transfer_coins(from_user, to_user, amount: int, idempotency_key: str | None = None):
    """انتقال مستقیم سکه از یک کاربر به کاربر دیگر؛ برداشت و واریز در یک تراکنش اتمیک.

    ``idempotency_key`` (مثلاً توکن دکمه‌ی تأیید یا شناسه‌ی پیام دستور) جلوی انتقال دوباره با کلیک
    دوباره یا تحویل دوباره‌ی همان update را می‌گیرد: انتقال تکراری چیزی جابه‌جا نمی‌کند و دو تراکنش
    قبلی را با ``duplicate=True`` برمی‌گرداند. خروجی ``(tx_out, tx_in)`` است.
    """
    amount = int(amount)
    if amount <= 0:
        raise WalletError("bad_amount")
    from_id, to_id = _user_id(from_user), _user_id(to_user)
    if from_id == to_id:
        raise WalletError("self")
    base = idempotency_key or f"transfer:{uuid.uuid4().hex}"
    with transaction.atomic():
        # هر دو کاربر همیشه به ترتیب شناسه قفل می‌شوند تا دو انتقال هم‌زمانِ برعکس به بن‌بست نخورند
        locked = {
            u.pk: u
            for u in TelegramUser.objects.select_for_update().filter(pk__in=[from_id, to_id]).order_by("pk")
        }
        if from_id not in locked or to_id not in locked:
            raise WalletError("user_not_found")
        done = CoinTransaction.objects.filter(idempotency_key__in=[f"{base}:out", f"{base}:in"]).order_by("amount")
        if done:
            tx_out, tx_in = done[0], done[len(done) - 1]
            if (tx_out.user_id, tx_out.amount, tx_in.user_id, tx_in.amount) != (from_id, -amount, to_id, amount):
                raise IdempotencyConflict(base)
            tx_out.duplicate = tx_in.duplicate = True
        else:
            sender, receiver = locked[from_id], locked[to_id]
            if sender.is_banned or receiver.is_banned:
                raise WalletError("banned")
            if sender.coins < amount:
                raise InsufficientFunds(sender.coins, amount)
            tx_out = apply_transaction(sender, -amount, TxType.TRANSFER_OUT, f"{base}:out")
            tx_in = apply_transaction(receiver, amount, TxType.TRANSFER_IN, f"{base}:in")
        balances = dict(TelegramUser.objects.filter(pk__in=[from_id, to_id]).values_list("pk", "coins"))
    for user, pk in ((from_user, from_id), (to_user, to_id)):
        if isinstance(user, TelegramUser):
            user.coins = balances[pk]
    return tx_out, tx_in


# ------------------------------------------------------------------ شارژ کیف پول با رسید
@dataclass(frozen=True)
class Quote:
    coins: int
    amount: int  # مبلغ خام (تومان)
    fee: int
    total: int  # مبلغ قابل واریز


def topup_quote(coins: int, eco: EconomySettings) -> Quote:
    raw = coins * eco.coin_price_toman
    fee = raw * eco.topup_fee_percent // 100
    return Quote(coins, raw, fee, raw + fee)


def check_request_coins(coins, minimum: int = 1) -> int:
    if isinstance(coins, bool) or not isinstance(coins, int) or coins < minimum:
        raise WalletError("bad_amount", minimum=minimum)
    if coins > MAX_REQUEST_COINS:
        raise WalletError("too_many", maximum=MAX_REQUEST_COINS)
    return coins


def create_topup_request(user, coins: int, receipt_file_id: str, eco: EconomySettings | None = None) -> TopUpRequest:
    """درخواست شارژ با رسید واریز؛ سکه فقط بعد از تأیید ادمین (``approve_topup``) اضافه می‌شود."""
    eco = eco or EconomySettings.load()
    quote = topup_quote(check_request_coins(coins), eco)
    return TopUpRequest.objects.create(
        user_id=_user_id(user),
        coins=quote.coins,
        amount_toman=quote.amount,
        fee_toman=quote.fee,
        total_toman=quote.total,
        receipt_photo_id=receipt_file_id[:255],
    )


@dataclass
class Review:
    """نتیجه‌ی بررسی یک درخواست. ``changed`` یعنی همین فراخوانی وضعیت را عوض کرد (نه قبلاً کس دیگری)."""

    request: TopUpRequest | SellRequest
    changed: bool
    balance: int = 0


def _reviewer(admin_tg_id: int, admin_name: str) -> str:
    return f"{admin_tg_id} ({admin_name})"[:255] if admin_name else str(admin_tg_id)


def _review(model, req_id: int, status: str, note: str, refund_type: str | None = None, credit_type: str | None = None):
    """تغییر وضعیت «در انتظار» به وضعیت نهایی، فقط یک بار و زیر قفل ردیف درخواست.

    اگر دو ادمین هم‌زمان (یکی تأیید و یکی رد) کلیک کنند، فقط اولی اثر دارد و دومی ``changed=False``
    می‌گیرد؛ پس هیچ رسیدی هم شارژ و هم رد نمی‌شود و هیچ فروشی هم واریز و هم برگشت نمی‌خورد.
    """
    with transaction.atomic():
        req = model.objects.select_for_update().get(pk=req_id)
        if req.status != model.Status.PENDING:
            return Review(req, False)
        if credit_type:
            apply_transaction(req.user_id, req.coins, credit_type, f"topup:{req.pk}")
        if refund_type:
            apply_transaction(req.user_id, req.coins, refund_type, f"sell_refund:{req.pk}")
        req.status = status
        req.reviewed_at = timezone.now()
        req.admin_note = note[:255]
        req.save(update_fields=["status", "reviewed_at", "admin_note"])
    req = model.objects.select_related("user").get(pk=req.pk)
    return Review(req, True, req.user.coins)


def approve_topup(req_id: int, admin_tg_id: int, admin_name: str = "") -> Review:
    return _review(
        TopUpRequest, req_id, TopUpRequest.Status.APPROVED, f"Approved by {_reviewer(admin_tg_id, admin_name)}",
        credit_type=TxType.TOPUP,
    )  # fmt: skip


def reject_topup(req_id: int, admin_tg_id: int, admin_name: str = "") -> Review:
    return _review(TopUpRequest, req_id, TopUpRequest.Status.REJECTED, f"Rejected by {_reviewer(admin_tg_id, admin_name)}")


# ------------------------------------------------------------------ فروش سکه (تسویه)
_IBAN = re.compile(r"IR\s*((?:\d\s*){23}\d)(?!\d)", re.IGNORECASE)
_CARD = re.compile(r"(?<!\d)((?:\d[\s-]*){15}\d)(?!\d)")
# ارقام فارسی و عربی → انگلیسی (یک‌به‌یک، تا جای نویسه‌ها در متن عوض نشود)
_DIGITS = str.maketrans({d: str(i) for digits in ("۰۱۲۳۴۵۶۷۸۹", "٠١٢٣٤٥٦٧٨٩") for i, d in enumerate(digits)})


def luhn_ok(number: str) -> bool:
    """کارت‌های بانکی شتاب الگوریتم Luhn دارند؛ یک رقم اشتباه تقریباً همیشه همین‌جا پیدا می‌شود."""
    total = 0
    for index, digit in enumerate(reversed(number)):
        value = int(digit)
        if index % 2:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


def parse_bank_account(text: str) -> tuple[str, str]:
    """شماره کارت ۱۶ رقمی (یا شبای IR) و نام صاحب حساب را از یک پیام جدا می‌کند.

    ارقام فارسی و فاصله/خط تیره‌ی بین رقم‌ها پذیرفته می‌شود. خروجی ``(شماره، نام)``؛ اگر شماره‌ی
    معتبری نبود ``WalletError("bad_card")`` و اگر نام نبود ``WalletError("no_holder")``.
    """
    raw = (text or "").translate(_DIGITS)
    found = _IBAN.search(raw)
    if found:
        number = "IR" + re.sub(r"\D", "", found.group(1))
    else:
        found = _CARD.search(raw)
        if not found:
            raise WalletError("bad_card")
        number = re.sub(r"\D", "", found.group(1))
        if not luhn_ok(number):
            raise WalletError("bad_card")
    # نام صاحب حساب: بقیه‌ی همان پیام، بدون عدد و علامت‌ها
    rest = raw[: found.start()] + " " + raw[found.end() :]
    holder = " ".join(re.sub(r"[\d:\-–—_/|,،.#*]+", " ", rest).split())
    if len(normalize_fa(holder, keep_spaces=False)) < 3:
        raise WalletError("no_holder")
    return number, holder[:128]


def sell_quote(coins: int, eco: EconomySettings) -> int:
    return coins * eco.coin_sell_price_toman


def create_sell_request(
    user, coins: int, card_number: str, card_holder: str, eco: EconomySettings | None = None
) -> SellRequest:
    """درخواست فروش: سکه همان لحظه کم و درخواست ثبت می‌شود — هر دو در یک تراکنش.

    اگر ثبت درخواست به هر دلیلی نشود سکه‌ای هم کم نمی‌شود (قبلاً ممکن بود سکه کم شود و درخواستی ثبت نشود).
    """
    eco = eco or EconomySettings.load()
    coins = check_request_coins(coins, max(1, eco.min_sell_coins))
    with transaction.atomic():
        req = SellRequest.objects.create(
            user_id=_user_id(user),
            coins=coins,
            amount_toman=sell_quote(coins, eco),
            card_number=card_number[:32],
            card_holder=card_holder[:128],
        )
        apply_transaction(user, -coins, TxType.SELL, f"sell:{req.pk}")
    return req


def mark_sell_paid(req_id: int, admin_tg_id: int, admin_name: str = "", receipt: bool = False) -> Review:
    how = "Paid with receipt by" if receipt else "Paid by"
    return _review(SellRequest, req_id, SellRequest.Status.PAID, f"{how} {_reviewer(admin_tg_id, admin_name)}")


def reject_sell(req_id: int, admin_tg_id: int, admin_name: str = "") -> Review:
    """رد درخواست فروش و برگشت کامل سکه‌ها؛ برگشت و تغییر وضعیت در یک تراکنش."""
    return _review(
        SellRequest, req_id, SellRequest.Status.REJECTED, f"Rejected by {_reviewer(admin_tg_id, admin_name)}",
        refund_type=TxType.REFUND,
    )  # fmt: skip
