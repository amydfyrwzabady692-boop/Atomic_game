"""جوین اجباری (کانال‌هایی که کاربر برای استفاده از ربات باید عضوشان باشد) و کلیدهای API ربات‌های دیگر.

ربات‌های دیگر با کلید API می‌پرسند کاربری این ربات را استارت کرده یا عضو کانالی شده است (مثلاً وقتی استارت
این ربات را جوین اجباری خودشان گذاشته‌اند) و اگر وب‌هوک داده باشند، استارت، بلاک و عضویت کانال همان لحظه
برایشان فرستاده می‌شود.
"""

import secrets

from django.db import models


class ForcedChannel(models.Model):
    """کانال (یا گروه) جوین اجباری. ربات باید در کانال ادمین باشد تا عضویت کاربرها را بتواند بپرسد."""

    chat_id = models.BigIntegerField("شناسه‌ی چت", unique=True)
    title = models.CharField("عنوان", max_length=255, blank=True, default="")
    username = models.CharField("یوزرنیم", max_length=64, blank=True, default="", help_text="بدون @")
    invite_link = models.CharField(
        "لینک دعوت", max_length=255, blank=True, default="", help_text="برای کانال خصوصی (کانال عمومی لینک t.me دارد)"
    )
    is_active = models.BooleanField("فعال", default=True)
    position = models.PositiveIntegerField("ترتیب", default=0)
    added_by = models.BigIntegerField("افزوده‌ی مدیر", null=True, blank=True)
    created_at = models.DateTimeField("تاریخ افزودن", auto_now_add=True)

    class Meta:
        ordering = ("position", "pk")
        verbose_name = "کانال جوین اجباری"
        verbose_name_plural = "کانال‌های جوین اجباری"

    def __str__(self) -> str:
        return self.title or self.handle

    @property
    def handle(self) -> str:
        return f"@{self.username}" if self.username else str(self.chat_id)

    @property
    def link(self) -> str:
        return f"https://t.me/{self.username}" if self.username else self.invite_link


def new_key() -> str:
    return "wz_" + secrets.token_urlsafe(30)


class PartnerKey(models.Model):
    """کلید API یک ربات دیگر. کلید همان رمز امضای وب‌هوک‌هایش هم هست."""

    name = models.CharField("نام", max_length=64)
    key = models.CharField("کلید", max_length=64, unique=True, default=new_key)
    webhook_url = models.URLField("آدرس وب‌هوک", max_length=500, blank=True, default="")
    is_active = models.BooleanField("فعال", default=True)
    created_by = models.BigIntegerField("سازنده", null=True, blank=True)
    created_at = models.DateTimeField("تاریخ ساخت", auto_now_add=True)
    last_used_at = models.DateTimeField("آخرین استفاده", null=True, blank=True)

    class Meta:
        ordering = ("pk",)
        verbose_name = "کلید API ربات دیگر"
        verbose_name_plural = "کلیدهای API ربات‌های دیگر"

    def __str__(self) -> str:
        return self.name
