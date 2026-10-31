from django.contrib import admin

from .models import ForcedChannel, PartnerKey


@admin.register(ForcedChannel)
class ForcedChannelAdmin(admin.ModelAdmin):
    list_display = ("title", "handle", "chat_id", "is_active", "position", "created_at")
    list_editable = ("is_active", "position")
    search_fields = ("title", "username", "chat_id")


@admin.register(PartnerKey)
class PartnerKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "webhook_url", "last_used_at", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = ("key", "created_at", "last_used_at")
