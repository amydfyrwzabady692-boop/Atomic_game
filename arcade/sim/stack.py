"""«برج‌ساز» — معادل دقیق ``static/arcade/stack/core.js``."""

from .base import ArcadeSimulator, register_simulator
from .rng import MASK

FIELD = 3600
BASE_W = 1800
PERFECT = 60


def spawn(state: dict) -> None:
    prev = state["blocks"][-1]
    count = len(state["blocks"]) - 1
    w = prev["w"]
    even = count % 2 == 0
    state["cur"] = {
        "w": w,
        "x": -(w // 2) if even else FIELD - w // 2,
        "dir": 1 if even else -1,
        "speed": 36 + min(count, 60),
    }


@register_simulator
class StackSimulator(ArcadeSimulator):
    key = "stack"
    title_fa = "برج‌ساز"
    emoji = "🗼"
    description_fa = "بلوک‌ها را دقیق روی هم بینداز؛ هر چه بیرون بزند بریده می‌شود."
    howto_fa = "وقتی بلوک دقیقاً بالای برج است تپ کن."
    rules_fa = [
        "وقتی طبقه دقیقاً بالای برج است تپ کن.",
        "هر طبقه امتیاز دارد؛ چیدن دقیقِ پشت‌سرهم امتیاز بیشتری می‌دهد.",
        "اگر طبقه کاملاً بیرون بیفتد بازی تمام می‌شود.",
    ]
    category = "skill"
    suggested_minutes = 3
    TICK_MS = 16
    INPUT_ARITY = 1
    FIXTURE_MS = 60_000

    @classmethod
    def new_state(cls, seed, config):
        state = {
            "seed": seed & MASK,
            "tick": 0,
            "over": False,
            "cause": "",
            "score": 0,
            "level": 0,
            "combo": 0,
            "blocks": [{"x": (FIELD - BASE_W) // 2, "w": BASE_W}],
            "cur": None,
        }
        spawn(state)
        return state

    @classmethod
    def apply_input(cls, state, event):
        if state["over"]:
            return
        cur, prev = state["cur"], state["blocks"][-1]
        diff = cur["x"] - prev["x"]
        if abs(diff) <= PERFECT:
            state["combo"] += 1
            state["blocks"].append({"x": prev["x"], "w": prev["w"]})
            state["score"] += 10 + min(state["combo"], 10) * 5
        else:
            left = max(cur["x"], prev["x"])
            right = min(cur["x"] + cur["w"], prev["x"] + prev["w"])
            overlap = right - left
            if overlap <= 0:
                state["over"] = True
                state["cause"] = "miss"
                return
            state["combo"] = 0
            state["blocks"].append({"x": left, "w": overlap})
            state["score"] += 10
        state["level"] = len(state["blocks"]) - 1
        spawn(state)

    @classmethod
    def step(cls, state):
        cur = state["cur"]
        lo, hi = -(cur["w"] // 2), FIELD - cur["w"] // 2
        cur["x"] += cur["dir"] * cur["speed"]
        if cur["x"] >= hi:
            cur["x"] = hi
            cur["dir"] = -1
        elif cur["x"] <= lo:
            cur["x"] = lo
            cur["dir"] = 1
        state["tick"] += 1

    @classmethod
    def demo_policy(cls, rng, skill, options=None):
        wait = [10]

        def policy(state, tick):
            if tick < wait[0]:
                return None
            cur, prev = state["cur"], state["blocks"][-1]
            # با مهارت کمتر، خطای قابل‌قبول بیشتر می‌شود (بلوک بریده می‌شود)
            tolerance = cur["speed"] // 2 + 1 + (100 - skill) * 12
            if abs(cur["x"] - prev["x"]) <= tolerance:
                wait[0] = tick + 12
                return []
            return None

        return policy
