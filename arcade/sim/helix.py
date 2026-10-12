"""«مارپیچ سقوط» — معادل دقیق ``static/arcade/helix/core.js``."""

from .base import ArcadeSimulator, register_simulator
from .rng import MASK, Mulberry32

CIRCLE = 360000
BALL_ANGLE = 90000
FLOOR_H = 1800
GRAVITY, BOUNCE, MAX_VY = 6, -108, 150
PAUSE_TICKS = 30
MAX_TURN = 12000
FIRE_STREAK = 3


def build_level(state: dict) -> None:
    level = min(state["level"], 10)
    count = 10 + level * 2
    floors = []
    for k in range(1, count + 1):
        rng = Mulberry32((state["seed"] + state["level"] * 1009 + k * 31) & MASK)
        floor = {"gapStart": rng.int(360) * 1000, "gapSize": max(42000, 78000 - level * 4000), "reds": []}
        if k > 1:
            reds = min(3, 1 + (level + rng.int(2)) // 2)
            for _ in range(reds):
                start = rng.int(360) * 1000
                floor["reds"].append([start, 30000 + rng.int(21) * 1000])
        floors.append(floor)
    state["floors"] = floors
    state["count"] = count
    state["y"] = 0
    state["vy"] = 0
    state["floorIdx"] = 1
    state["streak"] = 0
    state["rot"] = (BALL_ANGLE - (floors[0]["gapStart"] + 180000)) % CIRCLE


def sector(floor: dict, local: int) -> int:
    if (local - floor["gapStart"]) % CIRCLE < floor["gapSize"]:
        return 0
    for start, size in floor["reds"]:
        if (local - start) % CIRCLE < size:
            return 2
    return 1


@register_simulator
class HelixSimulator(ArcadeSimulator):
    key = "helix"
    title_fa = "مارپیچ سقوط"
    emoji = "🌀"
    description_fa = "برج را بچرخان تا توپ از شکاف‌ها پایین بیفتد؛ به بخش قرمز نخور. چند طبقه پشت‌سرهم = حالت آتشین!"
    howto_fa = "انگشتت را چپ و راست بکش تا برج بچرخد."
    rules_fa = [
        "انگشتت را چپ و راست بکش تا برج بچرخد و توپ از شکاف‌ها پایین برود.",
        "هر طبقه امتیاز دارد؛ چند طبقه پشت‌سرهم امتیاز بیشتری می‌دهد.",
        "برخورد با بخش قرمز یعنی پایان بازی.",
    ]
    category = "stage"
    suggested_minutes = 5
    TICK_MS = 16
    INPUT_ARITY = 2
    MAX_INPUTS = 40_000
    MIN_INPUT_GAP_MS = 0  # ورودی پیوسته (کشیدن انگشت)
    FIXTURE_MS = 45_000

    @classmethod
    def new_state(cls, seed, config):
        state = {
            "seed": seed & MASK,
            "tick": 0,
            "over": False,
            "cause": "",
            "score": 0,
            "level": 0,
            "pause": 0,
            "floors": [],
            "count": 0,
            "y": 0,
            "vy": 0,
            "floorIdx": 1,
            "streak": 0,
            "rot": 0,
        }
        build_level(state)
        return state

    @classmethod
    def apply_input(cls, state, event):
        if state["over"] or state["pause"] > 0:
            return
        turn = max(-MAX_TURN, min(MAX_TURN, event[1]))
        state["rot"] = (state["rot"] + turn) % CIRCLE

    @classmethod
    def step(cls, state):
        if state["pause"] > 0:
            state["pause"] -= 1
            if state["pause"] == 0:
                build_level(state)
            state["tick"] += 1
            return
        state["vy"] = min(state["vy"] + GRAVITY, MAX_VY)
        state["y"] += state["vy"]
        floor_y = state["floorIdx"] * FLOOR_H
        if state["vy"] > 0 and state["y"] >= floor_y:
            if state["floorIdx"] > state["count"]:
                state["y"] = floor_y
                state["vy"] = 0
                state["score"] += 20 + state["level"] * 5
                state["level"] += 1
                state["pause"] = PAUSE_TICKS
            else:
                kind = sector(state["floors"][state["floorIdx"] - 1], (BALL_ANGLE - state["rot"]) % CIRCLE)
                if kind == 0:
                    state["floorIdx"] += 1
                    state["streak"] += 1
                    state["score"] += state["streak"]
                elif state["streak"] >= FIRE_STREAK:
                    state["floorIdx"] += 1
                    state["streak"] = 0
                    state["score"] += 3
                elif kind == 2:
                    state["y"] = floor_y
                    state["over"] = True
                    state["cause"] = "red"
                else:
                    state["y"] = floor_y
                    state["vy"] = BOUNCE
                    state["streak"] = 0
        state["tick"] += 1

    @classmethod
    def random_payload(cls, rng, state):
        return [rng.randint(-6000, 6000)]

    @classmethod
    def demo_policy(cls, rng, skill, options=None):
        """برج را طوری می‌چرخاند که توپ روی شکاف طبقه‌ی بعد فرود بیاید؛ اگر نرسد، روی بخش امن."""
        turn_rate = 6000

        def ticks_to_land(state):
            y, vy, target = state["y"], state["vy"], state["floorIdx"] * FLOOR_H
            for t in range(1, 200):
                vy = min(vy + GRAVITY, MAX_VY)
                y += vy
                if vy > 0 and y >= target:
                    return t
            return 200

        def signed(delta):
            delta %= CIRCLE
            return delta - CIRCLE if delta > CIRCLE // 2 else delta

        def policy(state, tick):
            if state["pause"] > 0 or state["floorIdx"] > state["count"]:
                return None
            floor = state["floors"][state["floorIdx"] - 1]
            local = (BALL_ANGLE - state["rot"]) % CIRCLE
            remaining = ticks_to_land(state)
            reach = turn_rate * max(0, remaining - 1)
            margin = 9000 + (100 - skill) * 400
            want = signed(floor["gapStart"] + floor["gapSize"] // 2 - local)
            if abs(want) > reach and state["streak"] < FIRE_STREAK:
                # به شکاف نمی‌رسد: نزدیک‌ترین نقطه‌ی امن (غیرقرمز) در مسیر
                direction = 1 if want > 0 else -1
                want = 0
                for step in range(reach, -reach - 1, -3000):
                    candidate = (local + direction * step) % CIRCLE
                    if all(sector(floor, (candidate + off) % CIRCLE) != 2 for off in (-margin, 0, margin)):
                        want = direction * step
                        break
            if abs(want) < 800:
                return None
            # local = BALL_ANGLE - rot  ⇒  برای افزایش local باید rot کم شود
            return [-max(-turn_rate, min(turn_rate, want))]

        return policy
