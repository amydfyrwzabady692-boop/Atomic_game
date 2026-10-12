"""«هیزم‌شکن» — معادل دقیق ``static/arcade/timber/core.js``."""

from .base import ArcadeSimulator, register_simulator
from .rng import MASK, Mulberry32

VISIBLE = 9
MAX_TIME = 10000
START_TIME = 6000
GAIN = 420
CLOCK_GAIN = 1500
FAST_TICKS = 14


def generate(state: dict) -> dict:
    """تکه‌ی بعدی تنه. شاخه‌ی طرف مخالف هیچ‌وقت چسبیده به شاخه‌ی قبلی نمی‌آید (همیشه راه سالم هست)."""
    g, rng = state["gen"], state["rng"]
    i = g["index"]
    g["index"] += 1
    if i < 3:
        return {"b": 0, "c": 0}
    lvl = min(i // 20, 10)
    b = 0
    if g["run"] > 0:
        g["run"] -= 1
        b = g["runSide"]
    elif rng.int(100) < 45 + lvl * 4:
        side = rng.int(2) + 1
        if g["prev"] == 0 or g["prev"] == side:
            b = side
            if lvl >= 2 and rng.int(100) < 10 + lvl * 3:
                g["run"] = 1 + rng.int(2)
                g["runSide"] = side
    c = 0
    if lvl >= 1 and rng.int(100) < 6:
        c = rng.int(2) + 1 if b == 0 else 3 - b
    g["prev"] = b
    return {"b": b, "c": c}


def drain_for(level: int) -> int:
    return min(50, 14 + level * 3)


@register_simulator
class TimberSimulator(ArcadeSimulator):
    key = "timber"
    title_fa = "هیزم‌شکن"
    emoji = "🪓"
    description_fa = "چپ و راست تنه را بزن، از شاخه‌ها جاخالی بده و نگذار نوار زمان خالی شود."
    howto_fa = "نیمه‌ی چپ یا راست صفحه را بزن؛ شاخه روی سرت نیفتد!"
    rules_fa = [
        "نیمه‌ی چپ یا راست صفحه را بزن تا همان سمت تنه را بزنی.",
        "هر ضربه ۱ امتیاز دارد و نوار زمان را پر می‌کند.",
        "اگر شاخه روی سرت بیفتد یا نوار زمان خالی شود بازی تمام است.",
    ]
    category = "speed"
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
            "side": 0,
            "chops": 0,
            "time": START_TIME,
            "started": False,
            "lastChop": -1000,
            "streak": 0,
            "gen": {"index": 0, "prev": 0, "run": 0, "runSide": 0},
            "segs": [],
        }
        for _ in range(VISIBLE):
            state["segs"].append(generate(state))
        return state

    @classmethod
    def apply_input(cls, state, event):
        side = event[1]
        if state["over"] or side not in (0, 1):
            return
        state["started"] = True
        state["side"] = side
        if state["segs"][0]["b"] == side + 1:
            state["over"] = True
            state["cause"] = "branch"
            return
        seg = state["segs"].pop(0)
        state["segs"].append(generate(state))
        state["chops"] += 1
        state["score"] += 1
        if seg["c"] == side + 1:
            state["time"] = min(MAX_TIME, state["time"] + CLOCK_GAIN)
        state["time"] = min(MAX_TIME, state["time"] + GAIN)
        if state["tick"] - state["lastChop"] <= FAST_TICKS:
            state["streak"] += 1
            if state["streak"] % 10 == 0:
                state["score"] += 5
        else:
            state["streak"] = 0
        state["lastChop"] = state["tick"]
        state["level"] = state["chops"] // 20
        if state["segs"][0]["b"] == side + 1:
            state["over"] = True
            state["cause"] = "branch"

    @classmethod
    def step(cls, state):
        if state["started"]:
            state["time"] -= drain_for(state["level"])
            if state["time"] <= 0:
                state["time"] = 0
                state["over"] = True
                state["cause"] = "time"
        state["tick"] += 1

    @classmethod
    def random_payload(cls, rng, state):
        return [rng.randint(0, 1)]

    @classmethod
    def demo_policy(cls, rng, skill, options=None):
        wait = [20]
        # مهارت کمتر = ضربه‌های کندتر (نوار زمان زودتر خالی می‌شود) و گاهی طرف اشتباه
        gap = 7 if skill >= 100 else 9 if skill >= 97 else 16

        def policy(state, tick):
            if tick < wait[0]:
                return None
            wait[0] = tick + gap
            side = state["side"]
            if state["segs"][1]["b"] == side + 1:
                side = 1 - side
            elif (
                state["segs"][0]["c"] == 2 - side
                and state["segs"][0]["b"] != 2 - side
                and state["segs"][1]["b"] != 2 - side
            ):
                side = 1 - side  # رفتن سراغ آیتم ساعت
            if skill < 95 and rng.random() < 0.02:
                side = rng.randint(0, 1)
            return [side]

        return policy
