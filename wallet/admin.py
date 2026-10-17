from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from core.admin_utils import ReadOnlyAdmin

from .models import CoinTransaction, EconomySettings, SellRequest, TopUpRequest
from .services import apply_transaction


@admin.register(CoinTransaction)
class CoinTransactionAdmin(ReadOnlyAdmin):
    """دفتر کل سکه: فقط‌خواندنی، بدون حذف و ویرایش."""

    list_display = ("id", "created_at", "user", "type", "amount", "balance_after", "ref_match")
    list_filter = ("type", "created_at")
    search_fields = ("user__tg_id", "user__username", "idempotency_key")
    list_select_related = ("user", "ref_match")
    date_hierarchy = "created_at"
    list_per_page = 100
    show_full_result_count = False


@admin.register(EconomySettings)
class EconomySettingsAdmin(admin.ModelAdmin):
    """فقط یک ردیف؛ باز کردن لیست مستقیم به فرم ویرایش همان ردیف می‌رود."""

    fieldsets = (
        ("شارژ و فروش سکه", {"fields": ("coin_price_toman", "topup_fee_percent", "card_number", "card_holder", "min_sell_coins", "coin_sell_price_toman")}),
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


@admin.register(TopUpRequest)
class TopUpRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "user", "coins", "amount_toman", "fee_toman", "total_toman", "status")
    list_filter = ("status", "created_at")
    search_fields = ("user__tg_id", "user__username", "user__first_name")
    list_select_related = ("user",)
    readonly_fields = ("created_at", "reviewed_at")
    actions = ["approve_topup", "reject_topup"]

    @admin.action(description="تایید درخواست‌های انتخاب‌شده و شارژ سکه")
    def approve_topup(self, request, queryset):
        for req in queryset.filter(status=TopUpRequest.Status.PENDING):
            apply_transaction(req.user, req.coins, "TOPUP", f"topup:{req.pk}")
            req.status = TopUpRequest.Status.APPROVED
            req.reviewed_at = timezone.now()
            req.save(update_fields=["status", "reviewed_at"])

    @admin.action(description="رد درخواست‌های انتخاب‌شده")
    def reject_topup(self, request, queryset):
        queryset.filter(status=TopUpRequest.Status.PENDING).update(
            status=TopUpRequest.Status.REJECTED, reviewed_at=timezone.now()
        )


@admin.register(SellRequest)
class SellRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "user", "coins", "amount_toman", "card_number", "card_holder", "status")
    list_filter = ("status", "created_at")
    search_fields = ("user__tg_id", "user__username", "card_number", "card_holder")
    list_select_related = ("user",)
    readonly_fields = ("created_at", "reviewed_at")
    actions = ["mark_paid", "reject_and_refund"]

    @admin.action(description="ثبت به عنوان واریزشده")
    def mark_paid(self, request, queryset):
        queryset.filter(status=SellRequest.Status.PENDING).update(
            status=SellRequest.Status.PAID, reviewed_at=timezone.now()
        )

    @admin.action(description="رد درخواست و برگشت سکه به کاربر")
    def reject_and_refund(self, request, queryset):
        for req in queryset.filter(status=SellRequest.Status.PENDING):
            apply_transaction(req.user, req.coins, "REFUND", f"sell_refund:{req.pk}")
            req.status = SellRequest.Status.REJECTED
            req.reviewed_at = timezone.now()
            req.save(update_fields=["status", "reviewed_at"])
