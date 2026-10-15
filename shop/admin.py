from django.contrib import admin

from core.admin_utils import ReadOnlyAdmin

from .models import ShopItem, StarsPurchase, UserItem


@admin.register(ShopItem)
class ShopItemAdmin(admin.ModelAdmin):
    """آیتم‌ها فقط ظاهری‌اند و فقط با سکه‌ی مجازی خریده می‌شوند."""

    list_display = ("name", "kind", "value", "price", "is_active", "sort_order")
    list_filter = ("kind", "is_active")
    list_editable = ("price", "is_active", "sort_order")


@admin.register(UserItem)
class UserItemAdmin(ReadOnlyAdmin):
    list_display = ("user", "item", "equipped", "created_at")
    list_filter = ("item__kind", "equipped")
    search_fields = ("user__tg_id", "user__username")


@admin.register(StarsPurchase)
class StarsPurchaseAdmin(ReadOnlyAdmin):
    list_display = ("user", "item", "stars", "charge_id", "created_at")
    search_fields = ("charge_id", "user__tg_id", "user__username")
