from django.contrib import admin

from core.admin_utils import ReadOnlyAdmin

from .models import ArcadeRecord, ArcadeSession


@admin.register(ArcadeSession)
class ArcadeSessionAdmin(ReadOnlyAdmin):
    """تلاش‌های آرکید. جلسه‌های مشکوک با فیلتر «مشکوک» پیدا می‌شوند."""

    list_display = (
        "started_at",
        "user",
        "game_key",
        "match",
        "status",
        "flagged",
        "reject_reason",
        "claimed_score",
        "verified_score",
        "duration_ms",
    )
    list_filter = ("flagged", "status", "game_key", "reject_reason")
    search_fields = ("user__tg_id", "user__username", "id")
    list_select_related = ("user", "match")
    date_hierarchy = "started_at"


@admin.register(ArcadeRecord)
class ArcadeRecordAdmin(ReadOnlyAdmin):
    list_display = ("user", "game_key", "best_score", "level_reached", "updated_at")
    list_filter = ("game_key",)
    search_fields = ("user__tg_id", "user__username")
