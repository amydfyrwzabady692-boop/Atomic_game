"""ذخیره و به‌روزرسانی وضعیت بازی‌های دونفره‌ی گرافیکی (شطرنج) در ``Match.state["board"]``.

همه‌ی تغییرها زیر قفل ردیفی مسابقه انجام می‌شوند، چون هم سرویس وب (حرکت بازیکن‌ها) و هم ربات
(پایان مهلت حرکت و اعلام نتیجه) همین وضعیت را می‌خوانند و می‌نویسند.
"""

import time

from django.db import transaction

from games import gridlive
from games.chess import live
from games.models import Match

LIVE_GAMES = ("chess", "tictactoe", "connect4")


def rules_for(state: dict):
    """ماژول قوانین بازیِ این وضعیت (شطرنج یا بازی‌های خانه‌ای)."""
    return live if state.get("game", "chess") == "chess" else gridlive


def new_state(game: str, first_id: int, second_id: int, now: float) -> dict:
    if game == "chess":
        return live.new_state(first_id, second_id, now)
    return gridlive.new_state(game, first_id, second_id, now)


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
