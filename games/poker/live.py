"""میز پوکر تگزاس هولدم برای گروه و مینی‌اپ.

مثل ``games.chess.live`` و ``games.gridlive``: وضعیت یک dict قابل‌ذخیره در JSON است، همه‌ی حرکت‌ها
همین‌جا اعتبارسنجی می‌شوند و ماژول به جنگو یا تلگرام وابسته نیست. ژتون‌های میز جدا از سکه‌اند: هر
بازیکن با ``START_CHIPS`` ژتون شروع می‌کند، بازی بعد از ``HAND_LIMIT`` دست (یا وقتی یک نفر همه‌ی
ژتون‌ها را برد) تمام می‌شود و رتبه‌بندی نهایی بر اساس ژتون است؛ جایزه‌ی سکه را موتور مسابقه
بر اساس همین رتبه‌ها تقسیم می‌کند.

قوانین: بلایند کوچک/بزرگ (هر ``BLIND_UP_HANDS`` دست دو برابر)، چهار دور شرط‌بندی، پات‌های جانبی
برای آل‌این، تقسیم پات در تساوی. در بازی دونفره دیلر بلایند کوچک را می‌گذارد و قبل از فلاپ اول
حرف می‌زند. مهلت هر حرکت ``MOVE_SECONDS`` است؛ اگر تمام شود چک (اگر ممکن باشد) وگرنه فولد می‌شود.
"""

from games.chess.live import LiveError

from .cards import best_hand, hand_name, shuffled_deck

START_CHIPS = 1000
SMALL_BLIND = 10
BLIND_UP_HANDS = 4
HAND_LIMIT = 10
MOVE_SECONDS = 30
PAUSE_SECONDS = 6
MIN_PLAYERS = 2
MAX_PLAYERS = 8
STREETS = ("preflop", "flop", "turn", "river")
ACTIONS = ("fold", "check", "call", "raise", "allin")


# ------------------------------------------------------------------ ساخت میز
def new_state(user_ids: list[int], now: float, seed: str = "", hand_limit: int = HAND_LIMIT) -> dict:
    if not MIN_PLAYERS <= len(user_ids) <= MAX_PLAYERS:
        raise ValueError("تعداد بازیکن پوکر باید بین ۲ و ۸ باشد")
    n = len(user_ids)
    state = {
        "game": "poker",
        "seats": list(user_ids),
        "chips": [START_CHIPS] * n,
        "left": [False] * n,
        "seed": seed or str(now),
        "hand": 0,
        "hand_limit": hand_limit,
        "dealer": -1,
        "sb": SMALL_BLIND,
        "bb": SMALL_BLIND * 2,
        "deck": [],
        "board": [],
        "hole": [[] for _ in range(n)],
        "in_hand": [False] * n,
        "folded": [False] * n,
        "allin": [False] * n,
        "bet": [0] * n,
        "contrib": [0] * n,
        "acted": [False] * n,
        "street": "",
        "to_act": None,
        "current_bet": 0,
        "min_raise": SMALL_BLIND * 2,
        "phase": "betting",
        "deadline": None,
        "move_seconds": MOVE_SECONDS,
        "last_action": None,
        "result": None,
        "over": None,
        "version": 1,
    }
    _start_hand(state, now)
    return state


def players(state: dict) -> dict:
    return {f"s{i}": uid for i, uid in enumerate(state["seats"])}


def seat_of(state: dict, user_id: int) -> int | None:
    try:
        return state["seats"].index(user_id)
    except ValueError:
        return None


def pot(state: dict) -> int:
    return sum(state["contrib"])


# ------------------------------------------------------------------ ابزار
def _next_seat(state: dict, start: int, accept) -> int | None:
    n = len(state["seats"])
    for step in range(1, n + 1):
        seat = (start + step) % n
        if accept(seat):
            return seat
    return None


def _live(state: dict) -> list[int]:
    """بازیکن‌هایی که در این دست هستند و فولد نکرده‌اند."""
    return [i for i in range(len(state["seats"])) if state["in_hand"][i] and not state["folded"][i]]


def _needs_action(state: dict, seat: int) -> bool:
    return (
        state["in_hand"][seat]
        and not state["folded"][seat]
        and not state["allin"][seat]
        and (not state["acted"][seat] or state["bet"][seat] < state["current_bet"])
    )


def _put(state: dict, seat: int, amount: int) -> int:
    """ژتون را از جلوی بازیکن به میز می‌برد (حداکثر تا موجودی‌اش) و مقدار واقعی را برمی‌گرداند."""
    amount = max(0, min(amount, state["chips"][seat]))
    state["chips"][seat] -= amount
    state["bet"][seat] += amount
    state["contrib"][seat] += amount
    if state["chips"][seat] == 0:
        state["allin"][seat] = True
    return amount


def _contenders(state: dict) -> list[int]:
    return [i for i in range(len(state["seats"])) if not state["left"][i] and state["chips"][i] > 0]


# ------------------------------------------------------------------ چرخه‌ی دست
def _start_hand(state: dict, now: float) -> None:
    contenders = _contenders(state)
    if len(contenders) <= 1 or state["hand"] >= state["hand_limit"]:
        _finish_game(state, "chips" if len(contenders) <= 1 else "limit")
        return
    n = len(state["seats"])
    state["hand"] += 1
    level = (state["hand"] - 1) // BLIND_UP_HANDS
    state["sb"] = SMALL_BLIND * (2**level)
    state["bb"] = state["sb"] * 2
    in_hand = [i in contenders for i in range(n)]
    state["in_hand"] = in_hand
    state["dealer"] = _next_seat(state, state["dealer"], lambda i: in_hand[i])
    state["folded"] = [False] * n
    state["allin"] = [False] * n
    state["bet"] = [0] * n
    state["contrib"] = [0] * n
    state["acted"] = [False] * n
    state["board"] = []
    state["hole"] = [[] for _ in range(n)]
    state["result"] = None
    state["last_action"] = None
    deck = shuffled_deck(f"{state['seed']}:{state['hand']}")
    order = [state["dealer"]]
    while len(order) < len(contenders):
        order.append(_next_seat(state, order[-1], lambda i: in_hand[i]))
    for _ in range(2):
        for seat in order[1:] + order[:1]:
            state["hole"][seat].append(deck.pop())
    state["deck"] = deck
    if len(contenders) == 2:
        sb_seat = state["dealer"]
        bb_seat = _next_seat(state, sb_seat, lambda i: in_hand[i])
    else:
        sb_seat = _next_seat(state, state["dealer"], lambda i: in_hand[i])
        bb_seat = _next_seat(state, sb_seat, lambda i: in_hand[i])
    _put(state, sb_seat, state["sb"])
    _put(state, bb_seat, state["bb"])
    state["current_bet"] = max(state["bet"])
    state["min_raise"] = state["bb"]
    state["street"] = "preflop"
    state["phase"] = "betting"
    state["to_act"] = _next_seat(state, bb_seat, lambda i: _needs_action(state, i))
    state["deadline"] = now + state["move_seconds"]
    if state["to_act"] is None:  # همه آل‌این شده‌اند (مثلاً بلایندها)
        _next_street(state, now)


def _deal(state: dict, count: int) -> None:
    state["deck"].pop()  # سوزاندن یک کارت
    for _ in range(count):
        state["board"].append(state["deck"].pop())


def _next_street(state: dict, now: float) -> None:
    n = len(state["seats"])
    while True:
        state["bet"] = [0] * n
        state["current_bet"] = 0
        state["min_raise"] = state["bb"]
        state["acted"] = [False] * n
        if state["street"] == "river":
            _showdown(state, now)
            return
        state["street"] = STREETS[STREETS.index(state["street"]) + 1]
        _deal(state, 3 if state["street"] == "flop" else 1)
        can_act = [i for i in _live(state) if not state["allin"][i]]
        if len(can_act) >= 2:
            state["to_act"] = _next_seat(state, state["dealer"], lambda i: _needs_action(state, i))
            state["deadline"] = now + state["move_seconds"]
            return


def _after_action(state: dict, now: float) -> None:
    live = _live(state)
    if len(live) == 1:
        winner = live[0]
        amount = pot(state)
        state["chips"][winner] += amount
        state["result"] = {"reveal": {}, "winners": [{"seat": winner, "amount": amount, "hand": ""}]}
        _end_hand(state, now)
        return
    seat = _next_seat(state, state["to_act"], lambda i: _needs_action(state, i))
    if seat is not None:
        state["to_act"] = seat
        state["deadline"] = now + state["move_seconds"]
        return
    _next_street(state, now)


def side_pots(state: dict) -> list[tuple[int, list[int]]]:
    """پات اصلی و پات‌های جانبی: [(مقدار، صندلی‌های مجاز)]. فولدکرده‌ها سهم می‌گذارند ولی نمی‌برند."""
    contrib = state["contrib"]
    live = set(_live(state))
    levels = sorted({c for c in contrib if c > 0})
    pots: list[tuple[int, list[int]]] = []
    previous = 0
    for level in levels:
        amount = sum(min(c, level) - min(c, previous) for c in contrib)
        eligible = [i for i in sorted(live) if contrib[i] >= level]
        if not eligible and pots:
            # سهم اضافه‌ی فولدکرده‌ای که بیشتر از همه‌ی بازیکن‌های مانده گذاشته به پات قبلی می‌رود
            pots[-1] = (pots[-1][0] + amount, pots[-1][1])
        elif pots and pots[-1][1] == eligible:
            pots[-1] = (pots[-1][0] + amount, eligible)
        else:
            pots.append((amount, eligible))
        previous = level
    return pots


def _showdown(state: dict, now: float) -> None:
    live = _live(state)
    scores = {i: best_hand(state["hole"][i] + state["board"]) for i in live}
    won: dict[int, int] = {}
    for amount, eligible in side_pots(state):
        if not eligible:
            continue
        top = max(scores[i][0] for i in eligible)
        winners = [i for i in eligible if scores[i][0] == top]
        share, extra = divmod(amount, len(winners))
        # باقیمانده‌ی تقسیم به اولین برنده بعد از دیلر می‌رسد
        first = _next_seat(state, state["dealer"], lambda i, winners=winners: i in winners)
        for i in winners:
            won[i] = won.get(i, 0) + share + (extra if i == first else 0)
    for seat, amount in won.items():
        state["chips"][seat] += amount
    state["result"] = {
        "reveal": {str(i): state["hole"][i] for i in live},
        "winners": [
            {"seat": i, "amount": amount, "hand": hand_name(scores[i][0]), "cards": scores[i][1]}
            for i, amount in sorted(won.items())
        ],
    }
    _end_hand(state, now)


def _end_hand(state: dict, now: float) -> None:
    state["phase"] = "pause"
    state["to_act"] = None
    state["contrib"] = [0] * len(state["seats"])
    state["bet"] = [0] * len(state["seats"])
    state["deadline"] = now + PAUSE_SECONDS


def _finish_game(state: dict, reason: str) -> None:
    ranked = standings(state)
    top = max(score for _, score in ranked)
    leaders = [uid for uid, score in ranked if score == top]
    state["over"] = {"reason": reason, "winner": leaders[0] if len(leaders) == 1 and top > 0 else None}
    state["phase"] = "over"
    state["to_act"] = None
    state["deadline"] = None


def standings(state: dict) -> list[tuple[int, int]]:
    """(شناسه‌ی کاربر، ژتون نهایی). کسی که میز را ترک کرده امتیاز صفر می‌گیرد."""
    return [(uid, 0 if state["left"][i] else state["chips"][i]) for i, uid in enumerate(state["seats"])]


# ------------------------------------------------------------------ حرکت‌ها
def check_timeout(state: dict, now: float) -> bool:
    """پایان مهلت: در وقفه‌ی بین دو دست، دست بعد شروع می‌شود؛ وگرنه نوبتی چک یا فولد می‌شود."""
    if state["over"] or state["deadline"] is None or now <= state["deadline"]:
        return False
    if state["phase"] == "pause":
        _start_hand(state, now)
    else:
        seat = state["to_act"]
        kind = "check" if state["bet"][seat] == state["current_bet"] else "fold"
        if kind == "fold":
            state["folded"][seat] = True
        state["acted"][seat] = True
        state["last_action"] = {"seat": seat, "kind": kind, "amount": 0, "timeout": True}
        _after_action(state, now)
    state["version"] += 1
    return True


def legal_actions(state: dict, seat: int) -> dict:
    """حرکت‌های مجاز این صندلی (اگر نوبتش باشد) برای دکمه‌های گروه و مینی‌اپ."""
    if state["over"] or state["phase"] != "betting" or state["to_act"] != seat:
        return {}
    chips, bet, current = state["chips"][seat], state["bet"][seat], state["current_bet"]
    to_call = min(current - bet, chips)
    min_to = current + state["min_raise"]
    max_to = bet + chips
    return {
        "fold": True,
        "check": bet == current,
        "call": to_call if to_call > 0 else 0,
        "raise_min": min_to if max_to > min_to else 0,
        "raise_max": max_to if max_to > min_to else 0,
        "allin": chips,
    }


def act(state: dict, user_id: int, kind: str, amount: int, now: float) -> None:
    """یک حرکت شرط‌بندی. ``amount`` فقط برای ``raise`` است: کل شرط این دور بعد از رِیز."""
    if check_timeout(state, now):
        raise LiveError("timeout")
    if state["over"]:
        raise LiveError("game_over")
    seat = seat_of(state, user_id)
    if seat is None:
        raise LiveError("not_a_player")
    if state["phase"] != "betting" or state["to_act"] != seat:
        raise LiveError("not_your_turn")
    legal = legal_actions(state, seat)
    current = state["current_bet"]
    if kind == "fold":
        state["folded"][seat] = True
        put = 0
    elif kind == "check":
        if not legal["check"]:
            raise LiveError("illegal_move")
        put = 0
    elif kind == "call":
        if not legal["call"]:
            raise LiveError("illegal_move")
        put = _put(state, seat, legal["call"])
    elif kind in ("raise", "allin"):
        target = state["bet"][seat] + state["chips"][seat] if kind == "allin" else amount
        if kind == "raise":
            if isinstance(target, bool) or not isinstance(target, int) or not legal["raise_min"]:
                raise LiveError("illegal_move")
            if not legal["raise_min"] <= target <= legal["raise_max"]:
                raise LiveError("illegal_move")
        put = _put(state, seat, target - state["bet"][seat])
        new_bet = state["bet"][seat]
        if new_bet > current:
            if new_bet - current >= state["min_raise"]:
                state["min_raise"] = new_bet - current
            state["current_bet"] = new_bet
            for other in range(len(state["seats"])):
                if other != seat:
                    state["acted"][other] = False
    else:
        raise LiveError("bad_action")
    state["acted"][seat] = True
    state["last_action"] = {"seat": seat, "kind": kind, "amount": put}
    _after_action(state, now)
    state["version"] += 1


def apply_move(state: dict, user_id: int, src: int, dst: int, promo: str, now: float):
    raise LiveError("bad_action")  # پوکر حرکت خانه‌ای ندارد؛ از ``act`` استفاده می‌شود


def resign(state: dict, user_id: int, now: float | None = None) -> None:
    """ترک میز: دست فعلی فولد و ژتون‌های باقی‌مانده بی‌اثر می‌شود (امتیاز نهایی صفر)."""
    import time

    now = time.time() if now is None else now
    seat = seat_of(state, user_id)
    if seat is None:
        raise LiveError("not_a_player")
    if state["over"]:
        raise LiveError("game_over")
    if state["left"][seat]:
        raise LiveError("bad_action")
    state["left"][seat] = True
    if state["phase"] == "betting" and state["in_hand"][seat] and not state["folded"][seat]:
        state["folded"][seat] = True
        state["acted"][seat] = True
        state["last_action"] = {"seat": seat, "kind": "leave", "amount": 0}
        if state["to_act"] == seat:
            _after_action(state, now)
        elif len(_live(state)) == 1:
            state["to_act"] = seat  # برای محاسبه‌ی نفر بعد؛ بلافاصله به برنده می‌رسد
            _after_action(state, now)
    if len([i for i in range(len(state["seats"])) if not state["left"][i]]) <= 1 and state["phase"] != "betting":
        _finish_game(state, "left")
    state["version"] += 1


def offer_draw(state: dict, user_id: int) -> bool:
    raise LiveError("bad_action")


# ------------------------------------------------------------------ نمایش
def view(state: dict, viewer_id: int | None, now: float) -> dict:
    you = seat_of(state, viewer_id) if viewer_id is not None else None
    reveal = (state["result"] or {}).get("reveal", {}) if state["phase"] == "pause" else {}
    seats = []
    for i in range(len(state["seats"])):
        if i == you or str(i) in reveal:
            cards = state["hole"][i]
        elif state["in_hand"][i] and not state["folded"][i] and not state["over"]:
            cards = ["", ""]  # پشت کارت
        else:
            cards = []
        seats.append(
            {
                "seat": i,
                "side": f"s{i}",
                "chips": state["chips"][i],
                "bet": state["bet"][i],
                "folded": state["folded"][i],
                "allin": state["allin"][i],
                "left": state["left"][i],
                "in_hand": state["in_hand"][i],
                "dealer": i == state["dealer"],
                "cards": cards,
            }
        )
    return {
        "game": "poker",
        "seats": seats,
        "you": you,
        "board": state["board"],
        "pot": pot(state),
        "street": state["street"],
        "phase": state["phase"],
        "to_act": state["to_act"],
        "legal": legal_actions(state, you) if you is not None else {},
        "hand": state["hand"],
        "hand_limit": state["hand_limit"],
        "sb": state["sb"],
        "bb": state["bb"],
        "last_action": state["last_action"],
        "result": state["result"] if state["phase"] in ("pause", "over") else None,
        "seconds_left": max(0, int(state["deadline"] - now)) if state["deadline"] else 0,
        "move_seconds": state["move_seconds"],
        "draw_offer": None,
        "over": state["over"],
        "version": state["version"],
    }
