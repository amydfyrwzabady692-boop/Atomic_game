"""منابع سکه‌ی مجازی: هدیه‌ی ثبت‌نام، جایزه‌ی روزانه، سکه‌ی نجات، دعوت دوست و هدیه‌ی ادمین.

مقدارها (و روشن/خاموش بودن هر کدام) از ``EconomySettings`` خوانده می‌شود که در پنل ادمین قابل تغییر است.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.models import TelegramUser

from .models import EconomySettings, TxType
from .services import apply_transaction


@dataclass
class DailyResult:
    claimed: bool
    amount: int = 0
    streak: int = 0
    rescue: int = 0
    next_at: object = None
    disabled: bool = False


def daily_amount(streak: int) -> int:
    return min(settings.DAILY_BASE + (max(streak, 1) - 1) * settings.DAILY_STEP, settings.DAILY_MAX)


@dataclass
class ReferralResult:
    """نتیجه‌ی ثبت یک دعوت موفق: ``reward`` صفر یعنی هنوز به تعداد لازم نرسیده."""

    referrer: TelegramUser
    count: int  # تعداد کل دعوت‌های موفق دعوت‌کننده
    every: int  # هر چند دعوت یک جایزه
    reward: int  # سکه‌ای که همین الان پرداخت شد (۰ = هنوز نه)
    next_reward: int  # جایزه‌ی هر دسته طبق تنظیمات فعلی


def get_settings() -> EconomySettings:
    return EconomySettings.load()


def grant_signup_bonus(user: TelegramUser):
    """هدیه‌ی ثبت‌نام؛ اگر در تنظیمات صفر باشد ``None`` برمی‌گرداند."""
    amount = get_settings().signup_bonus
    if amount <= 0:
        return None
    return apply_transaction(user, amount, TxType.SIGNUP_BONUS, f"signup:{user.pk}")


def _next_midnight(now):
    local = timezone.localtime(now)
    return (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def claim_daily(user: TelegramUser, now=None) -> DailyResult:
    """جایزه‌ی روزانه با streak. روز بر اساس ساعت تهران حساب می‌شود. اگر در تنظیمات خاموش باشد هیچ کاری نمی‌کند."""
    now = now or timezone.now()
    if not get_settings().daily_enabled:
        return DailyResult(False, disabled=True)
    today = timezone.localtime(now).date()
    with transaction.atomic():
        locked = TelegramUser.objects.select_for_update().get(pk=user.pk)
        last = timezone.localtime(locked.last_daily_at).date() if locked.last_daily_at else None
        if last == today:
            result = DailyResult(False, streak=locked.daily_streak, next_at=_next_midnight(now))
        else:
            streak = locked.daily_streak + 1 if last == today - timedelta(days=1) else 1
            amount = daily_amount(streak)
            locked.daily_streak = streak
            locked.last_daily_at = now
            locked.save(update_fields=["daily_streak", "last_daily_at"])
            apply_transaction(locked, amount, TxType.DAILY, f"daily:{locked.pk}:{today.isoformat()}")
            result = DailyResult(True, amount=amount, streak=streak, next_at=_next_midnight(now))
    user.refresh_from_db()
    if not result.claimed:
        result.rescue = claim_rescue(user, now)
    return result


def claim_rescue(user: TelegramUser, now=None) -> int:
    """اگر موجودی صفر باشد روزی یک بار مقدار کمی سکه می‌دهد. مقدار داده‌شده را برمی‌گرداند."""
    now = now or timezone.now()
    today = timezone.localtime(now).date()
    if not get_settings().daily_enabled:
        return 0
    with transaction.atomic():
        locked = TelegramUser.objects.select_for_update().get(pk=user.pk)
        if locked.coins > 0:
            return 0
        last = timezone.localtime(locked.last_rescue_at).date() if locked.last_rescue_at else None
        if last == today:
            return 0
        locked.last_rescue_at = now
        locked.save(update_fields=["last_rescue_at"])
        apply_transaction(
            locked, settings.RESCUE_AMOUNT, TxType.RESCUE, f"rescue:{locked.pk}:{today.isoformat()}"
        )
    user.refresh_from_db()
    return settings.RESCUE_AMOUNT


def try_reward_referral(invitee: TelegramUser, now=None) -> ReferralResult | None:
    """دعوت وقتی «موفق» حساب می‌شود که دعوت‌شده حداقل یک بازی سکه‌ای کرده و حسابش قدیمی‌تر از حد باشد.

    هر ``referral_every`` دعوت موفق، ``referral_reward`` سکه به دعوت‌کننده می‌دهد (هر دو از پنل ادمین).
    کلید تراکنش شماره‌ی همان دسته است، پس هر دسته فقط یک بار پرداخت می‌شود. اگر دعوت تازه‌ای ثبت
    نشد ``None`` برمی‌گرداند.
    """
    now = now or timezone.now()
    with transaction.atomic():
        locked = TelegramUser.objects.select_for_update().get(pk=invitee.pk)
        if locked.referred_by_id is None or locked.referral_rewarded or locked.games_played < 1:
            return None
        if locked.is_banned:
            return None
        min_age = timedelta(hours=settings.REFERRAL_MIN_ACCOUNT_AGE_HOURS)
        if now - locked.created_at < min_age:
            return None
        # قفل دعوت‌کننده تا شمارش دعوت‌های موفقش با دعوت هم‌زمان دیگری قاطی نشود
        referrer = TelegramUser.objects.select_for_update().get(pk=locked.referred_by_id)
        locked.referral_rewarded = True
        locked.save(update_fields=["referral_rewarded"])
        config = get_settings()
        every = max(1, config.referral_every)
        count = TelegramUser.objects.filter(referred_by_id=referrer.pk, referral_rewarded=True).count()
        reward = 0
        if config.referral_reward > 0 and count % every == 0:
            reward = config.referral_reward
            apply_transaction(referrer, reward, TxType.REFERRAL, f"referral-batch:{referrer.pk}:{count // every}")
        referrer.refresh_from_db()
        return ReferralResult(referrer, count, every, reward, config.referral_reward)


def admin_grant(user: TelegramUser, amount: int, admin_tg_id: int, nonce: str):
    """اعطای سکه توسط سوپرادمین (جوایز کانال/مسابقه). مقدار منفی برای اصلاح هم مجاز است."""
    return apply_transaction(user, amount, TxType.ADMIN_GRANT, f"grant:{admin_tg_id}:{user.pk}:{nonce}")
