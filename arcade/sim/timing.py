"""«زمان‌سنج» — معادل دقیق ``static/arcade/timing/core.js``."""

from .base import ArcadeSimulator, register_simulator
from .rng import MASK, Mulberry32

BAR = 10000
LIMIT_TICKS = 3750
LIVES = 3


def new_zone(state: dict) -> None:
    w = max(700, 2600 - state["level"] * 80)
    state["zone"] = {"s": state["rng"].range(300, BAR - 300 - w), "w": w}
    state["speed"] = min(330, 90 + state["level"] * 7)


@register_simulator
class TimingSimulator(ArcadeSimulator):
    key = "timing"
    title_fa = "زمان‌سنج"
    emoji = "🎯"
    description_fa = "نشانگر را دقیقاً وسط ناحیه‌ی هدف متوقف کن. ناحیه کوچک‌تر و سرعت بیشتر می‌شود. (۶۰ ثانیه)"
    howto_fa = "وقتی نشانگر روی ناحیه‌ی رنگی است تپ کن."
    rules_fa = [
        "وقتی نشانگر روی ناحیه‌ی رنگی است تپ کن.",
        "وسط ناحیه ۲۰ امتیاز و بقیه‌ی آن ۱۰ امتیاز دارد.",
        "۶۰ ثانیه وقت داری و با سومین خطا بازی تمام می‌شود.",
    ]
    category = "speed"
    suggested_minutes = 3
    TICK_MS = 16
    INPUT_ARITY = 1
    MAX_DURATION_MS = 61_000
    FIXTURE_MS = 61_000

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
            "pos": 0,
            "dir": 1,
            "lives": LIVES,
            "zone": None,
            "speed": 0,
        }
        new_zone(state)
        return state

    @classmethod
    def apply_input(cls, state, event):
        if state["over"]:
            return
        z = state["zone"]
        if z["s"] <= state["pos"] <= z["s"] + z["w"]:
            d = abs(state["pos"] - (z["s"] + z["w"] // 2))
            state["score"] += 20 if d * 5 <= z["w"] else 10
            state["level"] += 1
            new_zone(state)
        else:
            state["lives"] -= 1
            if state["lives"] <= 0:
                state["over"] = True
                state["cause"] = "miss"

    @classmethod
    def step(cls, state):
        state["pos"] += state["dir"] * state["speed"]
        if state["pos"] >= BAR:
            state["pos"] = BAR
            state["dir"] = -1
        elif state["pos"] <= 0:
            state["pos"] = 0
            state["dir"] = 1
        state["tick"] += 1
        if state["tick"] >= LIMIT_TICKS:
            state["over"] = True
            state["cause"] = "time"

    @classmethod
    def demo_policy(cls, rng, skill, options=None):
        wait = [15]

        def policy(state, tick):
            if tick < wait[0]:
                return None
            z = state["zone"]
            center = z["s"] + z["w"] // 2
            tolerance = state["speed"] // 2 + 1
            if abs(state["pos"] - center) <= tolerance:
                wait[0] = tick + 12
                return []
            if rng.randint(1, 100) > skill and rng.random() < 0.02:
                wait[0] = tick + 12
                return []
            return None

        return policy
