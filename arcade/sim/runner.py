"""«دونده‌ی سه‌خطی» — معادل دقیق ``static/arcade/runner/core.js``."""

from .base import ArcadeSimulator, register_simulator
from .rng import MASK, Mulberry32

ROW_GAP = 1400
FIRST = 4200
JUMP_TICKS = 30
AHEAD = 8


def generate(state: dict) -> None:
    k = len(state["rows"])
    if k < 2:
        state["rows"].append([0, 0, 0])
        return
    rng = state["rng"]
    lvl = min(k // 20, 8)
    safe = min(2, max(0, state["prevSafe"] + rng.int(3) - 1))
    row = [0, 0, 0]
    for lane in range(3):
        if lane == safe:
            row[lane] = 3 if rng.int(100) < 35 else 0
        else:
            r = rng.int(100)
            row[lane] = 0 if r < 30 - lvl * 2 else 1 if r < 60 else 2 if r < 92 else 3
    state["prevSafe"] = safe
    state["rows"].append(row)


def speed_for(passed: int) -> int:
    return 42 + min(passed, 120) // 3


def row_z(state: dict, k: int) -> int:
    return FIRST + k * ROW_GAP - state["dist"]


@register_simulator
class RunnerSimulator(ArcadeSimulator):
    key = "runner"
    title_fa = "دونده‌ی سه‌خطی"
    emoji = "🏃"
    description_fa = "بین سه خط جابه‌جا شو، از موانع کوتاه بپر و سکه جمع کن. سرعت کم‌کم بیشتر می‌شود."
    howto_fa = "چپ/راست بکش تا خط عوض شود؛ بالا بکش تا بپرد."
    rules_fa = [
        "چپ یا راست بکش تا خط عوض شود؛ بالا بکش تا بپرد.",
        "مسافت و سکه‌ها امتیاز می‌دهند.",
        "برخورد با مانع یعنی پایان بازی.",
    ]
    category = "skill"
    suggested_minutes = 3
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
            "lane": 1,
            "air": 0,
            "dist": 0,
            "passed": 0,
            "prevSafe": 1,
            "rows": [],
        }
        while len(state["rows"]) < AHEAD:
            generate(state)
        return state

    @classmethod
    def apply_input(cls, state, event):
        action = event[1]
        if state["over"]:
            return
        if action == 0:
            if state["lane"] > 0:
                state["lane"] -= 1
        elif action == 1:
            if state["lane"] < 2:
                state["lane"] += 1
        elif action == 2:
            if state["air"] == 0:
                state["air"] = JUMP_TICKS

    @classmethod
    def step(cls, state):
        state["dist"] += speed_for(state["passed"])
        if state["air"] > 0:
            state["air"] -= 1
        while not state["over"] and row_z(state, state["passed"]) <= 0:
            row = state["rows"][state["passed"]]
            cell = row[state["lane"]]
            if cell == 2 or (cell == 1 and state["air"] == 0):
                state["over"] = True
                state["cause"] = "crash"
                break
            if cell == 3:
                state["score"] += 5
                row[state["lane"]] = 0
            state["score"] += 1
            state["passed"] += 1
            while len(state["rows"]) < state["passed"] + AHEAD:
                generate(state)
        state["level"] = state["passed"] // 20
        state["tick"] += 1

    @classmethod
    def random_payload(cls, rng, state):
        return [rng.randint(0, 2)]

    @classmethod
    def demo_policy(cls, rng, skill, options=None):
        wait = [0]

        def policy(state, tick):
            if tick < wait[0]:
                return None
            row = state["rows"][state["passed"]]
            lane = state["lane"]
            speed = speed_for(state["passed"])
            ticks_to = row_z(state, state["passed"]) // speed
            if skill < 95 and rng.random() < 0.004:
                wait[0] = tick + 6
                return [rng.randint(0, 2)]
            cell = row[lane]
            if cell in (0, 3):
                # خط فعلی امن است؛ اگر سکه‌ای کنار دست بود و وقت هست، برو سراغش
                return None
            # نزدیک‌ترین خط امن (خالی یا سکه)
            options_ = sorted((abs(i - lane), i) for i in range(3) if row[i] in (0, 3))
            if options_ and ticks_to > options_[0][0] * 6:
                target = options_[0][1]
                wait[0] = tick + 6
                return [0 if target < lane else 1]
            if cell == 1 and state["air"] == 0 and ticks_to <= 14:
                wait[0] = tick + 6
                return [2]
            return None

        return policy
