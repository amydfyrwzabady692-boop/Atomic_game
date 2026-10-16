from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse

from core.admin_utils import ReadOnlyAdmin

from .models import CoinTransaction, EconomySettings


@admin.register(CoinTransaction)
class CoinTransactionAdmin(ReadOnlyAdmin):
    """دفتر کل سکه: فقط‌خواندنی، بدون حذف و ویرایش."""

    list_display = ("id", "created_at", "user", "type", "amount", "balance_after", "ref_match")
    list_filter = ("type", "created_at")
    search_fields = ("user__tg_id", "user__username", "idempotency_key")
    list_select_related = ("user", "ref_match")
    date_hierarchy = "created_at"
    list_per_page = 100
    # ledger بزرگ می‌شود؛ شمارش کامل جدول در هر بار باز کردن لیست کند است
    show_full_result_count = False


@admin.register(EconomySettings)
class EconomySettingsAdmin(admin.ModelAdmin):
    """فقط یک ردیف؛ باز کردن لیست مستقیم به فرم ویرایش همان ردیف می‌رود."""

    fieldsets = (
        ("ورود و جایزه‌ی روزانه", {"fields": ("signup_bonus", "daily_enabled")}),
        ("دعوت دوستان", {"fields": ("referral_every", "referral_reward")}),
    )
    readonly_fields = ("updated_at",)

    def changelist_view(self, request, extra_context=None):
        obj = EconomySettings.load()
        return redirect(reverse("admin:wallet_economysettings_change", args=[obj.pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
