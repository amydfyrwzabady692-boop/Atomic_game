"""«سیخ‌زن» — شبیه‌ساز سرور. معادل دقیق ``static/arcade/pins/core.js``."""

import json
from functools import lru_cache
from pathlib import Path

from .base import ArcadeSimulator, register_simulator
from .rng import MASK, Mulberry32

CIRCLE = 360000
BOTTOM = 90000
THRESHOLD = 11000
FLIGHT_TICKS = 5
PAUSE_TICKS = 45
PIN_POINTS = 10

PATTERNS = [
    [[1000, 100, 0]],
    [[1800, 100, 0], [1000, -100, 0]],
    [[1200, 100, 0], [400, 0, 0], [700, -100, 0], [400, 0, 0]],
    [[1500, 60, 0], [900, 170, 0]],
    [[2000, 160, 1], [2000, 40, 1]],
    [[900, 100, 0], [600, -140, 0], [600, 60, 0]],
    [[1500, 150, 1], [700, 0, 1], [900, -150, 1], [700, 0, 1]],
]

LEVELS_PATH = Path(__file__).resolve().parent.parent / "static" / "arcade" / "pins" / "levels.json"


@lru_cache(maxsize=1)
def load_levels() -> list[dict]:
    return json.loads(LEVELS_PATH.read_text(encoding="utf-8"))


def load_level(state: dict) -> None:
    index = state["level"]
    rng = Mulberry32((state["seed"] + index * 7919) & MASK)
    angle = rng.int(360) * 1000
    levels = state["levels"]
    pre: list[int] = []
    if index < len(levels):
        raw = levels[index]
        pre = [a * 1000 for a in raw["pre"]]
        lv = {"pins": raw["pins"], "speed": raw["speed"], "pattern": raw["pattern"]}
    else:
        pins = 7 + rng.int(6)
        count = rng.int(5)
        used = set()
        while len(pre) < count:
            slot = rng.int(18)
            if slot not in used:
                used.add(slot)
                pre.append(slot * 20000)
        speed = 1500 + min(index, 120) * 10 + rng.int(500)
        lv = {"pins": pins, "speed": speed, "pattern": PATTERNS[rng.int(len(PATTERNS))]}
    lv["total"] = sum(seg[0] for seg in lv["pattern"])
    state["lv"] = lv
    state["angle"] = angle
    state["pins"] = pre
    state["remaining"] = lv["pins"]
    state["flights"] = []
    state["ltick"] = 0


def speed_at(lv: dict, ltick: int, tick_ms: int) -> int:
    pattern = lv["pattern"]
    n = len(pattern)
    ms = (ltick * tick_ms) % lv["total"]
    acc = 0
    for i, seg in enumerate(pattern):
        if ms < acc + seg[0]:
            pct = seg[1]
            if seg[2]:
                prev = pattern[(i + n - 1) % n][1]
                pct = prev + ((seg[1] - prev) * (ms - acc)) // seg[0]
            return (lv["speed"] * pct) // 100
        acc += seg[0]
    return lv["speed"]


@register_simulator
class PinsSimulator(ArcadeSimulator):
    key = "pins"
    title_fa = "سیخ‌زن"
    emoji = "📍"
    description_fa = "سیخ‌ها را به دایره‌ی چرخان بزن، بدون اینکه به سیخ دیگری بخورند."
    howto_fa = "تپ کن تا سیخ پرتاب شود؛ به سیخ‌های دیگر نخورد!"
    rules_fa = [
        "تپ کن تا سیخ به دایره‌ی چرخان پرتاب شود.",
        "هر سیخ امتیاز دارد؛ با تمام شدن سیخ‌ها مرحله‌ی بعد می‌آید.",
        "برخورد با سیخ دیگر یعنی پایان بازی.",
    ]
    category = "stage"
    suggested_minutes = 5
    TICK_MS = 16
    INPUT_ARITY = 1

    @classmethod
    def demo_policy(cls, rng, skill, options=None):
        """وقتی تپ می‌کند که سیخ با حاشیه‌ی امن بنشیند؛ با مهارت کمتر گاهی بی‌هوا تپ می‌کند."""
        wait = [0]

        def policy(state, tick):
            if state["pause"] > 0 or state["flights"] or state["remaining"] <= 0:
                return None
            if tick < wait[0]:
                return None
            if rng.randint(1, 100) > skill and rng.random() < 0.05:
                wait[0] = tick + 8
                return []
            angle = state["angle"]
            for i in range(FLIGHT_TICKS + 1):
                angle += speed_at(state["lv"], state["ltick"] + i, cls.TICK_MS)
            local = (BOTTOM - angle) % CIRCLE
            for pin in state["pins"]:
                d = abs(pin - local)
                if min(d, CIRCLE - d) < THRESHOLD + 2500:
                    return None
            wait[0] = tick + 8  # فاصله‌ی انسانی بین دو تپ
            return []

        return policy

    @classmethod
    def new_state(cls, seed: int, config: dict) -> dict:
        state = {
            "seed": seed & MASK,
            "levels": load_levels(),
            "tick": 0,
            "over": False,
            "cause": "",
            "score": 0,
            "level": 0,
            "pause": 0,
        }
        load_level(state)
        return state

    @classmethod
    def apply_input(cls, state: dict, event: list) -> None:
        if state["over"] or state["pause"] > 0:
            return
        if state["remaining"] - len(state["flights"]) > 0:
            state["flights"].append(state["tick"] + FLIGHT_TICKS)

    @classmethod
    def _land(cls, state: dict) -> None:
        local = (BOTTOM - state["angle"]) % CIRCLE
        for pin in state["pins"]:
            d = abs(pin - local)
            if d > CIRCLE - d:
                d = CIRCLE - d
            if d < THRESHOLD:
                state["over"] = True
                state["cause"] = "hit"
                return
        state["pins"].append(local)
        state["remaining"] -= 1
        state["score"] += PIN_POINTS
        if state["remaining"] == 0:
            secs = (state["ltick"] * cls.TICK_MS) // 1000
            bonus = max(0, 20 - max(0, secs - state["lv"]["pins"]))
            state["level"] += 1
            state["score"] += 100 + 20 * state["level"] + bonus
            state["pause"] = PAUSE_TICKS
            state["flights"] = []

    @classmethod
    def step(cls, state: dict) -> None:
        if state["pause"] > 0:
            state["pause"] -= 1
            if state["pause"] == 0:
                load_level(state)
            state["tick"] += 1
            return
        state["angle"] = (state["angle"] + speed_at(state["lv"], state["ltick"], cls.TICK_MS)) % CIRCLE
        while state["flights"] and state["flights"][0] <= state["tick"] and not state["over"] and state["pause"] == 0:
            state["flights"].pop(0)
            cls._land(state)
        state["ltick"] += 1
        state["tick"] += 1
