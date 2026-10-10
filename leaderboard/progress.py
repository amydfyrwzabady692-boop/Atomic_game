"""سطح، XP و دستاوردها."""

from django.db import transaction

from core.models import TelegramUser
from wallet.models import TxType
from wallet.services import apply_transaction

from .models import Achievement, UserAchievement

# code: (emoji, title, description, reward_coins)
ACHIEVEMENTS: dict[str, tuple[str, str, str, int]] = {
    "first_game": ("🎈", "اولین بازی", "اولین مسابقه‌ات را تمام کردی", 50),
    "first_win": ("🥇", "اولین برد", "اولین بار نفر اول شدی", 100),
    "wins_10": ("🔥", "۱۰ برد", "ده بار نفر اول شدی", 300),
    "wins_50": ("👑", "۵۰ برد", "پنجاه بار نفر اول شدی", 1500),
    "games_25": ("🎮", "بازیکن پرکار", "در ۲۵ مسابقه شرکت کردی", 200),
    "games_100": ("🕹", "معتاد بازی", "در ۱۰۰ مسابقه شرکت کردی", 800),
    "streak_7": ("📅", "۷ روز پیاپی", "هفت روز پشت‌سرهم جایزه‌ی روزانه گرفتی", 300),
    "streak_30": ("🗓", "۳۰ روز پیاپی", "سی روز پشت‌سرهم جایزه‌ی روزانه گرفتی", 1500),
    "quiz_freefire": ("🔫", "قهرمان کوییز فری فایر", "در کوییز فری فایر نفر اول شدی", 200),
    "arcade_first": ("👾", "آرکیدباز", "اولین مسابقه‌ی آرکید را بردی", 150),
    "level_10": ("⭐", "سطح ۱۰", "به سطح ۱۰ رسیدی", 500),
}


def xp_for_level(level: int) -> int:
    """XP کل لازم برای رسیدن به ``level``. تصاعدی: ۰، ۱۰۰، ۳۰۰، ۶۰۰، ۱۰۰۰، …"""
    return 50 * level * (level - 1)


def level_for_xp(xp: int) -> int:
    level = 1
    while xp_for_level(level + 1) <= xp:
        level += 1
    return level


def award(user: TelegramUser, code: str) -> Achievement | None:
    """دستاورد را (اگر قبلاً نگرفته) ثبت می‌کند و جایزه‌ی سکه‌اش را می‌دهد."""
    emoji, title, description, reward = ACHIEVEMENTS[code]
    with transaction.atomic():
        achievement, _ = Achievement.objects.get_or_create(
            code=code,
            defaults={"emoji": emoji, "title": title, "description": description, "reward_coins": reward},
        )
        _, created = UserAchievement.objects.get_or_create(user=user, achievement=achievement)
        if not created:
            return None
        if achievement.reward_coins:
            apply_transaction(user, achievement.reward_coins, TxType.ACHIEVEMENT, f"ach:{user.pk}:{code}")
    return achievement


def check_progress_achievements(user: TelegramUser) -> list[Achievement]:
    """دستاوردهای وابسته به آمار کلی کاربر (تعداد بازی، برد، streak، سطح)."""
    wanted = []
    if user.games_played >= 1:
        wanted.append("first_game")
    if user.games_played >= 25:
        wanted.append("games_25")
    if user.games_played >= 100:
        wanted.append("games_100")
    if user.wins >= 1:
        wanted.append("first_win")
    if user.wins >= 10:
        wanted.append("wins_10")
    if user.wins >= 50:
        wanted.append("wins_50")
    if user.daily_streak >= 7:
        wanted.append("streak_7")
    if user.daily_streak >= 30:
        wanted.append("streak_30")
    if user.level >= 10:
        wanted.append("level_10")
    if not wanted:
        return []
    have = set(
        UserAchievement.objects.filter(user=user, achievement__code__in=wanted).values_list(
            "achievement__code", flat=True
        )
    )
    return [a for code in wanted if code not in have and (a := award(user, code))]
