"""کارت‌ها و ارزیابی دست پوکر (تگزاس هولدم): بهترین دست ۵ کارتی از ۷ کارت.

کارت‌ها رشته‌ی دوحرفی‌اند: رتبه (``23456789TJQKA``) و خال (``s h d c``)، مثل ``"As"`` یا ``"Td"``.
"""

import random
from collections import Counter
from itertools import combinations

RANKS = "23456789TJQKA"
SUITS = "shdc"
RANK_VALUE = {r: i for i, r in enumerate(RANKS, start=2)}
SUIT_SYMBOL = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}
RANK_LABEL = {"T": "10"}

HAND_NAMES = (
    "کارت بالا",
    "یک جفت",
    "دو جفت",
    "سه‌تایی",
    "استریت",
    "فلاش",
    "فول هاوس",
    "چهارتایی",
    "استریت فلاش",
)


def full_deck() -> list[str]:
    return [r + s for r in RANKS for s in SUITS]


def shuffled_deck(seed: str) -> list[str]:
    deck = full_deck()
    random.Random(seed).shuffle(deck)
    return deck


def label(card: str) -> str:
    """نمایش کارت برای متن پیام: ``A♠``، ``10♥``."""
    return RANK_LABEL.get(card[0], card[0]) + SUIT_SYMBOL[card[1]]


def _straight_high(values: list[int]) -> int:
    """بالاترین کارت استریت در این مقادیر (با A-2-3-4-5)، یا ۰."""
    distinct = sorted(set(values), reverse=True)
    if 14 in distinct:
        distinct.append(1)
    run = 1
    for a, b in zip(distinct, distinct[1:], strict=False):
        run = run + 1 if a - b == 1 else 1
        if run >= 5:
            return b + 4
    return 0


def rank5(cards: list[str]) -> tuple:
    """ارزش یک دست ۵ کارتی؛ تاپل بزرگ‌تر یعنی دست قوی‌تر. عنصر اول دسته‌ی دست (۰ تا ۸) است."""
    values = sorted((RANK_VALUE[c[0]] for c in cards), reverse=True)
    flush = len({c[1] for c in cards}) == 1
    straight = _straight_high(values)
    counts = Counter(values)
    # مرتب بر اساس تعداد تکرار و بعد ارزش: [(تعداد، ارزش), ...]
    groups = sorted(((n, v) for v, n in counts.items()), reverse=True)
    ordered = [v for n, v in groups for _ in range(n)]
    if straight and flush:
        return (8, straight)
    if groups[0][0] == 4:
        return (7, *ordered)
    if groups[0][0] == 3 and groups[1][0] == 2:
        return (6, *ordered)
    if flush:
        return (5, *values)
    if straight:
        return (4, straight)
    if groups[0][0] == 3:
        return (3, *ordered)
    if groups[0][0] == 2 and groups[1][0] == 2:
        return (2, *ordered)
    if groups[0][0] == 2:
        return (1, *ordered)
    return (0, *values)


def best_hand(cards: list[str]) -> tuple[tuple, list[str]]:
    """بهترین دست ۵ کارتی از بین ۵ تا ۷ کارت: (ارزش، کارت‌ها)."""
    best = None
    for combo in combinations(cards, 5):
        score = rank5(list(combo))
        if best is None or score > best[0]:
            best = (score, list(combo))
    return best


def hand_name(score: tuple) -> str:
    return HAND_NAMES[score[0]]


RANK_NAMES = {14: "آس", 13: "شاه", 12: "بی‌بی", 11: "سرباز", 10: "۱۰", 9: "۹", 8: "۸", 7: "۷", 6: "۶", 5: "۵", 4: "۴", 3: "۳", 2: "۲"}


def describe(score: tuple) -> str:
    """نام کامل دست مثل میزهای واقعی: «جفت آس»، «دو جفت شاه و ۷»، «فول هاوس: سه ۸ و دو شاه»، «رویال فلاش»."""
    category, values = score[0], score[1:]
    top = RANK_NAMES[values[0]]
    if category == 8:
        return "رویال فلاش" if values[0] == 14 else f"استریت فلاش تا {top}"
    if category == 7:
        return f"چهارتایی {top}"
    if category == 6:
        return f"فول هاوس: سه {top} و دو {RANK_NAMES[values[3]]}"
    if category == 5:
        return f"فلاش {top}"
    if category == 4:
        return f"استریت تا {top}"
    if category == 3:
        return f"سه‌تایی {top}"
    if category == 2:
        return f"دو جفت {top} و {RANK_NAMES[values[2]]}"
    if category == 1:
        return f"جفت {top}"
    return f"کارت بالا {top}"


def describe_cards(cards: list[str]) -> str:
    """بهترین دست بازیکن با کارت‌های فعلی؛ قبل از فلاپ فقط دو کارت دست (مثل «جفت آس» یا «آس و شاه هم‌خال»)."""
    if len(cards) >= 5:
        return describe(best_hand(cards)[0])
    if len(cards) != 2:
        return ""
    high, low = sorted((RANK_VALUE[c[0]] for c in cards), reverse=True)
    if high == low:
        return f"جفت {RANK_NAMES[high]}"
    suited = " هم‌خال" if cards[0][1] == cards[1][1] else ""
    return f"{RANK_NAMES[high]} و {RANK_NAMES[low]}{suited}"
