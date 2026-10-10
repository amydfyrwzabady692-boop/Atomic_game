from django.contrib import admin

from core.admin_utils import ReadOnlyAdmin

from .models import Achievement, UserAchievement, WeeklyChampion


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ("emoji", "title", "code", "reward_coins")
    readonly_fields = ("code",)


@admin.register(UserAchievement)
class UserAchievementAdmin(ReadOnlyAdmin):
    list_display = ("user", "achievement", "created_at")
    list_filter = ("achievement",)
    search_fields = ("user__tg_id", "user__username")


@admin.register(WeeklyChampion)
class WeeklyChampionAdmin(ReadOnlyAdmin):
    list_display = ("group", "week_start", "user", "coins_won", "wins")
    list_filter = ("week_start",)
