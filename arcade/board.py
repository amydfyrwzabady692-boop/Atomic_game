"""ذخیره و به‌روزرسانی وضعیت بازی‌های دونفره‌ی گرافیکی (شطرنج) در ``Match.state["board"]``.

همه‌ی تغییرها زیر قفل ردیفی مسابقه انجام می‌شوند، چون هم سرویس وب (حرکت بازیکن‌ها) و هم ربات
(پایان مهلت حرکت و اعلام نتیجه) همین وضعیت را می‌خوانند و می‌نویسند.
"""

import time

from django.db import transaction

from games import gridlive
from games.chess import live
from games.models import Match
from games.poker import live as poker

LIVE_GAMES = ("chess", "tictactoe", "connect4", "poker")


def rules_for(state: dict):
    """ماژول قوانین بازیِ این وضعیت (شطرنج، پوکر یا بازی‌های خانه‌ای)."""
    game = state.get("game", "chess")
    if game == "chess":
        return live
    if game == "poker":
        return poker
    return gridlive


def new_state(game: str, user_ids: list[int], now: float, seed: str = "", options: dict | None = None) -> dict:
    """وضعیت تازه؛ ``user_ids`` به ترتیب نشستن (شطرنج: سفید، سیاه). پوکر ۲ تا ۸ نفر می‌گیرد.
    کنترل زمانی شطرنج همان گزینه‌ای است که سازنده‌ی مسابقه انتخاب کرده (``options["variant"]``)."""
    if game == "chess":
        control = (options or {}).get("variant") or live.DEFAULT_CONTROL
        return live.new_state(user_ids[0], user_ids[1], now, control=control)
    if game == "poker":
        return poker.new_state(list(user_ids), now, seed=seed)
    return gridlive.new_state(game, user_ids[0], user_ids[1], now)


def standings(state: dict) -> list[tuple[int, int]]:
    """(کاربر، امتیاز) برای تقسیم جایزه: پوکر بر اساس ژتون، بقیه برنده ۱ و بازنده ۰."""
    rules = rules_for(state)
    if hasattr(rules, "standings"):
        return rules.standings(state)
    winner = (state.get("over") or {}).get("winner")
    return [(uid, 1 if uid == winner else 0) for uid in rules.players(state).values()]


def live_match(token: str) -> Match | None:
    """مسابقه‌ای با این توکن که صفحه‌ی گرافیکی دارد (یا ``None``)."""
    match = Match.objects.filter(token=token, game_type__in=LIVE_GAMES).first()
    return match if match is not None and (match.state or {}).get("board") else None


def start(match_id: int, state: dict) -> None:
    with transaction.atomic():
        match = Match.objects.select_for_update().get(pk=match_id)
        match.state = {**(match.state or {}), "board": state}
        match.save(update_fields=["state"])


def remember(match_id: int, **values) -> None:
    """مقدارهای کناری (مثل شناسه‌ی پیام گروه) را کنار وضعیت بازی نگه می‌دارد."""
    with transaction.atomic():
        match = Match.objects.select_for_update().get(pk=match_id)
        match.state = {**(match.state or {}), **values}
        match.save(update_fields=["state"])


def update(match_id: int, change):
    """``change(state)`` را زیر قفل اجرا می‌کند و اگر نسخه عوض شد ذخیره می‌کند.

    اگر ``change`` خطای ``LiveError`` بدهد ولی وضعیت را عوض کرده باشد (مثلاً مهلت حرکت تمام شده و
    بازی به سود حریف بسته شده)، همان تغییر ذخیره می‌شود و خطا بالا می‌رود.
    """
    with transaction.atomic():
        match = Match.objects.select_for_update().get(pk=match_id)
        state = (match.state or {}).get("board")
        if state is None:
            raise live.LiveError("match_not_found")
        before = state["version"]
        error = None
        result = None
        try:
            result = change(state)
        except live.LiveError as exc:
            error = exc
        if state["version"] != before:
            match.state = {**match.state, "board": state}
            match.save(update_fields=["state"])
    if error is not None:
        raise error
    return match, state, result


def tick(match_id: int, now: float | None = None) -> dict | None:
    """برای ربات: مهلت حرکت را بررسی می‌کند و وضعیت فعلی را برمی‌گرداند."""
    now = time.time() if now is None else now
    match = Match.objects.filter(pk=match_id).first()
    state = (match.state or {}).get("board") if match else None
    if state is None:
        return None
    if not state["over"] and state["deadline"] is not None and now > state["deadline"]:
        _, state, _ = update(match_id, lambda s: rules_for(s).check_timeout(s, now))
    return state
