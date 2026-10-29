"""شطرنج زنده برای صفحه‌ی گرافیکی مینی‌اپ.

وضعیت بازی یک dict ساده است که در ``Match.state["board"]`` ذخیره می‌شود؛ هم سرویس وب (که حرکت‌ها
را از مینی‌اپ می‌گیرد) و هم ربات (که نتیجه را در گروه اعلام می‌کند) همین را می‌خوانند. این ماژول
هیچ وابستگی به جنگو یا تلگرام ندارد و فقط قوانین را اعمال می‌کند؛ همه‌ی حرکت‌ها با موتور
``engine.Position`` اعتبارسنجی می‌شوند و کلاینت هیچ‌وقت وضعیت را تعیین نمی‌کند.

ساعت مثل شطرنج بین‌المللی است: هر بازیکن ساعت خودش را دارد (مثلاً ۵ دقیقه) و بعد از هر حرکت چند
ثانیه به آن اضافه می‌شود (افزایش «فیشر»، مثل ۳+۲ قهرمانی برق‌آسای جهان فیده). ساعت فقط وقتی
بازیکن نوبت دارد کم می‌شود. مثل سایت‌های شطرنج آنلاین، اولین حرکت هر طرف از ساعتش کم نمی‌شود و فقط
مهلت جداگانه‌ی ``FIRST_MOVE_SECONDS`` دارد (تا بازیکن فرصت باز کردن صفحه را داشته باشد). تمام شدن
ساعت یعنی باخت، مگر حریف با هیچ رشته حرکتی نتواند مات کند (فقط شاه دارد) که مساوی است (قانون ۶.۹).
"""

from .engine import START_FEN, Move, Position, parse_square

# کنترل‌های زمانی: کلید ← (ثانیه‌ی پایه‌ی هر بازیکن، ثانیه‌ی افزایشی بعد از هر حرکت)
TIME_CONTROLS = {
    "bullet": (120, 1),  # ۲+۱
    "blitz3": (180, 2),  # ۳+۲ قهرمانی برق‌آسای جهان (فیده)
    "blitz5": (300, 3),  # ۵+۳
    "rapid10": (600, 5),  # ۱۰+۵
    "rapid15": (900, 10),  # ۱۵+۱۰ قهرمانی شطرنج سریع جهان (فیده)
    "classic": (1800, 20),  # ۳۰+۲۰
}
DEFAULT_CONTROL = "blitz5"
FIRST_MOVE_SECONDS = 60
MAX_PLIES = 600
LEGACY_MOVE_SECONDS = 90  # وضعیت‌های قدیمی (قبل از ساعت شطرنج) که مهلت ثابت هر حرکت داشتند
DRAW_REASONS = ("stalemate", "insufficient", "fifty", "repetition", "agreed", "limit", "timeout_draw")


class LiveError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def control_of(key: str | None) -> tuple[int, int] | None:
    """(پایه، افزایش) کنترل زمانی؛ کلید نامعتبر یعنی پیش‌فرض و ``None`` یعنی بازی بدون ساعت."""
    if key is None:
        return None
    return TIME_CONTROLS.get(key) or TIME_CONTROLS[DEFAULT_CONTROL]


def new_state(white_id: int, black_id: int, now: float, control: str | None = DEFAULT_CONTROL) -> dict:
    """بازی تازه. ``control=None`` بازی بدون ساعت است (تمرین با کامپیوتر)."""
    timing = control_of(control)
    if timing is not None and control not in TIME_CONTROLS:
        control = DEFAULT_CONTROL
    base, increment = timing or (None, 0)
    return {
        "game": "chess",
        "w": white_id,
        "b": black_id,
        "fen": START_FEN,
        "moves": [],
        "san": [],
        "last": None,
        "control": control,
        "base": base,
        "inc": increment,
        "clock": {"w": float(base), "b": float(base)} if base else None,
        "turn_at": now,  # لحظه‌ی شروع نوبت فعلی
        "deadline": now + FIRST_MOVE_SECONDS if base else None,  # لحظه‌ای که وقت بازیکن نوبت‌دار تمام می‌شود
        "draw_offer": None,
        "over": None,
        "version": 1,
    }


def _upgrade(state: dict) -> None:
    """وضعیتی که قبل از اضافه شدن ساعت شطرنج ذخیره شده را به قالب تازه درمی‌آورد (بی‌اثر روی وضعیت تازه).

    بازی‌های قدیمی با مهلت ثابت هر حرکت، ساعت ۱۰+۵ می‌گیرند؛ تمرین‌های بدون ساعت بدون ساعت می‌مانند."""
    if "clock" in state:
        return
    seconds = state.pop("move_seconds", LEGACY_MOVE_SECONDS)
    deadline = state.get("deadline")
    timed = seconds < 10**7
    base, increment = TIME_CONTROLS["rapid10"] if timed else (None, 0)
    turn_at = deadline - seconds if deadline is not None else 0.0
    position, san = Position.initial(), []
    for text in state["moves"]:
        move = _parse(position, text)
        san.append(position.san(move))
        position = position.push(move, validate=False)
    state.update(
        san=san,
        control="rapid10" if timed else None,
        base=base,
        inc=increment,
        clock={"w": float(base), "b": float(base)} if timed else None,
        turn_at=turn_at,
    )
    if state["over"] is None:
        state["deadline"] = _deadline(state, position.turn) if timed else None


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


def in_first_move(state: dict) -> bool:
    """هنوز در اولین حرکت یکی از دو طرف هستیم (ساعت شروع نشده)."""
    return len(state["moves"]) < 2


def _deadline(state: dict, turn: str) -> float:
    if in_first_move(state):
        return state["turn_at"] + FIRST_MOVE_SECONDS
    return state["turn_at"] + state["clock"][turn]


def clocks(state: dict, now: float) -> dict | None:
    """ثانیه‌ی باقی‌مانده‌ی ساعت هر طرف در لحظه‌ی ``now`` (یا ``None`` برای بازی بدون ساعت)."""
    _upgrade(state)
    if state["clock"] is None:
        return None
    result = dict(state["clock"])
    if not state["over"] and not in_first_move(state):
        turn = position_of(state).turn
        result[turn] = max(0.0, result[turn] - (now - state["turn_at"]))
    return result


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
    """اگر وقت بازیکن نوبت‌دار تمام شده باشد بازی را تمام می‌کند: باخت او، یا مساوی اگر حریف فقط شاه دارد."""
    _upgrade(state)
    if state["over"] or state["deadline"] is None or now <= state["deadline"]:
        return False
    position = position_of(state)
    flagged = position.turn
    if state["clock"] is not None and not in_first_move(state):
        state["clock"][flagged] = 0.0
    if position.has_mating_material(other(flagged)):
        _finish(state, "timeout", other(flagged))
    else:
        _finish(state, "timeout_draw")
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
    clock = state["clock"]
    if clock is not None and not in_first_move(state):
        # وقت مصرف‌شده کم و افزایش این کنترل زمانی اضافه می‌شود (اولین حرکت هر طرف مجانی است)
        clock[side] = round(max(0.0, clock[side] - (now - state["turn_at"])) + state["inc"], 3)
    san = position.san(move)
    position = position.push(move)
    state["fen"] = position.fen()
    state["moves"].append(str(move))
    state["san"].append(san)
    state["last"] = [move.src, move.dst]
    state["turn_at"] = now
    if state["draw_offer"] not in (None, user_id):
        state["draw_offer"] = None  # حرکت کردن یعنی رد پیشنهاد مساوی حریف
    state["deadline"] = _deadline(state, position.turn) if clock is not None else None
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
    _upgrade(state)
    side = side_of(state, user_id)
    if side is None:
        raise LiveError("not_a_player")
    if state["over"]:
        raise LiveError("game_over")
    _finish(state, "resign", other(side))


def offer_draw(state: dict, user_id: int) -> bool:
    """پیشنهاد مساوی می‌دهد یا پیشنهاد حریف را قبول می‌کند. اگر بازی مساوی تمام شد ``True``."""
    _upgrade(state)
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
    """تصویر وضعیت برای کلاینت. حرکت‌های مجاز فقط برای بازیکنی که نوبتش است فرستاده می‌شود.

    ساعت‌ها بر حسب میلی‌ثانیه‌اند؛ ``running`` طرفی است که ساعتش در حال کم شدن است (یا ``None``)."""
    _upgrade(state)
    position = position_of(state)
    side = side_of(state, viewer_id) if viewer_id is not None else None
    legal: dict[str, list[int]] = {}
    if not state["over"] and side == position.turn:
        for move in position.legal_moves():
            targets = legal.setdefault(str(move.src), [])
            if move.dst not in targets:
                targets.append(move.dst)
    offer = state["draw_offer"]
    remaining = clocks(state, now)
    left = max(0.0, state["deadline"] - now) if state["deadline"] else 0.0
    first = state["clock"] is not None and not state["over"] and in_first_move(state)
    return {
        "game": "chess",
        "board": "".join(position.board),
        "turn": position.turn,
        "you": side,
        "check": position.king_square(position.turn) if position.in_check() else None,
        "legal": legal,
        "last": state["last"],
        "plies": len(state["moves"]),
        "san": state["san"],
        "control": state["control"],
        "base": state["base"],
        "inc": state["inc"],
        "clock": {k: int(v * 1000) for k, v in remaining.items()} if remaining else None,
        "running": position.turn if remaining and not state["over"] and not first else None,
        "first_move": first,
        "seconds_left": int(left),
        "left_ms": int(left * 1000),
        "draw_offer": None if offer is None else ("you" if offer == viewer_id else "opponent"),
        "over": state["over"],
        "version": state["version"],
    }
