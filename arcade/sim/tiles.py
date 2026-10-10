"""«کاشی‌های سیاه» — معادل دقیق ``static/arcade/tiles/core.js``."""

from .base import ArcadeSimulator, register_simulator
from .rng import MASK, Mulberry32

ROW_H = 1600
VISIBLE_ROWS = 4
START = 2 * ROW_H
TARGET = 50
FIFTY_LIMIT_MS = 60000


def ensure_rows(state: dict) -> None:
    while len(state["cols"]) < state["hits"] + 8:
        state["cols"].append(state["rng"].int(4))


def speed_for(hits: int) -> int:
    return min(130, 40 + (hits * 2) // 5)


def row_bottom(state: dict, k: int) -> int:
    return START + k * ROW_H - state["offset"]


@register_simulator
class TilesSimulator(ArcadeSimulator):
    key = "tiles"
    title_fa = "کاشی‌های سیاه"
    emoji = "🎹"
    description_fa = "فقط کاشی‌های تیره را به ترتیب بزن. تپ روی خانه‌ی خالی یا جا انداختن کاشی یعنی باخت."
    howto_fa = "پایین‌ترین کاشی تیره را بزن؛ خانه‌ی خالی را نزن!"
    category = "speed"
    suggested_minutes = 3
    variant_title_fa = "حالت بازی"
    variants = {"endless": "♾ بی‌پایان", "fifty": "⏱ ۵۰ کاشی با کمترین زمان"}
    TICK_MS = 16
    INPUT_ARITY = 2
    FIXTURE_MS = 60_000

    @classmethod
    def new_state(cls, seed, config):
        state = {
            "seed": seed & MASK,
            "rng": Mulberry32(seed),
            "tick": 0,
            "over": False,
            "cause": "",
            "score": 0,
            "level": 0,
            "mode": "fifty" if config.get("variant") == "fifty" else "endless",
            "hits": 0,
            "offset": 0,
            "started": False,
            "startTick": 0,
            "cols": [],
        }
        ensure_rows(state)
        return state

    @classmethod
    def apply_input(cls, state, event):
        col = event[1]
        if state["over"] or col not in (0, 1, 2, 3):
            return
        if state["mode"] == "endless" and row_bottom(state, state["hits"]) >= VISIBLE_ROWS * ROW_H:
            return
        if col != state["cols"][state["hits"]]:
            state["over"] = True
            state["cause"] = "wrong"
            return
        if not state["started"]:
            state["started"] = True
            state["startTick"] = state["tick"]
        state["hits"] += 1
        ensure_rows(state)
        if state["mode"] == "fifty":
            state["offset"] = state["hits"] * ROW_H
            state["score"] = state["hits"] * 10
            if state["hits"] >= TARGET:
                elapsed = (state["tick"] - state["startTick"]) * cls.TICK_MS
                state["score"] = 1000 + max(0, (30000 - elapsed) // 10)
                state["over"] = True
                state["cause"] = "done"
        else:
            state["score"] += 1
            state["level"] = state["hits"] // 10

    @classmethod
    def step(cls, state):
        if state["started"]:
            if state["mode"] == "endless":
                state["offset"] += speed_for(state["hits"])
                if row_bottom(state, state["hits"]) + ROW_H <= 0:
                    state["over"] = True
                    state["cause"] = "miss"
            elif (state["tick"] - state["startTick"]) * cls.TICK_MS >= FIFTY_LIMIT_MS:
                state["over"] = True
                state["cause"] = "time"
        state["tick"] += 1

    @classmethod
    def random_payload(cls, rng, state):
        return [rng.randint(0, 3)]

    @classmethod
    def demo_policy(cls, rng, skill, options=None):
        wait = [20]
        gap = 7 if skill >= 100 else 9 if skill >= 97 else 14

        def policy(state, tick):
            if tick < wait[0]:
                return None
            bottom = row_bottom(state, state["hits"])
            if state["mode"] == "endless" and bottom >= ROW_H * 5 // 2:
                return None
            wait[0] = tick + gap
            col = state["cols"][state["hits"]]
            if skill < 95 and rng.random() < 0.01:
                col = (col + 1) % 4
            return [col]

        return policy
