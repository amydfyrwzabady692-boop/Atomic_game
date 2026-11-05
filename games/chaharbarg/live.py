"""چهاربرگ (پاسور) برای میز کارت مینی‌اپ؛ ۲ تا ۴ نفر، هر کس برای خودش.

مثل بقیه‌ی بازی‌های زنده: وضعیت یک dict قابل‌ذخیره در JSON است و همه‌ی حرکت‌ها همین‌جا اعتبارسنجی می‌شود.

قوانین (چهاربرگ رایج ایرانی):
- اول ۴ کارت رو وسط زمین می‌آید (سرباز وسط نمی‌ماند و با کارت دیگری عوض می‌شود) و به هر نفر ۴ کارت می‌رسد؛ هر بار دست
  همه خالی شد، تا وقتی کارت هست دوباره نفری ۴ کارت پخش می‌شود.
- هر نوبت یک کارت بازی می‌شود. کارت عددی (آس = ۱ تا ۱۰) کارت‌هایی از زمین را برمی‌دارد که جمعشان با خودش ۱۱ شود؛
  سرباز همه‌ی کارت‌های زمین به‌جز شاه و بی‌بی را جمع می‌کند؛ بی‌بی فقط یک بی‌بی و شاه فقط یک شاه برمی‌دارد. اگر چیزی
  برنداشت، کارت روی زمین می‌ماند (بازیکن می‌تواند با وجود امکان برداشتن هم کارتش را زمین بگذارد، جز سرباز).
- «سور»: اگر با برداشتن، زمین خالی شود (نه با سرباز و نه با آخرین کارت دور) ۵ امتیاز.
- آخر دور کارت‌های مانده‌ی زمین مال آخرین کسی است که چیزی برداشته. امتیاز دور: بیشترین گشنیز ۷ (اگر تنها بیشترین باشد)،
  ده خشت ۳، دو گشنیز ۲، هر آس ۱، هر سرباز ۱ و هر سور ۵.
- بازی یک دور است یا تا رسیدن کسی به امتیاز هدف (۳۱ یا ۶۲).
"""

import time
from itertools import combinations

from games.chess.live import LiveError
from games.poker.cards import shuffled_deck

MIN_PLAYERS = 2
MAX_PLAYERS = 4
HAND = 4
TABLE = 4
MOVE_SECONDS = 25
AWAY_SECONDS = 6
AWAY_AFTER = 2
PAUSE_SECONDS = 7
TARGETS = (0, 31, 62)  # ۰ یعنی فقط یک دور
DEFAULT_TARGET = 0
SUR_POINTS = 5
FACES = "JQK"


def value(card: str) -> int:
    """ارزش عددی برای جمع ۱۱ (آس ۱، ده ۱۰)؛ کارت‌های تصویری صفر."""
    rank = card[0]
    if rank == "A":
        return 1
    if rank == "T":
        return 10
    return int(rank) if rank.isdigit() else 0


def players(state: dict) -> dict:
    return {f"s{i}": uid for i, uid in enumerate(state["seats"])}


def seat_of(state: dict, user_id) -> int | None:
    try:
        return state["seats"].index(user_id)
    except ValueError:
        return None


def size(state: dict) -> int:
    return len(state["seats"])


# ------------------------------------------------------------------ برداشتن
def options(table: list[str], card: str) -> list[list[str]]:
    """همه‌ی راه‌های برداشتن با این کارت (هر گزینه فهرست کارت‌های زمین)."""
    rank = card[0]
    if rank == "J":
        taken = [c for c in table if c[0] not in "KQ"]
        return [taken] if taken else []
    if rank in "QK":
        return [[c] for c in table if c[0] == rank]
    need = 11 - value(card)
    numeric = [c for c in table if c[0] not in FACES]
    found = []
    for k in range(1, len(numeric) + 1):
        for combo in combinations(numeric, k):
            if sum(value(c) for c in combo) == need:
                found.append(list(combo))
    return found


def card_points(card: str) -> int:
    """ارزش امتیازی هر کارت (برای انتخاب خودکار بهترین برداشت)."""
    return {"Td": 3, "2c": 2}.get(card, 0) + (1 if card[0] in "AJ" else 0)


def _score_option(card: str, taken: list[str]) -> tuple:
    cards = taken + [card]
    return (sum(card_points(c) for c in cards), sum(c[1] == "c" for c in cards), len(cards))


def best_option(table: list[str], card: str) -> list[str] | None:
    found = options(table, card)
    if not found:
        return None
    return max(found, key=lambda o: _score_option(card, o))


# ------------------------------------------------------------------ ساخت میز
def new_state(user_ids: list[int], now: float, seed: str = "", target: int = DEFAULT_TARGET) -> dict:
    n = len(user_ids)
    if not MIN_PLAYERS <= n <= MAX_PLAYERS:
        raise ValueError("چهاربرگ ۲ تا ۴ بازیکن لازم دارد")
    state = {
        "game": "chaharbarg",
        "seats": list(user_ids),
        "seed": seed or str(now),
        "target": target if target in TARGETS else DEFAULT_TARGET,
        "points": [0] * n,
        "round": 0,
        "dealer": n - 1,
        "deck": [],
        "table": [],
        "hands": [[] for _ in range(n)],
        "captured": [[] for _ in range(n)],
        "surs": [0] * n,
        "last_capturer": None,
        "turn": 0,
        "phase": "play",
        "deadline": None,
        "move_seconds": MOVE_SECONDS,
        "last_action": None,
        "result": None,
        "history": [],
        "misses": [0] * n,
        "away": [False] * n,
        "left": [False] * n,
        "over": None,
        "version": 1,
    }
    _start_round(state, now)
    return state


def _deadline(state: dict, seat: int, now: float) -> float:
    return now + (AWAY_SECONDS if state["away"][seat] or state["left"][seat] else state["move_seconds"])


def _start_round(state: dict, now: float) -> None:
    n = size(state)
    state["round"] += 1
    state["dealer"] = (state["dealer"] + 1) % n
    deck = shuffled_deck(f"{state['seed']}:{state['round']}")
    table = []
    while len(table) < TABLE:
        card = deck.pop()
        if card[0] == "J":  # سرباز وسط زمین نمی‌ماند
            deck.insert(0, card)
            continue
        table.append(card)
    state["deck"] = deck
    state["table"] = table
    state["captured"] = [[] for _ in range(n)]
    state["surs"] = [0] * n
    state["last_capturer"] = None
    state["result"] = None
    _deal(state)
    state["turn"] = (state["dealer"] + 1) % n
    state["phase"] = "play"
    state["deadline"] = _deadline(state, state["turn"], now)


def _deal(state: dict) -> None:
    n = size(state)
    order = [(state["dealer"] + 1 + i) % n for i in range(n)]
    for seat in order:
        for _ in range(HAND):
            state["hands"][seat].append(state["deck"].pop())


# ------------------------------------------------------------------ حرکت
def _mark(state: dict, seat: int, timeout: bool) -> None:
    if timeout:
        state["misses"][seat] += 1
        if state["misses"][seat] >= AWAY_AFTER:
            state["away"][seat] = True
    else:
        state["misses"][seat] = 0
        state["away"][seat] = False


def _apply(state: dict, seat: int, card: str, take: list[str] | None, now: float, timeout: bool = False) -> None:
    hand = state["hands"][seat]
    hand.remove(card)
    table = state["table"]
    sur = False
    if take:
        for c in take:
            table.remove(c)
        state["captured"][seat].extend(take + [card])
        state["last_capturer"] = seat
        last_card = not state["deck"] and not any(state["hands"])
        if not table and card[0] != "J" and not last_card:
            state["surs"][seat] += 1
            sur = True
    else:
        table.append(card)
    _mark(state, seat, timeout)
    state["last_action"] = {"kind": "play", "seat": seat, "card": card, "take": list(take or []), "sur": sur, "timeout": timeout}
    n = size(state)
    if any(state["hands"]):
        state["turn"] = (seat + 1) % n
        state["deadline"] = _deadline(state, state["turn"], now)
        return
    if state["deck"]:
        _deal(state)
        state["turn"] = (seat + 1) % n
        state["deadline"] = _deadline(state, state["turn"], now)
        return
    _end_round(state, now)


def score_round(state: dict) -> list[dict]:
    """امتیاز هر نفر در این دور، با جزئیات."""
    n = size(state)
    clubs = [sum(c[1] == "c" for c in state["captured"][i]) for i in range(n)]
    top = max(clubs)
    rows = []
    for i in range(n):
        cards = state["captured"][i]
        row = {
            "clubs": clubs[i],
            "clubs_bonus": 7 if clubs[i] == top and clubs.count(top) == 1 else 0,
            "ten_diamonds": 3 if "Td" in cards else 0,
            "two_clubs": 2 if "2c" in cards else 0,
            "aces": sum(c[0] == "A" for c in cards),
            "jacks": sum(c[0] == "J" for c in cards),
            "surs": state["surs"][i] * SUR_POINTS,
            "cards": len(cards),
        }
        row["total"] = row["clubs_bonus"] + row["ten_diamonds"] + row["two_clubs"] + row["aces"] + row["jacks"] + row["surs"]
        rows.append(row)
    return rows


def _end_round(state: dict, now: float) -> None:
    if state["table"] and state["last_capturer"] is not None:
        state["captured"][state["last_capturer"]].extend(state["table"])
        state["table"] = []
    rows = score_round(state)
    for i, row in enumerate(rows):
        state["points"][i] += row["total"]
    state["result"] = {"round": state["round"], "rows": rows}
    state["history"] = (state["history"] + [{"round": state["round"], "totals": [r["total"] for r in rows]}])[-20:]
    state["turn"] = None
    best = max(state["points"])
    leaders = [i for i, p in enumerate(state["points"]) if p == best]
    if state["target"] == 0 or (best >= state["target"] and len(leaders) == 1):
        _finish(state, "points" if state["target"] else "round")
        return
    state["phase"] = "pause"
    state["deadline"] = now + PAUSE_SECONDS


def _finish(state: dict, reason: str, **extra) -> None:
    active = [i for i in range(size(state)) if not state["left"][i]]
    best = max(state["points"][i] for i in active) if active else 0
    leaders = [i for i in active if state["points"][i] == best]
    state["over"] = {"reason": reason, "winner": state["seats"][leaders[0]] if len(leaders) == 1 else None, **extra}
    state["phase"] = "over"
    state["turn"] = None
    state["deadline"] = None


def auto_move(state: dict, seat: int) -> tuple[str, list[str] | None]:
    """حرکت به جای بازیکنِ دیر یا غایب: بهترین برداشت، وگرنه کم‌ارزش‌ترین کارت را زمین می‌گذارد."""
    hand = state["hands"][seat]
    best = None
    for card in hand:
        option = best_option(state["table"], card)
        if option is not None:
            score = _score_option(card, option)
            if best is None or score > best[0]:
                best = (score, card, option)
    if best is not None:
        return best[1], best[2]
    card = min(hand, key=lambda c: (card_points(c), c[0] in FACES, c[1] == "c", value(c)))
    return card, None


def check_timeout(state: dict, now: float) -> bool:
    if state["over"] or state["deadline"] is None or now <= state["deadline"]:
        return False
    if state["phase"] == "pause":
        _start_round(state, now)
    elif state["phase"] == "play":
        seat = state["turn"]
        card, take = auto_move(state, seat)
        _apply(state, seat, card, take, now, timeout=not state["left"][seat])
    else:
        return False
    state["version"] += 1
    return True


def play(state: dict, user_id: int, card, take, now: float) -> None:
    """بازی یک کارت. ``take`` کارت‌هایی از زمین که برداشته می‌شود؛ ``[]`` یعنی زمین گذاشتن و ``None`` یعنی بهترین برداشت."""
    if check_timeout(state, now):
        raise LiveError("timeout")
    if state["over"]:
        raise LiveError("game_over")
    seat = seat_of(state, user_id)
    if seat is None:
        raise LiveError("not_a_player")
    if state["phase"] != "play" or state["turn"] != seat:
        raise LiveError("not_your_turn")
    if not isinstance(card, str) or card not in state["hands"][seat]:
        raise LiveError("illegal_move")
    found = options(state["table"], card)
    if take is None:
        take = best_option(state["table"], card) or []
    if not isinstance(take, list) or not all(isinstance(c, str) for c in take):
        raise LiveError("illegal_move")
    if take:
        if sorted(take) not in [sorted(o) for o in found]:
            raise LiveError("illegal_move")
    elif card[0] == "J" and found:
        raise LiveError("illegal_move")  # سرباز همیشه جمع می‌کند
    _apply(state, seat, card, take, now)
    state["version"] += 1


def resign(state: dict, user_id: int, now: float | None = None) -> None:
    """ترک بازی: امتیاز این نفر صفر می‌شود و از این به بعد کارتش خودکار بازی می‌شود؛ اگر یک نفر بماند بازی تمام است."""
    seat = seat_of(state, user_id)
    if seat is None:
        raise LiveError("not_a_player")
    if state["over"] or state["left"][seat]:
        raise LiveError("game_over" if state["over"] else "bad_action")
    state["left"][seat] = True
    if sum(not x for x in state["left"]) <= 1:
        _finish(state, "left", left_seat=seat)
    elif state["turn"] == seat:
        state["deadline"] = min(state["deadline"] or 0, (now or time.time()) + 1)
    state["version"] += 1


def apply_move(state, user_id, src, dst, promo, now):
    raise LiveError("bad_action")


def offer_draw(state, user_id):
    raise LiveError("bad_action")


def standings(state: dict) -> list[tuple[int, int]]:
    """(کاربر، امتیاز)؛ کسی که بازی را ترک کرده صفر می‌گیرد."""
    return [(uid, 0 if state["left"][i] else state["points"][i]) for i, uid in enumerate(state["seats"])]


def view(state: dict, viewer_id: int | None, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    you = seat_of(state, viewer_id) if viewer_id is not None else None
    hand = list(state["hands"][you]) if you is not None else []
    my_turn = you is not None and state["phase"] == "play" and state["turn"] == you and not state["over"]
    left = max(0.0, state["deadline"] - now) if state["deadline"] else 0.0
    turn = state["turn"]
    over = state["over"]
    winner_seat = seat_of(state, over["winner"]) if over and over.get("winner") is not None else None
    return {
        "game": "chaharbarg",
        "you": you,
        "hand": hand,
        "options": {c: options(state["table"], c) for c in hand} if my_turn else {},
        "table": state["table"],
        "seats": [
            {
                "seat": i,
                "side": f"s{i}",
                "count": len(state["hands"][i]),
                "captured": len(state["captured"][i]),
                "clubs": sum(c[1] == "c" for c in state["captured"][i]),
                "surs": state["surs"][i],
                "away": state["away"][i],
                "left": state["left"][i],
                "dealer": i == state["dealer"],
            }
            for i in range(size(state))
        ],
        "points": state["points"],
        "target": state["target"],
        "round": state["round"],
        "deck": len(state["deck"]),
        "phase": state["phase"],
        "turn": turn,
        "last_action": state["last_action"],
        "result": state["result"],
        "history": state["history"][-8:],
        "seconds_left": int(left),
        "left_ms": int(left * 1000),
        "move_seconds": AWAY_SECONDS if turn is not None and state["away"][turn] else state["move_seconds"],
        "over": state["over"],
        "winner_seat": winner_seat,
        "version": state["version"],
    }
