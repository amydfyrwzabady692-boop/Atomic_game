"""حکم چهارنفره (دو تیم دونفره) برای میز گرافیکی مینی‌اپ.

مثل ``games.poker.live``: وضعیت یک dict قابل‌ذخیره در JSON است، همه‌ی حرکت‌ها همین‌جا اعتبارسنجی می‌شوند و
ماژول به جنگو یا تلگرام وابسته نیست. کارت‌ها همان رشته‌های دوحرفی پوکرند (``"As"``، ``"Td"``).

قوانین (حکم رایج ایرانی):
- چهار نفر در دو تیم؛ یارها روبه‌روی هم‌اند: صندلی‌های ۰ و ۲ تیم اول، ۱ و ۳ تیم دوم. نوبت خلاف عقربه‌های ساعت
  (به سمت راست) می‌چرخد؛ در کد نفر بعدی ``(seat + 1) % 4`` است.
- حاکم اول: از یک دسته‌ی بُرخورده کارت‌ها رو و یکی‌یکی به ترتیب صندلی‌ها داده می‌شود تا اولین آس بیاید؛ صاحب آن آس
  حاکم دور اول است (``draw`` همین کارت‌ها را برای نمایش نگه می‌دارد).
- هر دور: دسته‌ی ۵۲تایی بُر می‌خورد؛ اول به هر نفر ۵ کارت (از حاکم)، حاکم از روی همین ۵ کارت «حکم» (خال برنده) را
  انتخاب می‌کند، بعد بقیه‌ی کارت‌ها چهارتا چهارتا پخش می‌شود تا هر نفر ۱۳ کارت داشته باشد.
- حاکم دست اول را باز می‌کند. هر کس باید از خال زمین بدهد؛ اگر ندارد هر کارتی (حکم یا خال دیگر). بالاترین حکم، وگرنه
  بالاترین کارت خال زمین، دست را می‌برد و برنده‌ی دست، دست بعد را باز می‌کند. ترتیب: آس، شاه، بی‌بی، سرباز، ۱۰ … ۲.
- تیمی که زودتر ۷ دست ببرد دور را برده است (بقیه‌ی دست‌ها بازی نمی‌شود). امتیاز دور: ۱؛ اگر حریف هیچ دستی نبرده باشد
  «کُت» = ۲؛ و اگر تیم حاکم کُت شود («حاکم‌کُت») = ۳.
- اگر تیم حاکم دور را برد، حاکم همان می‌ماند؛ وگرنه حاکم نفر بعدی (سمت راست حاکم) می‌شود.
- بازی تا رسیدن یک تیم به امتیاز هدف (``target``، پیش‌فرض ۷) ادامه دارد.

مهلت هر حرکت ``MOVE_SECONDS`` و انتخاب حکم ``TRUMP_SECONDS`` است. اگر وقت کسی تمام شود، کارتی مجاز (کوچک‌ترین) به جایش
بازی می‌شود و کسی که دو نوبت پشت هم وقتش تمام شده «غایب» حساب می‌شود و تا وقتی خودش حرکتی نکند با مهلت کوتاه
``AWAY_SECONDS`` به جایش بازی می‌شود تا بقیه منتظر نمانند. ترک بازی یعنی باخت تیم همان نفر.
"""

import time

from games.chess.live import LiveError
from games.poker.cards import RANK_VALUE, SUITS, shuffled_deck

PLAYERS = 4
TRICKS_TO_WIN = 7
HAND_SIZE = 13
FIRST_DEAL = 5
MOVE_SECONDS = 25
TRUMP_SECONDS = 30
AWAY_SECONDS = 6
AWAY_AFTER = 2  # چند وقت‌تمام‌شدن پشت هم تا «غایب»
PAUSE_SECONDS = 6  # نمایش نتیجه‌ی دور قبل از پخش دور بعد
TARGETS = (3, 5, 7)
DEFAULT_TARGET = 7
SUIT_NAMES = {"s": "پیک", "h": "دل", "d": "خشت", "c": "گشنیز"}
SUIT_SYMBOL = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}


# ------------------------------------------------------------------ ابزار
def team_of(seat: int) -> int:
    return seat % 2


def partner_of(seat: int) -> int:
    return (seat + 2) % PLAYERS


def next_seat(seat: int) -> int:
    return (seat + 1) % PLAYERS


def suit(card: str) -> str:
    return card[1]


def value(card: str) -> int:
    return RANK_VALUE[card[0]]


def players(state: dict) -> dict:
    return {f"s{i}": uid for i, uid in enumerate(state["seats"])}


def seat_of(state: dict, user_id) -> int | None:
    try:
        return state["seats"].index(user_id)
    except ValueError:
        return None


def sort_hand(cards: list[str], trump: str = "") -> list[str]:
    """مرتب برای نمایش: خال‌ها کنار هم (حکم اول) و در هر خال از بزرگ به کوچک."""
    order = {s: i for i, s in enumerate(([trump] if trump else []) + [s for s in "shcd" if s != trump])}
    return sorted(cards, key=lambda c: (order[suit(c)], -value(c)))


def trick_winner(plays: list, trump: str) -> int:
    """صندلی برنده‌ی یک دست کامل: بالاترین حکم، وگرنه بالاترین کارت خال زمین."""
    best_seat, best = plays[0]
    for seat, card in plays[1:]:
        if suit(card) == suit(best):
            # هم‌خالِ بهترین کارت فعلی (خال زمین یا حکم): بزرگ‌تر می‌برد
            if value(card) > value(best):
                best_seat, best = seat, card
        elif suit(card) == trump:
            # اولین حکم روی خال زمین (اگر بهترین فعلی حکم بود، شرط بالا آن را گرفته بود)
            best_seat, best = seat, card
    return best_seat


# ------------------------------------------------------------------ ساخت میز
def first_hakem(seed: str) -> tuple[int, list]:
    """تعیین حاکم اول: کارت‌ها یکی‌یکی رو به ترتیب صندلی‌ها تا اولین آس."""
    deck = shuffled_deck(f"{seed}:hakem")
    draw = []
    for i, card in enumerate(deck):
        seat = i % PLAYERS
        draw.append([seat, card])
        if card[0] == "A":
            return seat, draw
    return 0, draw  # هرگز: در هر ۵۲ کارت چهار آس هست


def new_state(user_ids: list[int], now: float, seed: str = "", target: int = DEFAULT_TARGET) -> dict:
    if len(user_ids) != PLAYERS:
        raise ValueError("حکم دقیقاً ۴ بازیکن لازم دارد")
    if target not in TARGETS:
        target = DEFAULT_TARGET
    seed = seed or str(now)
    hakem, draw = first_hakem(seed)
    state = {
        "game": "hokm",
        "seats": list(user_ids),
        "seed": seed,
        "target": target,
        "points": [0, 0],
        "round": 0,
        "hakem": hakem,
        "draw": draw,
        "trump": "",
        "hands": [[] for _ in range(PLAYERS)],
        "pending": [],
        "phase": "trump",
        "turn": hakem,
        "leader": hakem,
        "trick": [],
        "trick_no": 0,
        "tricks": [0, 0],
        "last_trick": None,
        "won": [[] for _ in range(PLAYERS)],  # کارت‌های دست‌های بُرده‌ی هر صندلی در همین دور (برای شمارش)
        "result": None,
        "history": [],
        "misses": [0] * PLAYERS,
        "away": [False] * PLAYERS,
        "left": [False] * PLAYERS,
        "deadline": None,
        "move_seconds": MOVE_SECONDS,
        "trump_seconds": TRUMP_SECONDS,
        "last_action": None,
        "over": None,
        "version": 1,
    }
    _start_round(state, now)
    return state


def _deadline(state: dict, seat: int, now: float, seconds: float) -> float:
    return now + (AWAY_SECONDS if state["away"][seat] else seconds)


def _start_round(state: dict, now: float) -> None:
    """دور تازه: بُر، ۵ کارت به هر نفر از حاکم، و انتظار برای انتخاب حکم."""
    state["round"] += 1
    deck = shuffled_deck(f"{state['seed']}:{state['round']}")
    hakem = state["hakem"]
    order = [(hakem + i) % PLAYERS for i in range(PLAYERS)]
    hands = [[] for _ in range(PLAYERS)]
    for seat in order:
        for _ in range(FIRST_DEAL):
            hands[seat].append(deck.pop())
    state["hands"] = hands
    state["pending"] = deck  # بقیه بعد از انتخاب حکم چهارتا چهارتا پخش می‌شود
    state["trump"] = ""
    state["phase"] = "trump"
    state["turn"] = hakem
    state["leader"] = hakem
    state["trick"] = []
    state["trick_no"] = 0
    state["tricks"] = [0, 0]
    state["last_trick"] = None
    state["won"] = [[] for _ in range(PLAYERS)]
    state["result"] = None
    state["deadline"] = _deadline(state, hakem, now, state.get("trump_seconds", TRUMP_SECONDS))


def _deal_rest(state: dict) -> None:
    deck = state["pending"]
    hakem = state["hakem"]
    order = [(hakem + i) % PLAYERS for i in range(PLAYERS)]
    for _ in range(2):  # دو دور، هر بار ۴ کارت به هر نفر
        for seat in order:
            for _ in range(4):
                state["hands"][seat].append(deck.pop())
    state["pending"] = []


# ------------------------------------------------------------------ قانون‌ها
def legal_cards(state: dict, seat: int) -> list[str]:
    """کارت‌هایی که این صندلی الان می‌تواند بازی کند (اگر نوبتش باشد)."""
    if state["over"] or state["phase"] != "play" or state["turn"] != seat:
        return []
    hand = state["hands"][seat]
    if not state["trick"]:
        return list(hand)
    led = suit(state["trick"][0][1])
    follow = [c for c in hand if suit(c) == led]
    return follow or list(hand)


def best_trump(cards: list[str]) -> str:
    """حکمی که به جای حاکمِ غایب انتخاب می‌شود: خالی که بیشترین کارت را دارد (در تساوی، کارت‌های بزرگ‌تر)."""
    score = {s: (0, 0) for s in SUITS}
    for card in cards:
        count, total = score[suit(card)]
        score[suit(card)] = (count + 1, total + value(card))
    return max(SUITS, key=lambda s: (score[s], s))


def auto_card(state: dict, seat: int) -> str:
    """کارتی که به جای بازیکنِ دیر یا غایب بازی می‌شود: کوچک‌ترین کارت مجاز (حکم فقط وقتی چاره نیست)."""
    legal = legal_cards(state, seat)
    trump = state["trump"]
    plain = [c for c in legal if suit(c) != trump] or legal
    return min(plain, key=value)


def _mark(state: dict, seat: int, timeout: bool) -> None:
    if timeout:
        state["misses"][seat] += 1
        if state["misses"][seat] >= AWAY_AFTER:
            state["away"][seat] = True
    else:
        state["misses"][seat] = 0
        state["away"][seat] = False


def _choose_trump(state: dict, seat: int, chosen: str, now: float, timeout: bool = False) -> None:
    state["trump"] = chosen
    _mark(state, seat, timeout)
    state["last_action"] = {"kind": "trump", "seat": seat, "suit": chosen, "timeout": timeout}
    _deal_rest(state)
    state["phase"] = "play"
    state["turn"] = state["hakem"]
    state["leader"] = state["hakem"]
    state["deadline"] = _deadline(state, state["hakem"], now, state["move_seconds"])


def _play(state: dict, seat: int, card: str, now: float, timeout: bool = False) -> None:
    state["hands"][seat].remove(card)
    state["trick"].append([seat, card])
    _mark(state, seat, timeout)
    state["last_action"] = {"kind": "play", "seat": seat, "card": card, "timeout": timeout}
    if len(state["trick"]) < PLAYERS:
        state["turn"] = next_seat(seat)
        state["deadline"] = _deadline(state, state["turn"], now, state["move_seconds"])
        return
    winner = trick_winner(state["trick"], state["trump"])
    state["tricks"][team_of(winner)] += 1
    state["won"][winner].extend(card for _, card in state["trick"])
    state["trick_no"] += 1
    state["last_trick"] = {"plays": state["trick"], "winner": winner, "no": state["trick_no"]}
    state["trick"] = []
    if max(state["tricks"]) >= TRICKS_TO_WIN:
        _end_round(state, now)
        return
    state["turn"] = winner
    state["leader"] = winner
    state["deadline"] = _deadline(state, winner, now, state["move_seconds"])


def _end_round(state: dict, now: float) -> None:
    tricks = state["tricks"]
    winner = 0 if tricks[0] >= TRICKS_TO_WIN else 1
    loser = 1 - winner
    hakem_team = team_of(state["hakem"])
    kot = ""
    gained = 1
    if tricks[loser] == 0:
        kot = "kot" if winner == hakem_team else "hakem_kot"
        gained = 2 if kot == "kot" else 3
    state["points"][winner] += gained
    result = {
        "round": state["round"],
        "winner_team": winner,
        "points": gained,
        "kot": kot,
        "tricks": list(tricks),
        "hakem": state["hakem"],
        "trump": state["trump"],
    }
    state["result"] = result
    state["history"] = (state["history"] + [result])[-20:]
    if winner != hakem_team:
        state["hakem"] = next_seat(state["hakem"])  # حکم به نفر بعدی (از تیم برنده) می‌رسد
    state["turn"] = None
    if state["points"][winner] >= state["target"]:
        _finish(state, "points", winner)
        return
    state["phase"] = "pause"
    state["deadline"] = now + PAUSE_SECONDS


def _finish(state: dict, reason: str, winner_team: int, **extra) -> None:
    state["over"] = {"reason": reason, "winner_team": winner_team, "winner": None, **extra}
    state["phase"] = "over"
    state["turn"] = None
    state["deadline"] = None


# ------------------------------------------------------------------ حرکت‌ها
def check_timeout(state: dict, now: float) -> bool:
    """پایان مهلت: بین دو دور، دور بعد پخش می‌شود؛ وگرنه حکم یا کارتی مجاز به جای نفرِ نوبت انتخاب می‌شود."""
    if state["over"] or state["deadline"] is None or now <= state["deadline"]:
        return False
    if state["phase"] == "pause":
        _start_round(state, now)
    elif state["phase"] == "trump":
        seat = state["turn"]
        _choose_trump(state, seat, best_trump(state["hands"][seat]), now, timeout=True)
    elif state["phase"] == "play":
        seat = state["turn"]
        _play(state, seat, auto_card(state, seat), now, timeout=True)
    else:
        return False
    state["version"] += 1
    return True


def _actor(state: dict, user_id: int, now: float, phase: str) -> int:
    if check_timeout(state, now):
        raise LiveError("timeout")
    if state["over"]:
        raise LiveError("game_over")
    seat = seat_of(state, user_id)
    if seat is None:
        raise LiveError("not_a_player")
    if state["phase"] != phase or state["turn"] != seat:
        raise LiveError("not_your_turn")
    return seat


def choose_trump(state: dict, user_id: int, chosen, now: float) -> None:
    """حاکم خال حکم را انتخاب می‌کند (``s h d c``)."""
    seat = _actor(state, user_id, now, "trump")
    if not isinstance(chosen, str) or len(chosen) != 1 or chosen not in SUITS:
        raise LiveError("illegal_move")
    _choose_trump(state, seat, chosen, now)
    state["version"] += 1


def play(state: dict, user_id: int, card, now: float) -> None:
    """بازی یک کارت از دست. باید از خال زمین باشد، مگر بازیکن آن خال را نداشته باشد."""
    seat = _actor(state, user_id, now, "play")
    if not isinstance(card, str) or card not in legal_cards(state, seat):
        raise LiveError("illegal_move")
    _play(state, seat, card, now)
    state["version"] += 1


def resign(state: dict, user_id: int, now: float | None = None) -> None:
    """ترک بازی: بازی همان لحظه تمام می‌شود و تیمِ کسی که رفت می‌بازد."""
    seat = seat_of(state, user_id)
    if seat is None:
        raise LiveError("not_a_player")
    if state["over"]:
        raise LiveError("game_over")
    state["left"][seat] = True
    _finish(state, "left", 1 - team_of(seat), left_seat=seat)
    state["version"] += 1


def apply_move(state: dict, user_id: int, src: int, dst: int, promo: str, now: float):
    raise LiveError("bad_action")  # حکم حرکت خانه‌ای ندارد؛ از ``play`` و ``choose_trump`` استفاده می‌شود


def offer_draw(state: dict, user_id: int) -> bool:
    raise LiveError("bad_action")


def standings(state: dict) -> list[tuple[int, int]]:
    """(کاربر، امتیاز) برای تقسیم جایزه: هر نفر امتیاز تیمش را می‌گیرد. تیم برنده دست‌کم امتیاز هدف را دارد (حتی اگر
    با رفتن حریف برده باشد) تا همیشه بالاتر از تیم بازنده بنشیند و دو یار برنده جایزه را نصف‌نصف ببرند."""
    over = state["over"] or {}
    winner = over.get("winner_team")
    scores = list(state["points"])
    if winner is not None:
        scores[winner] = max(scores[winner], state["target"])
        scores[1 - winner] = min(scores[1 - winner], scores[winner] - 1)
    return [(uid, scores[team_of(i)]) for i, uid in enumerate(state["seats"])]


# ------------------------------------------------------------------ نمایش
def view(state: dict, viewer_id: int | None, now: float | None = None) -> dict:
    """وضعیت برای یک بیننده: فقط کارت‌های خود او؛ از بقیه فقط تعداد کارت."""
    now = time.time() if now is None else now
    you = seat_of(state, viewer_id) if viewer_id is not None else None
    trump = state["trump"]
    seats = []
    for i in range(PLAYERS):
        seats.append(
            {
                "seat": i,
                "side": f"s{i}",
                "team": team_of(i),
                "count": len(state["hands"][i]),
                "hakem": i == state["hakem"],
                "away": state["away"][i],
                "left": state["left"][i],
                "tricks": len(state["won"][i]) // PLAYERS,
            }
        )
    hand = []
    if you is not None:
        if state["phase"] == "trump" and you != state["hakem"]:
            hand = sort_hand(state["hands"][you])  # هنوز حکم معلوم نیست
        else:
            hand = sort_hand(state["hands"][you], trump)
    left = max(0.0, state["deadline"] - now) if state["deadline"] else 0.0
    turn = state["turn"]
    seconds = state["trump_seconds"] if state["phase"] == "trump" else state["move_seconds"]
    return {
        "game": "hokm",
        "seats": seats,
        "you": you,
        "hand": hand,
        "legal": sort_hand(legal_cards(state, you), trump) if you is not None else [],
        "phase": state["phase"],
        "turn": turn,
        "hakem": state["hakem"],
        "trump": trump,
        "trick": state["trick"],
        "leader": state["leader"],
        "last_trick": state["last_trick"],
        "trick_no": state["trick_no"],
        "tricks": state["tricks"],
        "points": state["points"],
        "target": state["target"],
        "round": state["round"],
        "result": state["result"],
        "history": state["history"][-8:],
        "draw": state["draw"] if state["round"] == 1 else [],
        "last_action": state["last_action"],
        "seconds_left": int(left),
        "left_ms": int(left * 1000),
        "move_seconds": AWAY_SECONDS if turn is not None and state["away"][turn] else seconds,
        "over": state["over"],
        "version": state["version"],
    }
