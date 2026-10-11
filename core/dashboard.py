"""داشبورد آمار پنل ادمین."""

from datetime import timedelta

from django.contrib import admin
from django.db.models import Count, Q, Sum
from django.shortcuts import render

from arcade.models import ArcadeSession
from games.catalog import catalog
from games.models import Match, MatchPlayer, MatchStatus
from leaderboard.queries import day_start

from .models import TelegramGroup, TelegramUser
from .textutils import fa_num


def collect_stats(now=None) -> dict:
    today = day_start(now)
    games = catalog(include_disabled=True)

    daily = []
    for offset in range(13, -1, -1):
        start = today - timedelta(days=offset)
        end = start + timedelta(days=1)
        users = MatchPlayer.objects.filter(joined_at__gte=start, joined_at__lt=end).values("user_id").distinct().count()
        matches = Match.objects.filter(created_at__gte=start, created_at__lt=end).count()
        daily.append({"day": start, "users": users, "matches": matches})
    peak = max((row["users"] for row in daily), default=0) or 1
    for row in daily:
        row["percent"] = round(row["users"] * 100 / peak)

    by_game = list(
        Match.objects.values("game_type")
        .annotate(
            finished=Count("id", filter=Q(status=MatchStatus.FINISHED)),
            cancelled=Count("id", filter=Q(status=MatchStatus.CANCELLED)),
        )
        .order_by("-finished")
    )
    top = max((row["finished"] for row in by_game), default=0) or 1
    for row in by_game:
        info = games.get(row["game_type"])
        row["title"] = f"{info.emoji} {info.title_fa}" if info else row["game_type"]
        row["percent"] = round(row["finished"] * 100 / top)

    week_ago = today - timedelta(days=6)
    groups = list(
        TelegramGroup.objects.filter(matches__created_at__gte=week_ago)
        .annotate(n=Count("matches"))
        .order_by("-n")[:10]
        .values("title", "chat_id", "n")
    )
    return {
        "daily": daily,
        "by_game": by_game,
        "groups": [
            {"title": g["title"] or g["chat_id"], "matches": g["n"], "percent": round(g["n"] * 100 / (groups[0]["n"] or 1))}
            for g in groups
        ],
        "totals": {
            "users": fa_num(TelegramUser.objects.count()),
            "dau": fa_num(daily[-1]["users"]),
            "groups": fa_num(
                TelegramGroup.objects.filter(matches__created_at__gte=week_ago).distinct().count()
            ),
            "matches": fa_num(Match.objects.filter(status=MatchStatus.FINISHED).count()),
            "popular": by_game[0]["title"] if by_game and by_game[0]["finished"] else "—",
            "coins": fa_num(TelegramUser.objects.aggregate(s=Sum("coins"))["s"] or 0),
            "flagged": fa_num(ArcadeSession.objects.filter(flagged=True).count()),
        },
    }


def dashboard(request):
    context = {**admin.site.each_context(request), "title": "داشبورد آمار", **collect_stats()}
    return render(request, "admin/dashboard.html", context)
