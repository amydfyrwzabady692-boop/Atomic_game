import re
import uuid

from django.contrib import admin, messages
from django.db import transaction
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from wallet.models import CoinTransaction, TxType
from wallet.services import apply_transaction

from .models import TelegramGroup, TelegramUser

admin.site.site_header = "مدیریت ربات بازی‌های گروهی"
admin.site.site_title = "ربات بازی"
admin.site.index_title = "پنل مدیریت"
admin.site.index_template = "admin/custom_index.html"

RECENT_TX_LIMIT = 30
MAX_GRANT = 1_000_000
_NONCE_RE = re.compile(r"^[0-9a-f]{32}$")


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ("tg_id", "first_name", "username", "coins", "level", "games_played", "wins", "is_banned", "created_at")
    list_display_links = ("tg_id", "first_name")
    list_per_page = 50
    # شمارش کامل جدول کاربران در هر بار باز کردن لیست کند است
    show_full_result_count = False
    list_filter = ("is_banned", "started_bot", "level")
    search_fields = ("tg_id", "username", "first_name")
    # موجودی فقط از مسیر ledger (wallet.services.apply_transaction) تغییر می‌کند؛ اعطای سکه با /grant در ربات
    readonly_fields = (
        "tg_id",
        "coins",
        "xp",
        "level",
        "games_played",
        "wins",
        "daily_streak",
        "last_daily_at",
        "last_rescue_at",
        "referred_by",
        "referral_rewarded",
        "created_at",
        "recent_transactions",
    )
    actions = ["grant_credit", "ban_users", "unban_users"]

    @admin.display(description=f"آخرین {RECENT_TX_LIMIT} تراکنش (فقط‌خواندنی)")
    def recent_transactions(self, obj):
        """به‌جای inline که همه‌ی تراکنش‌های کاربر را بار می‌کرد، فقط آخرین‌ها را نشان می‌دهد."""
        if obj is None or obj.pk is None:
            return "—"
        rows = list(
            CoinTransaction.objects.filter(user_id=obj.pk)
            .order_by("-id")
            .values_list("created_at", "type", "amount", "balance_after", "ref_match_id")[:RECENT_TX_LIMIT]
        )
        if not rows:
            return "هنوز تراکنشی ثبت نشده است."
        labels = dict(TxType.choices)
        body = format_html_join(
            "",
            '<tr><td dir="ltr">{}</td><td>{}</td><td dir="ltr" class="{}">{}</td><td dir="ltr">{}</td><td>{}</td></tr>',
            (
                (
                    created.strftime("%Y/%m/%d %H:%M"),
                    labels.get(kind, kind),
                    "tx-in" if amount > 0 else "tx-out",
                    f"{amount:+,}",
                    f"{after:,}",
                    match_id or "—",
                )
                for created, kind, amount, after, match_id in rows
            ),
        )
        all_url = reverse("admin:wallet_cointransaction_changelist") + f"?user__id__exact={obj.pk}"
        return format_html(
            '<table class="tx-table"><thead><tr><th>زمان</th><th>نوع</th><th>مقدار</th><th>موجودی بعد</th>'
            '<th>مسابقه</th></tr></thead><tbody>{}</tbody></table><p><a class="button" href="{}">همه‌ی تراکنش‌ها ←</a></p>',
            body,
            all_url,
        )

    @admin.action(description="🪙 شارژ اعتبار مجازی کاربران انتخاب‌شده")
    def grant_credit(self, request, queryset):
        """صفحه‌ی میانی: مقدار را می‌گیرد و از مسیر ledger به هر کاربر اعتبار مجازی می‌دهد.

        هر فرم یک ``nonce`` یکتا دارد که در کلید تراکنش می‌نشیند؛ پس ارسال دوباره‌ی همان فرم
        (دوبار کلیک، رفرش، دکمه‌ی back) دوباره شارژ نمی‌کند.
        """
        if request.POST.get("apply") == "1":
            raw = (request.POST.get("amount") or "").strip()
            nonce = (request.POST.get("nonce") or "").strip()
            if not raw.isdigit() or not 0 < int(raw) <= MAX_GRANT:
                self.message_user(request, "مقدار باید عددی بین ۱ تا ۱٬۰۰۰٬۰۰۰ باشد.", messages.ERROR)
            elif not _NONCE_RE.match(nonce):
                self.message_user(request, "فرم نامعتبر است؛ دوباره از لیست کاربران شروع کنید.", messages.ERROR)
                return None
            else:
                amount = int(raw)
                granted = skipped = 0
                with transaction.atomic():  # همه یا هیچ
                    for user in queryset.order_by("pk"):
                        tx = apply_transaction(user, amount, TxType.ADMIN_GRANT, f"admin-panel:{nonce}:{user.pk}")
                        if tx.duplicate:
                            skipped += 1
                        else:
                            granted += 1
                if granted:
                    self.message_user(request, f"به {granted} کاربر {amount:,} اعتبار مجازی داده شد.")
                if skipped:
                    self.message_user(
                        request, f"{skipped} مورد قبلاً با همین فرم شارژ شده بود و تکرار نشد.", messages.WARNING
                    )
                return None
        users = list(queryset.order_by("pk")[:31])
        return TemplateResponse(
            request,
            "admin/core/grant_credit.html",
            {
                **self.admin_site.each_context(request),
                "title": "شارژ اعتبار مجازی",
                "users": users[:30],
                "more": len(users) > 30,
                "count": queryset.count(),
                "selected_ids": list(queryset.values_list("pk", flat=True)),
                "nonce": uuid.uuid4().hex,
                "max_grant": MAX_GRANT,
                "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
                "opts": self.model._meta,
            },
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="🚫 مسدود کردن کاربران انتخاب‌شده")
    def ban_users(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_banned=True)} کاربر مسدود شد.")

    @admin.action(description="✅ رفع مسدودی کاربران انتخاب‌شده")
    def unban_users(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_banned=False)} کاربر آزاد شد.")


@admin.register(TelegramGroup)
class TelegramGroupAdmin(admin.ModelAdmin):
    list_display = (
        "title", "chat_id", "is_active", "min_entry", "max_entry", "allow_user_created_games", "prize_note", "created_at",
    )  # fmt: skip
    list_filter = ("is_active", "allow_user_created_games")
    search_fields = ("title", "chat_id")
    readonly_fields = ("chat_id", "created_at")
