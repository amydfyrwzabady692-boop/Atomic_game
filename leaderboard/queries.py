"""رتبه‌بندی‌ها و آمار پروفایل. جدول «امروز» و «هفته» از روی تاریخ محاسبه می‌شوند
(منطقه‌ی زمانی تهران، شروع هفته شنبه)، پس «ریست هفتگی» خودکار است."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone

from core.models import TelegramGroup, TelegramUser
from games.models import MatchPlayer, MatchStatus
from shop.services import decorations

from .models import WeeklyChampion


@dataclass
class TopRow:
    rank: int
    user: TelegramUser
    coins: int
    wins: int
    games: int
    badge: str = ""
    title: str = ""


def day_start(now=None) -> datetime:
    local = timezone.localtime(now or timezone.now())
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def week_start(now=None) -> datetime:
    start = day_start(now)
    return start - timedelta(days=(start.weekday() - 5) % 7)  # شنبه


def period_range(period: str, now=None) -> tuple[datetime | None, datetime | None]:
    if period == "day":
        return day_start(now), None
    if period == "week":
        return week_start(now), None
    return None, None


def top_players(
    group_id: int | None = None, period: str = "all", limit: int = 10, since=None, until=None
) -> list[TopRow]:
    """بر اساس سکه‌ی برده‌شده و سپس تعداد برد."""
    if since is None and until is None:
        since, until = period_range(period)
    # بازی‌های رایگان امتیازی ندارند و در رتبه‌بندی حساب نمی‌شوند
    qs = MatchPlayer.objects.filter(match__status=MatchStatus.FINISHED, match__entry_fee__gt=0)
    if group_id is not None:
        qs = qs.filter(match__group_id=group_id)
    if since is not None:
        qs = qs.filter(match__finished_at__gte=since)
    if until is not None:
        qs = qs.filter(match__finished_at__lt=until)
    rows = list(
        qs.values("user_id")
        .annotate(coins=Sum("prize"), wins=Count("id", filter=Q(rank=1)), games=Count("id"))
        .order_by("-coins", "-wins", "user_id")[:limit]
    )
    users = TelegramUser.objects.in_bulk([r["user_id"] for r in rows])
    decor = decorations(list(users))
    result = []
    for i, row in enumerate(rows, start=1):
        d = decor.get(row["user_id"], {})
        result.append(
            TopRow(
                i,
                users[row["user_id"]],
                int(row["coins"] or 0),
                row["wins"],
                row["games"],
                badge=d.get("emoji", ""),
                title=d.get("title", ""),
            )
        )
    return result


def profile_stats(user: TelegramUser) -> dict:
    best = (
        MatchPlayer.objects.filter(user=user, rank=1, match__status=MatchStatus.FINISHED, match__entry_fee__gt=0)
        .values("match__game_type")
        .annotate(n=Count("id"))
        .order_by("-n")
        .first()
    )
    badges = list(user.achievements.select_related("achievement").values_list("achievement__emoji", flat=True))
    records = list(user.arcade_records.filter(best_score__gt=0).values_list("game_key", "best_score"))
    return {
        "best_game": best["match__game_type"] if best else None,
        "badges": badges,
        "records": records,
        "decor": decorations([user.pk]).get(user.pk, {}),
    }


def announce_weekly_champions(now=None) -> list[tuple[TelegramGroup, TopRow]]:
    """قهرمان هفته‌ی گذشته‌ی هر گروه فعال را ثبت می‌کند و فقط موارد تازه را برمی‌گرداند."""
    this_week = week_start(now)
    last_week = this_week - timedelta(days=7)
    result = []
    for group in TelegramGroup.objects.filter(is_active=True):
        if WeeklyChampion.objects.filter(group=group, week_start=last_week.date()).exists():
            continue
        top = top_players(group.pk, limit=1, since=last_week, until=this_week)
        champion = top[0] if top and (top[0].coins > 0 or top[0].wins > 0) else None
        _, created = WeeklyChampion.objects.get_or_create(
            group=group,
            week_start=last_week.date(),
            defaults={
                "user": champion.user if champion else None,
                "coins_won": champion.coins if champion else 0,
                "wins": champion.wins if champion else 0,
            },
        )
        if created and champion:
            result.append((group, champion))
    return result
