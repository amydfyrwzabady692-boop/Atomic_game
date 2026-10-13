"""«موش‌زن» — معادل دقیق ``static/arcade/whack/core.js``."""

from .base import ArcadeSimulator, register_simulator
from .rng import MASK, Mulberry32

LIMIT_TICKS = 3750
HOLES = 9


@register_simulator
class WhackSimulator(ArcadeSimulator):
    key = "whack"
    title_fa = "موش‌زن"
    emoji = "🔨"
    description_fa = "شخصیت‌هایی که از سوراخ بیرون می‌آیند را بزن؛ بمب‌دارها را نزن! (۶۰ ثانیه)"
    howto_fa = "روی شخصیت‌ها بزن؛ به بمب‌دارها دست نزن."
    rules_fa = [
        "روی شخصیت‌هایی که از سوراخ بیرون می‌آیند بزن.",
        "هر ضربه ۱۰ امتیاز و شخصیت ویژه ۳۰ امتیاز دارد؛ بمب ۱۵ امتیاز کم می‌کند.",
        "۶۰ ثانیه وقت داری.",
    ]
    category = "speed"
    suggested_minutes = 3
    TICK_MS = 16
    INPUT_ARITY = 2
    MAX_DURATION_MS = 61_000
    FIXTURE_MS = 61_000

    @classmethod
    def new_state(cls, seed, config):
        return {
            "seed": seed & MASK,
            "rng": Mulberry32(seed),
            "tick": 0,
            "over": False,
            "cause": "",
            "score": 0,
            "level": 0,
            "hits": 0,
            "holes": [{"type": 0, "until": 0, "born": 0} for _ in range(HOLES)],
            "nextSpawn": 30,
        }

    @classmethod
    def apply_input(cls, state, event):
        index = event[1]
        if state["over"] or not 0 <= index < HOLES:
            return
        hole = state["holes"][index]
        if hole["type"] == 0:
            return
        if hole["type"] == 2:
            state["score"] = max(0, state["score"] - 15)
        else:
            state["score"] += 30 if hole["type"] == 3 else 10
            state["hits"] += 1
            state["level"] = state["hits"]
        hole["type"] = 0

    @classmethod
    def step(cls, state):
        tick = state["tick"]
        holes = state["holes"]
        for hole in holes:
            if hole["type"] != 0 and tick >= hole["until"]:
                hole["type"] = 0
        if tick >= state["nextSpawn"]:
            progress = (tick * 100) // LIMIT_TICKS
            free = [i for i in range(HOLES) if holes[i]["type"] == 0]
            if free:
                index = free[state["rng"].int(len(free))]
                r = state["rng"].int(100)
                hole = holes[index]
                hole["type"] = 2 if r < 16 + progress // 6 else 3 if r >= 95 else 1
                hole["born"] = tick
                hole["until"] = tick + 55 - (progress * 28) // 100
            state["nextSpawn"] = tick + 42 - (progress * 26) // 100
        state["tick"] += 1
        if state["tick"] >= LIMIT_TICKS:
            state["over"] = True
            state["cause"] = "time"

    @classmethod
    def random_payload(cls, rng, state):
        return [rng.randint(0, HOLES - 1)]

    @classmethod
    def demo_policy(cls, rng, skill, options=None):
        wait = [0]
        reaction = 12 if skill >= 100 else 18 if skill >= 97 else 34

        def policy(state, tick):
            if tick < wait[0]:
                return None
            for index, hole in enumerate(state["holes"]):
                if hole["type"] == 0 or tick - hole["born"] < reaction:
                    continue
                if hole["type"] == 2 and not (skill < 95 and rng.random() < 0.05):
                    continue
                wait[0] = tick + 7
                return [index]
            return None

        return policy
