from django.contrib import admin

from core.admin_utils import ReadOnlyAdmin

from .models import CoinTransaction


@admin.register(CoinTransaction)
class CoinTransactionAdmin(ReadOnlyAdmin):
    """دفتر کل سکه: فقط‌خواندنی، بدون حذف و ویرایش."""

    list_display = ("id", "created_at", "user", "type", "amount", "balance_after", "ref_match")
    list_filter = ("type", "created_at")
    search_fields = ("user__tg_id", "user__username", "idempotency_key")
    list_select_related = ("user", "ref_match")
    date_hierarchy = "created_at"
