"""«تعویض رنگ» — معادل دقیق ``static/arcade/colorswitch/core.js``."""

from .base import ArcadeSimulator, register_simulator
from .rng import MASK, Mulberry32

CIRCLE = 360000
GRAVITY, JUMP, MAX_FALL = 5, 80, -140
BALL_R = 110
SPACING, FIRST_Y = 4200, 2600
RING_R, OUTER_R, HALF_T = 820, 1300, 75
BAND = HALF_T + BALL_R
SEG_W = 900
FALL_LIMIT = 2800


def spec_of(state: dict, k: int) -> dict:
    spec = state["specs"].get(k)
    if spec is not None:
        return spec
    rng = Mulberry32((state["seed"] + (k + 1) * 977) & MASK)
    stage = min(k // 5, 8)
    t = rng.int(100)
    spec = {
        "type": 0 if k < 2 else 0 if t < 50 else 2 if (t < 80 or stage < 1) else 1,
        "dir": 1 if rng.int(2) == 1 else -1,
        "speed": 900 + stage * 130 + rng.int(300),
        "phase": rng.int(360) * 1000,
        "barSpeed": 18 + stage * 2 + rng.int(8),
        "next": rng.int(3),
        "y": FIRST_Y + k * SPACING,
    }
    state["specs"][k] = spec
    return spec


def ring_rot(spec: dict, tick: int) -> int:
    return (spec["phase"] + spec["dir"] * spec["speed"] * tick) % CIRCLE


def outer_rot(spec: dict, tick: int) -> int:
    return (spec["phase"] + 45000 - spec["dir"] * spec["speed"] * tick) % CIRCLE


def bar_offset(spec: dict, tick: int) -> int:
    return (spec["phase"] // 100 + spec["dir"] * spec["barSpeed"] * tick) % (4 * SEG_W)


def arc_color(rot: int, theta: int) -> int:
    return ((theta - rot) % CIRCLE) // 90000


def bar_color(offset: int) -> int:
    return ((2 * SEG_W - offset) % (4 * SEG_W)) // SEG_W


def hits(state: dict, k: int, y: int, tick: int) -> bool:
    spec = spec_of(state, k)
    d = y - spec["y"]
    a = abs(d)
    if spec["type"] == 2:
        return a < BAND and bar_color(bar_offset(spec, tick)) != state["color"]
    theta = 90000 if d < 0 else 270000
    if abs(a - RING_R) < BAND and arc_color(ring_rot(spec, tick), theta) != state["color"]:
        return True
    return (
        spec["type"] == 1
        and abs(a - OUTER_R) < BAND
        and arc_color(outer_rot(spec, tick), theta) != state["color"]
    )


def top_of(spec: dict) -> int:
    return spec["y"] + (0 if spec["type"] == 2 else OUTER_R if spec["type"] == 1 else RING_R) + BAND


def bottom_of(spec: dict) -> int:
    return spec["y"] - (0 if spec["type"] == 2 else OUTER_R if spec["type"] == 1 else RING_R) - BAND


@register_simulator
class ColorSwitchSimulator(ArcadeSimulator):
    key = "colorswitch"
    title_fa = "تعویض رنگ"
    emoji = "🎨"
    description_fa = "توپ فقط از بخش هم‌رنگ خودش رد می‌شود. موانع چرخان هر مرحله سخت‌تر می‌شوند."
    howto_fa = "تپ کن تا توپ بالا برود؛ فقط از رنگ خودش رد شو."
    rules_fa = [
        "تپ کن تا توپ بالا برود.",
        "فقط از بخش هم‌رنگ توپ رد شو؛ هر مانع ۱ امتیاز دارد.",
        "برخورد با رنگ دیگر یا افتادن توپ یعنی پایان بازی.",
    ]
    category = "stage"
    suggested_minutes = 5
    TICK_MS = 16
    INPUT_ARITY = 1
    FIXTURE_MS = 60_000

    @classmethod
    def new_state(cls, seed, config):
        s = seed & MASK
        return {
            "seed": s,
            "tick": 0,
            "over": False,
            "cause": "",
            "score": 0,
            "level": 0,
            "y": 0,
            "vy": 0,
            "maxY": 0,
            "started": False,
            "color": Mulberry32(s).int(4),
            "passed": 0,
            "switched": 0,
            "specs": {},
        }

    @classmethod
    def apply_input(cls, state, event):
        if state["over"]:
            return
        state["started"] = True
        state["vy"] = JUMP

    @classmethod
    def step(cls, state):
        if not state["started"]:
            state["tick"] += 1
            return
        state["vy"] = max(state["vy"] - GRAVITY, MAX_FALL)
        state["y"] += state["vy"]
        if state["y"] > state["maxY"]:
            state["maxY"] = state["y"]
        if state["y"] <= 0 and state["maxY"] < 700:
            state["y"] = 0
            state["vy"] = 0
        elif state["y"] < state["maxY"] - FALL_LIMIT:
            state["over"] = True
            state["cause"] = "fall"
        if not state["over"]:
            nearest = (state["y"] - FIRST_Y + SPACING // 2) // SPACING
            for k in range(max(0, nearest - 1), nearest + 2):
                if hits(state, k, state["y"], state["tick"]):
                    state["over"] = True
                    state["cause"] = "color"
                    break
        if not state["over"]:
            spec = spec_of(state, state["passed"])
            if state["y"] > top_of(spec):
                state["passed"] += 1
                state["score"] += 1
                state["level"] = state["passed"] // 5
            sw = spec_of(state, state["switched"])
            if state["y"] >= sw["y"] + SPACING // 2:
                state["color"] = (state["color"] + 1 + sw["next"]) % 4
                state["switched"] += 1
        state["tick"] += 1

    # ------------------------------------------------------------------ بازیکن خودکار (فقط تست)
    @classmethod
    def _gates(cls, state) -> list[tuple[int, int]]:
        """بازه‌های خطرناک [پایین، بالا] مانع بعدی و بعدش، به ترتیب ارتفاع."""
        gates = []
        for k in (state["passed"], state["passed"] + 1):
            spec = spec_of(state, k)
            y = spec["y"]
            if spec["type"] == 2:
                gates.append((y - BAND, y + BAND))
            elif spec["type"] == 0:
                gates += [(y - RING_R - BAND, y - RING_R + BAND), (y + RING_R - BAND, y + RING_R + BAND)]
            else:
                # دو نوار تودرتو آن‌قدر نزدیک‌اند که باید یک‌جا رد شوند
                gates += [(y - OUTER_R - BAND, y - RING_R + BAND), (y + RING_R - BAND, y + OUTER_R + BAND)]
        return gates

    @classmethod
    def demo_policy(cls, rng, skill, options=None):
        mode = {"ascend_to": None, "wait": 0}

        def survives(state, target):
            """اگر از همین حالا پشت‌سرهم بپرد، سالم از بازه رد می‌شود؟"""
            sim = dict(state)
            sim["specs"] = state["specs"]
            for i in range(90):
                if sim["vy"] <= 8 and i % 5 == 0:
                    cls.apply_input(sim, [0])
                cls.step(sim)
                if sim["over"]:
                    return False
                if sim["y"] > target:
                    return True
            return False

        def policy(state, tick):
            if tick < mode["wait"]:
                return None
            if not state["started"]:
                mode["wait"] = tick + 6
                return [] if tick > 20 else None
            y, vy = state["y"], state["vy"]
            gates = [g for g in cls._gates(state) if g[1] > y]
            gate = gates[0]
            if mode["ascend_to"] is not None:
                if y > mode["ascend_to"]:
                    mode["ascend_to"] = None
                elif vy <= 8:
                    mode["wait"] = tick + 5
                    return []
                else:
                    return None
            # شناور ماندن زیر بازه‌ی بعدی؛ هر بار که وقت پرش است بررسی می‌کند می‌شود رد شد یا نه
            ceiling = gate[0] - 30
            hover_low = ceiling - 760
            if vy <= 0 and y <= hover_low:
                target = gate[1] + 30
                reckless = skill < 100 and rng.randint(1, 100) > skill and rng.random() < 0.3
                if reckless or survives(state, target):
                    mode["ascend_to"] = target
                mode["wait"] = tick + 5
                return []
            return None

        return policy
