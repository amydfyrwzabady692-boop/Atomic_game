"""انفجار (Crash) گروهی برای مینی‌اپ: ۲ تا ۱۰ نفر.

هر دور یک ضریب از ۱٫۰۰× شروع می‌کند و با سرعت ثابتی (هر ۶ ثانیه دو برابر) بالا می‌رود تا در نقطه‌ای که از قبل با دانه‌ی
مسابقه معلوم شده (و تا انفجار به هیچ بیننده‌ای فرستاده نمی‌شود) «منفجر» شود. هر بازیکن هر وقت خواست «برداشت» می‌زند و
ضریب همان لحظه (به ساعت سرور) امتیازش می‌شود؛ کسی که تا انفجار برنداشته در آن دور صفر می‌گیرد. امتیاز بازی جمع ضریب‌های
همه‌ی دورهاست (یک، سه یا پنج دور).

پول بازی فقط از ورودی خود بازیکن‌هاست (pot)؛ جایزه طبق رتبه بین بازیکن‌ها تقسیم می‌شود و درصد کمی از pot (``house_percent``
مسابقه) سهم سرویس است. یعنی سرویس هیچ‌وقت بیشتر از آنچه گرفته پرداخت نمی‌کند و از هر بازی سود کمی می‌برد.
"""

import hashlib
import math
import time

from games.chess.live import LiveError

MIN_PLAYERS = 2
MAX_PLAYERS = 10
ROUNDS = (1, 3, 5)
DEFAULT_ROUNDS = 3
WAIT_SECONDS = 6  # شمارش معکوس قبل از هر دور
PAUSE_SECONDS = 4  # نمایش انفجار قبل از دور بعد
RATE = math.log(2) / 6  # ضریب هر ۶ ثانیه دو برابر می‌شود
MAX_MULT = 30.0
INSTANT_SHARE = 0.03  # حدود ۳٪ دورها همان اول (۱٫۰۰×) منفجر می‌شوند


def players(state: dict) -> dict:
    return {f"s{i}": uid for i, uid in enumerate(state["seats"])}


def seat_of(state: dict, user_id) -> int | None:
    try:
        return state["seats"].index(user_id)
    except ValueError:
        return None


def crash_point(seed: str, round_no: int) -> float:
    """نقطه‌ی انفجار هر دور از دانه‌ی مسابقه (قطعی و غیرقابل‌پیش‌بینی برای بازیکن‌ها)."""
    digest = hashlib.sha256(f"crash:{seed}:{round_no}".encode()).digest()
    u = int.from_bytes(digest[:8], "big") / 2**64
    point = (1 - INSTANT_SHARE) / (1 - u)
    return max(1.0, min(MAX_MULT, math.floor(point * 100) / 100))


def multiplier(elapsed: float) -> float:
    """ضریب بعد از ``elapsed`` ثانیه پرواز (رو به پایین تا دو رقم اعشار)."""
    return math.floor(math.exp(RATE * max(0.0, elapsed)) * 100) / 100


def fly_seconds(point: float) -> float:
    return math.log(point) / RATE


def new_state(user_ids: list[int], now: float, seed: str = "", rounds: int = DEFAULT_ROUNDS) -> dict:
    n = len(user_ids)
    if not MIN_PLAYERS <= n <= MAX_PLAYERS:
        raise ValueError("انفجار ۲ تا ۱۰ بازیکن لازم دارد")
    if rounds not in ROUNDS:
        rounds = DEFAULT_ROUNDS
    state = {
        "game": "crash",
        "seats": list(user_ids),
        "seed": seed or str(now),
        "rounds": rounds,
        "round": 0,
        "phase": "wait",
        "start_at": None,
        "point": None,  # نقطه‌ی انفجار همین دور؛ در view تا انفجار فرستاده نمی‌شود
        "cashed": [None] * n,  # ضریب برداشت هر نفر در همین دور
        "scores": [0] * n,  # جمع ضریب‌ها × ۱۰۰
        "results": [],  # برای هر دور: {"round", "point", "cashed"}
        "left": [False] * n,
        "deadline": None,
        "last_action": None,
        "over": None,
        "version": 1,
    }
    _next_round(state, now)
    return state


def _next_round(state: dict, now: float) -> None:
    state["round"] += 1
    state["phase"] = "wait"
    state["point"] = crash_point(state["seed"], state["round"])
    state["cashed"] = [None] * len(state["seats"])
    state["start_at"] = now + WAIT_SECONDS
    state["deadline"] = state["start_at"]


def _crash(state: dict, now: float) -> None:
    point = state["point"]
    state["results"].append({"round": state["round"], "point": point, "cashed": list(state["cashed"])})
    state["last_action"] = {"kind": "crash", "point": point, "round": state["round"]}
    if state["round"] >= state["rounds"]:
        _finish(state, "rounds")
        return
    state["phase"] = "pause"
    state["deadline"] = now + PAUSE_SECONDS


def _finish(state: dict, reason: str, **extra) -> None:
    active = [i for i in range(len(state["seats"])) if not state["left"][i]]
    best = max((state["scores"][i] for i in active), default=0)
    leaders = [i for i in active if state["scores"][i] == best] if best > 0 else []
    winner = state["seats"][leaders[0]] if len(leaders) == 1 else None
    state["over"] = {"reason": reason, "winner": winner, **extra}
    state["phase"] = "over"
    state["deadline"] = None


def _everyone_done(state: dict) -> bool:
    return all(state["cashed"][i] is not None or state["left"][i] for i in range(len(state["seats"])))


def advance(state: dict, now: float) -> bool:
    """جلو بردن زمان: شروع پرواز، انفجار، دور بعد. اگر چیزی عوض شد True."""
    changed = False
    for _ in range(4):
        if state["over"] or state["deadline"] is None:
            break
        if state["phase"] == "wait" and now >= state["start_at"]:
            state["phase"] = "fly"
            state["deadline"] = state["start_at"] + fly_seconds(state["point"])
        elif state["phase"] == "fly" and now >= state["deadline"]:
            _crash(state, state["deadline"])
        elif state["phase"] == "pause" and now >= state["deadline"]:
            _next_round(state, state["deadline"])
        else:
            break
        changed = True
    if changed:
        state["version"] += 1
    return changed


check_timeout = advance


def cash_out(state: dict, user_id: int, now: float) -> float:
    """برداشت با ضریب همین لحظه (به ساعت سرور). بعد از انفجار یا دوباره ممکن نیست."""
    advance(state, now)
    if state["over"]:
        raise LiveError("game_over")
    seat = seat_of(state, user_id)
    if seat is None:
        raise LiveError("not_a_player")
    if state["left"][seat]:
        raise LiveError("bad_action")
    if state["phase"] != "fly":
        raise LiveError("not_flying" if state["phase"] == "wait" else "crashed")
    if state["cashed"][seat] is not None:
        raise LiveError("already_cashed")
    mult = min(multiplier(now - state["start_at"]), state["point"])
    if mult >= state["point"]:
        raise LiveError("crashed")
    state["cashed"][seat] = mult
    state["scores"][seat] += int(round(mult * 100))
    state["last_action"] = {"kind": "cash", "seat": seat, "mult": mult}
    if _everyone_done(state):
        _crash(state, now)  # همه برداشتند: دور همین حالا تمام می‌شود و نقطه‌ی انفجار رو می‌شود
    state["version"] += 1
    return mult


def resign(state: dict, user_id: int, now: float | None = None) -> None:
    seat = seat_of(state, user_id)
    if seat is None:
        raise LiveError("not_a_player")
    if state["over"] or state["left"][seat]:
        raise LiveError("game_over" if state["over"] else "bad_action")
    state["left"][seat] = True
    if sum(not x for x in state["left"]) <= 1:
        _finish(state, "left", left_seat=seat)
    elif state["phase"] == "fly" and _everyone_done(state):
        _crash(state, now or time.time())
    state["version"] += 1


def apply_move(state, user_id, src, dst, promo, now):
    raise LiveError("bad_action")


def offer_draw(state, user_id):
    raise LiveError("bad_action")


def standings(state: dict) -> list[tuple[int, int]]:
    """(کاربر، امتیاز): جمع ضریب‌ها × ۱۰۰؛ کسی که بازی را ترک کرده صفر."""
    return [(uid, 0 if state["left"][i] else state["scores"][i]) for i, uid in enumerate(state["seats"])]


def view(state: dict, viewer_id: int | None, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    you = seat_of(state, viewer_id) if viewer_id is not None else None
    flying = state["phase"] == "fly"
    revealed = state["phase"] in ("pause", "over") and state["results"]
    over = state["over"]
    return {
        "game": "crash",
        "you": you,
        "seats": [
            {"seat": i, "side": f"s{i}", "cashed": state["cashed"][i], "score": state["scores"][i], "left": state["left"][i]}
            for i in range(len(state["seats"]))
        ],
        "round": state["round"],
        "rounds": state["rounds"],
        "phase": state["phase"],
        "rate": RATE,
        # زمان‌ها نسبت به همین پاسخ (میلی‌ثانیه) تا ساعت گوشی مهم نباشد
        "start_in_ms": int((state["start_at"] - now) * 1000) if state["phase"] in ("wait", "fly") else None,
        "elapsed_ms": int((now - state["start_at"]) * 1000) if flying else None,
        "mult": multiplier(now - state["start_at"]) if flying else None,
        "point": state["results"][-1]["point"] if revealed else None,
        "history": [r["point"] for r in state["results"]][-12:],
        "results": state["results"][-6:],
        "last_action": state["last_action"],
        "seconds_left": int(max(0.0, (state["deadline"] or now) - now)) if state["phase"] != "fly" else 0,
        "left_ms": int(max(0.0, (state["deadline"] or now) - now) * 1000) if state["phase"] != "fly" else 0,
        "over": over,
        "winner_seat": seat_of(state, over["winner"]) if over and over.get("winner") is not None else None,
        "version": state["version"],
    }
