"""«پرش ابرها» — معادل دقیق ``static/arcade/jumper/core.js``."""

from .base import ArcadeSimulator, register_simulator
from .rng import MASK, Mulberry32

WIDTH = 3600
GRAVITY, JUMP, SPRING, MAX_FALL = 7, 150, 230, -220
H_SPEED = 30
MAX_SHIFT = 1100
PLAT_W, HALF_BODY = 620, 110
VIEW_BELOW = 2600
FALL_MARGIN = 600
GENERATE_AHEAD = 9000


def generate(state: dict) -> None:
    k = state["made"]
    state["made"] += 1
    rng = state["rng"]
    gap = 500 + min(k, 120) * 4 + rng.int(180)
    x = (state["lastX"] + rng.int(2 * MAX_SHIFT + 1) - MAX_SHIFT) % WIDTH
    state["lastX"] = x
    r = rng.int(100)
    lvl = min(k // 25, 6)
    kind = 1 if r < 12 + lvl * 4 else 2 if r < 22 + lvl * 8 else 0
    s = rng.int(100)
    phase = rng.int(240)
    state["topY"] += gap
    state["plats"].append(
        {
            "y": state["topY"],
            "x": x,
            "w": PLAT_W,
            "type": kind,
            "spring": kind == 0 and s < 8,
            "phase": phase,
            "alive": True,
        }
    )


def platform_x(p: dict, tick: int) -> int:
    if p["type"] != 1:
        return p["x"]
    tri = (tick + p["phase"]) % 240
    off = tri if tri < 120 else 240 - tri
    return (p["x"] + (off - 60) * 5) % WIDTH


@register_simulator
class JumperSimulator(ArcadeSimulator):
    key = "jumper"
    title_fa = "پرش ابرها"
    emoji = "☁️"
    description_fa = "روی سکوها بپر و بالا برو. سکوهای شکننده، متحرک و فنردار در راه‌اند؛ افتادن یعنی باخت."
    howto_fa = "چپ یا راست صفحه را بزن تا جهت حرکت عوض شود."
    rules_fa = [
        "چپ یا راست صفحه را بزن تا جهت حرکت عوض شود.",
        "هر چه بالاتر بروی امتیاز بیشتری می‌گیری.",
        "افتادن از پایین صفحه یعنی پایان بازی.",
    ]
    category = "skill"
    suggested_minutes = 5
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
            "x": WIDTH // 2,
            "y": 0,
            "vy": 0,
            "dir": 1,
            "started": False,
            "maxY": 0,
            "camY": -VIEW_BELOW,
            "made": 0,
            "topY": 0,
            "lastX": (WIDTH - PLAT_W) // 2,
            "plats": [{"y": 0, "x": 0, "w": WIDTH, "type": 0, "spring": False, "phase": 0, "alive": True}],
        }
        while state["topY"] < state["camY"] + GENERATE_AHEAD:
            generate(state)
        return state

    @classmethod
    def apply_input(cls, state, event):
        direction = event[1]
        if state["over"] or direction not in (0, 1):
            return
        state["dir"] = -1 if direction == 0 else 1
        state["started"] = True

    @classmethod
    def step(cls, state):
        if not state["started"]:
            state["tick"] += 1
            return
        state["x"] = (state["x"] + state["dir"] * H_SPEED) % WIDTH
        state["vy"] = max(state["vy"] - GRAVITY, MAX_FALL)
        prev_y = state["y"]
        state["y"] += state["vy"]

        if state["vy"] < 0:
            best = None
            for p in state["plats"]:
                if not p["alive"] or p["y"] > prev_y or p["y"] <= state["y"]:
                    continue
                dx = (state["x"] - platform_x(p, state["tick"])) % WIDTH
                if dx <= p["w"] + HALF_BODY or dx >= WIDTH - HALF_BODY:
                    if best is None or p["y"] > best["y"]:
                        best = p
            if best is not None:
                state["y"] = best["y"]
                state["vy"] = SPRING if best["spring"] else JUMP
                if best["type"] == 2:
                    best["alive"] = False

        if state["y"] > state["maxY"]:
            state["maxY"] = state["y"]
            state["score"] = state["maxY"] // 100
            state["level"] = state["score"] // 200
        if state["y"] - VIEW_BELOW > state["camY"]:
            state["camY"] = state["y"] - VIEW_BELOW
        if state["y"] < state["camY"] - FALL_MARGIN:
            state["over"] = True
            state["cause"] = "fall"
        while state["topY"] < state["camY"] + GENERATE_AHEAD:
            generate(state)
        plats = state["plats"]
        while plats and plats[0]["y"] < state["camY"] - 800:
            plats.pop(0)
        state["tick"] += 1

    @classmethod
    def random_payload(cls, rng, state):
        return [rng.randint(0, 1)]

    @classmethod
    def demo_policy(cls, rng, skill, options=None):
        """همیشه سکوی بعدیِ بالای آخرین سکویی که رویش پریده را هدف می‌گیرد؛ اگر جا بماند، سکوی زیر پا."""
        memory = {"wait": 0, "land_y": 0, "vy": 0}
        reaction = 4 if skill >= 100 else 7 if skill >= 97 else 18

        def policy(state, tick):
            if not state["started"]:
                if tick > 20 and tick >= memory["wait"]:
                    memory["wait"] = tick + reaction
                    return [1]
                return None
            y, vy, x = state["y"], state["vy"], state["x"]
            if vy > memory["vy"]:
                memory["land_y"] = y  # همین حالا روی سکویی پرید
            memory["vy"] = vy
            if tick < memory["wait"]:
                return None
            alive = [p for p in state["plats"] if p["alive"] and p["w"] < WIDTH]
            above = [p for p in alive if p["y"] > memory["land_y"] + 50]
            target = min(above, key=lambda p: p["y"]) if above else None
            if target is None or (vy < 0 and y < target["y"]):
                below = [p for p in alive if p["y"] <= y]
                if not below:
                    return None
                target = max(below, key=lambda p: p["y"])
            center = (platform_x(target, tick) + target["w"] // 2) % WIDTH
            delta = (center - x) % WIDTH
            want = 1 if delta < WIDTH // 2 else -1
            distance = min(delta, WIDTH - delta)
            if distance < 150 or want == state["dir"]:
                return None
            memory["wait"] = tick + reaction
            return [1 if want == 1 else 0]

        return policy
