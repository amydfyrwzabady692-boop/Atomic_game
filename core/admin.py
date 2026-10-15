from django.contrib import admin

from wallet.models import CoinTransaction

from .models import TelegramGroup, TelegramUser

admin.site.site_header = "مدیریت ربات بازی‌های گروهی"
admin.site.site_title = "ربات بازی"
admin.site.index_title = "پنل مدیریت"
admin.site.index_template = "admin/custom_index.html"


class TransactionInline(admin.TabularInline):
    model = CoinTransaction
    fields = ("created_at", "type", "amount", "balance_after", "ref_match")
    readonly_fields = fields
    extra = 0
    max_num = 0
    can_delete = False
    ordering = ("-id",)
    verbose_name_plural = "تراکنش‌های سکه (فقط‌خواندنی)"

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ("tg_id", "first_name", "username", "coins", "level", "games_played", "wins", "is_banned", "created_at")
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
    )
    inlines = [TransactionInline]
    actions = ["grant_credit", "ban_users", "unban_users"]

    @admin.action(description="شارژ اعتبار مجازی کاربران انتخاب‌شده")
    def grant_credit(self, request, queryset):
        """صفحه‌ی میانی: مقدار را می‌گیرد و از مسیر ledger به هر کاربر اعتبار مجازی می‌دهد."""
        import uuid

        from django.contrib import messages
        from django.template.response import TemplateResponse

        from wallet.models import TxType
        from wallet.services import apply_transaction

        if request.POST.get("apply") == "1":
            raw = (request.POST.get("amount") or "").strip()
            if not raw.isdigit() or not 0 < int(raw) <= 1_000_000:
                self.message_user(request, "مقدار باید عددی بین ۱ تا ۱٬۰۰۰٬۰۰۰ باشد.", messages.ERROR)
            else:
                batch = uuid.uuid4().hex[:12]
                for user in queryset:
                    apply_transaction(user, int(raw), TxType.ADMIN_GRANT, f"admin-panel:{batch}:{user.pk}")
                self.message_user(request, f"به {queryset.count()} کاربر {raw} اعتبار مجازی داده شد.")
                return None
        return TemplateResponse(
            request,
            "admin/core/grant_credit.html",
            {
                **self.admin_site.each_context(request),
                "title": "شارژ اعتبار مجازی",
                "users": queryset,
                "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
                "opts": self.model._meta,
            },
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="مسدود کردن کاربران انتخاب‌شده")
    def ban_users(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_banned=True)} کاربر مسدود شد.")

    @admin.action(description="رفع مسدودی کاربران انتخاب‌شده")
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
