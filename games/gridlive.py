"""دوز و دوز چهارتایی زنده برای صفحه‌ی گرافیکی مینی‌اپ.

مثل ``games.chess.live``: وضعیت یک dict قابل‌ذخیره در JSON است، همه‌ی حرکت‌ها همین‌جا اعتبارسنجی
می‌شوند و این ماژول وابستگی به جنگو یا تلگرام ندارد. خانه‌ها با ``ردیف × تعداد ستون + ستون``
شماره می‌خورند؛ در دوز چهارتایی ردیف ۰ پایین صفحه است و مهره به پایین‌ترین خانه‌ی خالی ستون می‌افتد.
"""

from games.chess.live import LiveError

GAMES = {
    "tictactoe": {"cols": 3, "rows": 3, "need": 3, "sides": ("X", "O"), "gravity": False, "seconds": 30},
    "connect4": {"cols": 7, "rows": 6, "need": 4, "sides": ("R", "Y"), "gravity": True, "seconds": 30},
}
DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))


def new_state(game: str, first_id: int, second_id: int, now: float) -> dict:
    spec = GAMES[game]
    first, second = spec["sides"]
    return {
        "game": game,
        "sides": {first: first_id, second: second_id},
        "cells": [""] * (spec["cols"] * spec["rows"]),
        "turn": first,
        "last": None,
        "win": [],
        "deadline": now + spec["seconds"],
        "move_seconds": spec["seconds"],
        "draw_offer": None,
        "over": None,
        "version": 1,
    }


def players(state: dict) -> dict:
    return dict(state["sides"])


def side_of(state: dict, user_id: int) -> str | None:
    return next((side for side, uid in state["sides"].items() if uid == user_id), None)


def other(state: dict, side: str) -> str:
    return next(s for s in state["sides"] if s != side)


def winning_cells(state: dict, last: int) -> list[int]:
    """خانه‌های خط برنده‌ای که از خانه‌ی ``last`` می‌گذرد (یا لیست خالی)."""
    spec = GAMES[state["game"]]
    cols, rows, cells = spec["cols"], spec["rows"], state["cells"]
    mark = cells[last]
    row, column = divmod(last, cols)
    for d_row, d_column in DIRECTIONS:
        line = [last]
        for sign in (1, -1):
            r, c = row + d_row * sign, column + d_column * sign
            while 0 <= r < rows and 0 <= c < cols and cells[r * cols + c] == mark:
                line.append(r * cols + c)
                r, c = r + d_row * sign, c + d_column * sign
        if len(line) >= spec["need"]:
            return sorted(line)
    return []


def _finish(state: dict, reason: str, winner_side: str | None = None) -> None:
    state["over"] = {
        "reason": reason,
        "side": winner_side,
        "winner": state["sides"][winner_side] if winner_side else None,
    }
    state["deadline"] = None
    state["version"] += 1


def check_timeout(state: dict, now: float) -> bool:
    if state["over"] or state["deadline"] is None or now <= state["deadline"]:
        return False
    _finish(state, "timeout", other(state, state["turn"]))
    return True


def legal(state: dict) -> list[int]:
    """حرکت‌های ممکن: شماره‌ی خانه در دوز، شماره‌ی ستون در دوز چهارتایی."""
    spec = GAMES[state["game"]]
    cells = state["cells"]
    if spec["gravity"]:
        top = (spec["rows"] - 1) * spec["cols"]
        return [column for column in range(spec["cols"]) if not cells[top + column]]
    return [index for index, mark in enumerate(cells) if not mark]


def apply_move(state: dict, user_id: int, src: int, dst: int, promo: str, now: float) -> int:
    """``src`` شماره‌ی خانه (دوز) یا ستون (دوز چهارتایی) است؛ ``dst`` و ``promo`` استفاده نمی‌شوند."""
    if check_timeout(state, now) or state["over"]:
        raise LiveError("game_over")
    side = side_of(state, user_id)
    if side is None:
        raise LiveError("not_a_player")
    if side != state["turn"]:
        raise LiveError("not_your_turn")
    if src not in legal(state):
        raise LiveError("illegal_move")
    spec = GAMES[state["game"]]
    cells = state["cells"]
    index = src
    if spec["gravity"]:
        index = next(r * spec["cols"] + src for r in range(spec["rows"]) if not cells[r * spec["cols"] + src])
    cells[index] = side
    state["last"] = index
    state["deadline"] = now + state["move_seconds"]
    state["version"] += 1
    state["win"] = winning_cells(state, index)
    if state["win"]:
        _finish(state, "line", side)
    elif all(cells):
        _finish(state, "full")
    else:
        state["turn"] = other(state, side)
    return index


def resign(state: dict, user_id: int) -> None:
    side = side_of(state, user_id)
    if side is None:
        raise LiveError("not_a_player")
    if state["over"]:
        raise LiveError("game_over")
    _finish(state, "resign", other(state, side))


def offer_draw(state: dict, user_id: int) -> bool:
    raise LiveError("bad_action")  # این بازی‌ها پیشنهاد مساوی ندارند


def view(state: dict, viewer_id: int | None, now: float) -> dict:
    spec = GAMES[state["game"]]
    side = side_of(state, viewer_id) if viewer_id is not None else None
    return {
        "game": state["game"],
        "cols": spec["cols"],
        "rows": spec["rows"],
        "gravity": spec["gravity"],
        "sides": list(spec["sides"]),
        "cells": state["cells"],
        "turn": state["turn"],
        "you": side,
        "legal": legal(state) if not state["over"] and side == state["turn"] else [],
        "last": state["last"],
        "win": state["win"],
        "seconds_left": max(0, int(state["deadline"] - now)) if state["deadline"] else 0,
        "move_seconds": state["move_seconds"],
        "draw_offer": None,
        "over": state["over"],
        "version": state["version"],
    }
