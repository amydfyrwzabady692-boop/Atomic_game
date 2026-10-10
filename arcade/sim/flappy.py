"""«پرنده‌ی پرشی» — معادل دقیق ``static/arcade/flappy/core.js``."""

from .base import ArcadeSimulator, register_simulator
from .rng import MASK, Mulberry32

FIELD_W, FIELD_H = 3600, 6400
BIRD_X, RADIUS, PIPE_W = 1000, 130, 560
GRAVITY, JUMP, MAX_VY = 7, -105, 200


def spacing_for(score: int) -> int:
    return max(1700, 2300 - score * 12)


def gap_for(score: int) -> int:
    return max(1350, 1900 - score * 15)


def speed_for(score: int) -> int:
    return 26 + min(score, 60) // 5


@register_simulator
class FlappySimulator(ArcadeSimulator):
    key = "flappy"
    title_fa = "پرنده‌ی پرشی"
    emoji = "🐤"
    description_fa = "با هر تپ بپر و از بین موانع رد شو؛ موانع کم‌کم تنگ‌تر و سریع‌تر می‌شوند."
    howto_fa = "تپ کن تا بپرد؛ به موانع و زمین نخور."
    category = "skill"
    suggested_minutes = 3
    TICK_MS = 16
    INPUT_ARITY = 1
    FIXTURE_MS = 60_000

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
            "started": False,
            "y": FIELD_H // 2 - 400,
            "vy": 0,
            "pipes": [],
            "dist": spacing_for(0) - 1400,
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
        speed = speed_for(state["score"])
        state["vy"] = min(state["vy"] + GRAVITY, MAX_VY)
        state["y"] += state["vy"]
        if state["y"] < RADIUS:
            state["y"] = RADIUS
            state["vy"] = 0

        state["dist"] += speed
        spacing = spacing_for(state["score"])
        if state["dist"] >= spacing:
            state["dist"] -= spacing
            gap_h = gap_for(state["score"])
            state["pipes"].append(
                {"x": FIELD_W, "gapY": state["rng"].range(700, FIELD_H - 1100 - gap_h), "gapH": gap_h, "passed": False}
            )
        pipes = state["pipes"]
        for p in pipes:
            p["x"] -= speed
        if pipes and pipes[0]["x"] + PIPE_W < -200:
            pipes.pop(0)

        if state["y"] + RADIUS >= FIELD_H:
            state["over"] = True
            state["cause"] = "ground"
        for p in pipes:
            if state["over"]:
                break
            if BIRD_X + RADIUS > p["x"] and BIRD_X - RADIUS < p["x"] + PIPE_W:
                if state["y"] - RADIUS < p["gapY"] or state["y"] + RADIUS > p["gapY"] + p["gapH"]:
                    state["over"] = True
                    state["cause"] = "pipe"
            elif not p["passed"] and p["x"] + PIPE_W <= BIRD_X - RADIUS:
                p["passed"] = True
                state["score"] += 1
                state["level"] = state["score"]
        state["tick"] += 1

    @classmethod
    def demo_policy(cls, rng, skill, options=None):
        wait = [0]

        def policy(state, tick):
            if tick < wait[0]:
                return None
            if not state["started"]:
                wait[0] = tick + 8
                return [] if tick > 20 else None
            target, gap_h = FIELD_H // 2, 1900
            for p in state["pipes"]:
                if p["x"] + PIPE_W >= BIRD_X - RADIUS:
                    target, gap_h = p["gapY"] + p["gapH"] // 2, p["gapH"]
                    break
            line = target + gap_h // 2 - RADIUS - 260 + (100 - skill) * 30
            if state["y"] > line and state["vy"] > -20:
                wait[0] = tick + 6
                return []
            return None

        return policy
