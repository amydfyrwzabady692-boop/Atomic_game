"""شطرنج زنده برای صفحه‌ی گرافیکی مینی‌اپ.

وضعیت بازی یک dict ساده است که در ``Match.state["board"]`` ذخیره می‌شود؛ هم سرویس وب (که حرکت‌ها
را از مینی‌اپ می‌گیرد) و هم ربات (که نتیجه را در گروه اعلام می‌کند) همین را می‌خوانند. این ماژول
هیچ وابستگی به جنگو یا تلگرام ندارد و فقط قوانین را اعمال می‌کند؛ همه‌ی حرکت‌ها با موتور
``engine.Position`` اعتبارسنجی می‌شوند و کلاینت هیچ‌وقت وضعیت را تعیین نمی‌کند.
"""

from .engine import START_FEN, Move, Position, parse_square

MOVE_SECONDS = 90
MAX_PLIES = 300
DRAW_REASONS = ("stalemate", "insufficient", "fifty", "repetition", "agreed", "limit")


class LiveError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def new_state(white_id: int, black_id: int, now: float, move_seconds: int = MOVE_SECONDS) -> dict:
    return {
        "game": "chess",
        "w": white_id,
        "b": black_id,
        "fen": START_FEN,
        "moves": [],
        "last": None,
        "deadline": now + move_seconds,
        "move_seconds": move_seconds,
        "draw_offer": None,
        "over": None,
        "version": 1,
    }


def position_of(state: dict) -> Position:
    return Position.from_fen(state["fen"])


def players(state: dict) -> dict:
    return {"w": state["w"], "b": state["b"]}


def side_of(state: dict, user_id: int) -> str | None:
    if state["w"] == user_id:
        return "w"
    if state["b"] == user_id:
        return "b"
    return None


def other(side: str) -> str:
    return "b" if side == "w" else "w"


def _parse(position: Position, text: str) -> Move:
    promo = text[4:5]
    if promo:
        promo = promo.upper() if position.turn == "w" else promo.lower()
    return Move(parse_square(text[:2]), parse_square(text[2:4]), promo)


def repetitions(state: dict) -> int:
    """وضعیت فعلی از ابتدای بازی چند بار پیش آمده است (برای قانون تکرار سه‌باره)."""
    position = Position.initial()
    counts = {position.key(): 1}
    for text in state["moves"]:
        position = position.push(_parse(position, text), validate=False)
        counts[position.key()] = counts.get(position.key(), 0) + 1
    return counts[position.key()]


def _finish(state: dict, reason: str, winner_side: str | None = None) -> None:
    state["over"] = {"reason": reason, "side": winner_side, "winner": state[winner_side] if winner_side else None}
    state["deadline"] = None
    state["draw_offer"] = None
    state["version"] += 1


def check_timeout(state: dict, now: float) -> bool:
    """اگر مهلت حرکت گذشته باشد بازی را به سود حریف تمام می‌کند."""
    if state["over"] or state["deadline"] is None or now <= state["deadline"]:
        return False
    _finish(state, "timeout", other(position_of(state).turn))
    return True


def apply_move(state: dict, user_id: int, src: int, dst: int, promo: str, now: float) -> Move:
    """یک حرکت را اعتبارسنجی و اعمال می‌کند؛ در خطا ``LiveError`` می‌دهد."""
    if check_timeout(state, now) or state["over"]:
        raise LiveError("game_over")
    side = side_of(state, user_id)
    if side is None:
        raise LiveError("not_a_player")
    position = position_of(state)
    if side != position.turn:
        raise LiveError("not_your_turn")
    if not (0 <= src < 64 and 0 <= dst < 64):
        raise LiveError("illegal_move")
    candidates = [move for move in position.moves_from(src) if move.dst == dst]
    if not candidates:
        raise LiveError("illegal_move")
    move = candidates[0]
    if move.promo:  # ارتقای پیاده: مهره‌ی خواسته‌شده، پیش‌فرض وزیر
        wanted = (promo or "q")[:1].upper()
        move = next((m for m in candidates if m.promo.upper() == wanted), None)
        if move is None:
            raise LiveError("illegal_move")
    position = position.push(move)
    state["fen"] = position.fen()
    state["moves"].append(str(move))
    state["last"] = [move.src, move.dst]
    if state["draw_offer"] not in (None, user_id):
        state["draw_offer"] = None  # حرکت کردن یعنی رد پیشنهاد مساوی حریف
    state["deadline"] = now + state["move_seconds"]
    state["version"] += 1
    outcome = position.outcome()
    if outcome == "checkmate":
        _finish(state, "checkmate", side)
    elif outcome:
        _finish(state, outcome)
    elif repetitions(state) >= 3:
        _finish(state, "repetition")
    elif len(state["moves"]) >= MAX_PLIES:
        _finish(state, "limit")
    return move


def resign(state: dict, user_id: int) -> None:
    side = side_of(state, user_id)
    if side is None:
        raise LiveError("not_a_player")
    if state["over"]:
        raise LiveError("game_over")
    _finish(state, "resign", other(side))


def offer_draw(state: dict, user_id: int) -> bool:
    """پیشنهاد مساوی می‌دهد یا پیشنهاد حریف را قبول می‌کند. اگر بازی مساوی تمام شد ``True``."""
    if side_of(state, user_id) is None:
        raise LiveError("not_a_player")
    if state["over"]:
        raise LiveError("game_over")
    if state["draw_offer"] not in (None, user_id):
        _finish(state, "agreed")
        return True
    if state["draw_offer"] != user_id:
        state["draw_offer"] = user_id
        state["version"] += 1
    return False


def view(state: dict, viewer_id: int | None, now: float) -> dict:
    """تصویر وضعیت برای کلاینت. حرکت‌های مجاز فقط برای بازیکنی که نوبتش است فرستاده می‌شود."""
    position = position_of(state)
    side = side_of(state, viewer_id) if viewer_id is not None else None
    legal: dict[str, list[int]] = {}
    if not state["over"] and side == position.turn:
        for move in position.legal_moves():
            targets = legal.setdefault(str(move.src), [])
            if move.dst not in targets:
                targets.append(move.dst)
    offer = state["draw_offer"]
    return {
        "game": "chess",
        "board": "".join(position.board),
        "turn": position.turn,
        "you": side,
        "check": position.king_square(position.turn) if position.in_check() else None,
        "legal": legal,
        "last": state["last"],
        "plies": len(state["moves"]),
        "seconds_left": max(0, int(state["deadline"] - now)) if state["deadline"] else 0,
        "move_seconds": state["move_seconds"],
        "draw_offer": None if offer is None else ("you" if offer == viewer_id else "opponent"),
        "over": state["over"],
        "version": state["version"],
    }
