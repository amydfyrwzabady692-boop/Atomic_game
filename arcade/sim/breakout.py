"""«آجرشکن» — معادل دقیق ``static/arcade/breakout/core.js`` (فیزیک با اعداد صحیح)."""

import json
from functools import lru_cache
from pathlib import Path

from .base import ArcadeSimulator, register_simulator
from .rng import MASK, Mulberry32

WIDTH, HEIGHT = 3600, 6400
COLS, ROWS = 8, 8
BRICK_W, BRICK_H, STEP_X, STEP_Y, LEFT, TOP = 420, 200, 444, 224, 36, 900
PADDLE_Y, PADDLE_W, PADDLE_WIDE = 5700, 660, 1000
BALL_R = 70
MAX_VX = 44
ATTACH_TICKS, PAUSE_TICKS, WIDE_TICKS = 45, 40, 600
ITEM_SPEED = 22
START_LIVES, MAX_LIVES = 3, 5

LEVELS_PATH = Path(__file__).resolve().parent.parent / "static" / "arcade" / "breakout" / "levels.json"


@lru_cache(maxsize=1)
def load_levels() -> list[list[str]]:
    return json.loads(LEVELS_PATH.read_text(encoding="utf-8"))


def paddle_width(state: dict) -> int:
    return PADDLE_WIDE if state["wide"] > 0 else PADDLE_W


def ball_speed(state: dict) -> int:
    return 66 + min(state["level"], 8) * 4


def clamp_paddle(state: dict) -> None:
    state["px"] = max(0, min(WIDTH - paddle_width(state), state["px"]))


def load_level(state: dict) -> None:
    layouts = state["levels"]
    layout = layouts[state["level"] % len(layouts)]
    extra = state["level"] // len(layouts)
    bricks = []
    remaining = 0
    for r in range(ROWS):
        for c in range(COLS):
            hp = ord(layout[r][c]) - 48 if r < len(layout) else 0
            if hp > 0:
                hp = min(3, hp + extra)
                remaining += 1
            bricks.append(hp)
    state["bricks"] = bricks
    state["remaining"] = remaining
    state["items"] = []
    state["wide"] = 0
    state["attach"] = ATTACH_TICKS
    state["vx"] = 0
    state["vy"] = 0
    clamp_paddle(state)


def brick_at(state: dict, x: int, y: int) -> int:
    c0 = max(0, (x - BALL_R - LEFT - BRICK_W) // STEP_X)
    c1 = min(COLS - 1, (x + BALL_R - LEFT) // STEP_X)
    r0 = max(0, (y - BALL_R - TOP - BRICK_H) // STEP_Y)
    r1 = min(ROWS - 1, (y + BALL_R - TOP) // STEP_Y)
    bricks = state["bricks"]
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            if bricks[r * COLS + c] <= 0:
                continue
            bx, by = LEFT + c * STEP_X, TOP + r * STEP_Y
            if bx - BALL_R <= x <= bx + BRICK_W + BALL_R and by - BALL_R <= y <= by + BRICK_H + BALL_R:
                return r * COLS + c
    return -1


def damage(state: dict, index: int) -> None:
    state["bricks"][index] -= 1
    state["score"] += 5
    if state["bricks"][index] > 0:
        return
    state["remaining"] -= 1
    state["score"] += 10
    if state["rng"].int(100) < 12:
        state["items"].append(
            {
                "x": LEFT + (index % COLS) * STEP_X + BRICK_W // 2,
                "y": TOP + (index // COLS) * STEP_Y + BRICK_H,
                "type": state["rng"].int(3),
            }
        )
    if state["remaining"] == 0:
        state["level"] += 1
        state["score"] += 100
        state["pause"] = PAUSE_TICKS


@register_simulator
class BreakoutSimulator(ArcadeSimulator):
    key = "breakout"
    title_fa = "آجرشکن"
    emoji = "🧱"
    description_fa = "با راکت توپ را نگه دار و آجرها را بشکن. آجرهای چندضربه‌ای و آیتم‌های کمکی در راه‌اند."
    howto_fa = "انگشتت را بکش تا راکت حرکت کند؛ توپ نیفتد!"
    rules_fa = [
        "انگشتت را بکش تا راکت حرکت کند و توپ را نگه دارد.",
        "هر آجر امتیاز دارد؛ با شکستن همه‌ی آجرها مرحله‌ی بعد می‌آید.",
        "۳ جان داری؛ هر بار توپ بیفتد یک جان کم می‌شود.",
    ]
    category = "stage"
    suggested_minutes = 5
    TICK_MS = 16
    INPUT_ARITY = 2
    MAX_INPUTS = 40_000
    MIN_INPUT_GAP_MS = 0  # ورودی پیوسته: موقعیت راکت در تیک‌های ثابت
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
            "levels": load_levels(),
            "lives": START_LIVES,
            "px": (WIDTH - PADDLE_W) // 2,
            "bx": WIDTH // 2,
            "by": PADDLE_Y - BALL_R,
            "vx": 0,
            "vy": 0,
            "pause": 0,
            "wide": 0,
            "attach": 0,
            "bricks": [],
            "remaining": 0,
            "items": [],
        }
        load_level(state)
        return state

    @classmethod
    def apply_input(cls, state, event):
        if state["over"]:
            return
        state["px"] = event[1] - paddle_width(state) // 2
        clamp_paddle(state)

    @classmethod
    def step(cls, state):
        if state["pause"] > 0:
            state["pause"] -= 1
            if state["pause"] == 0:
                load_level(state)
            state["tick"] += 1
            return
        if state["wide"] > 0:
            state["wide"] -= 1
            if state["wide"] == 0:
                clamp_paddle(state)
        w = paddle_width(state)
        if state["attach"] > 0:
            state["attach"] -= 1
            state["bx"] = state["px"] + w // 2
            state["by"] = PADDLE_Y - BALL_R
            if state["attach"] == 0:
                state["vx"] = (state["rng"].int(5) - 2) * 8
                state["vy"] = -ball_speed(state)
        else:
            state["bx"] += state["vx"]
            if state["bx"] < BALL_R:
                state["bx"] = BALL_R
                state["vx"] = -state["vx"]
            elif state["bx"] > WIDTH - BALL_R:
                state["bx"] = WIDTH - BALL_R
                state["vx"] = -state["vx"]
            hit = brick_at(state, state["bx"], state["by"])
            if hit >= 0:
                state["bx"] -= state["vx"]
                state["vx"] = -state["vx"]
                damage(state, hit)
            if state["pause"] == 0:
                state["by"] += state["vy"]
                if state["by"] < BALL_R:
                    state["by"] = BALL_R
                    state["vy"] = -state["vy"]
                hit = brick_at(state, state["bx"], state["by"])
                if hit >= 0:
                    state["by"] -= state["vy"]
                    state["vy"] = -state["vy"]
                    damage(state, hit)
            if (
                state["pause"] == 0
                and state["vy"] > 0
                and state["by"] + BALL_R >= PADDLE_Y
                and state["by"] + BALL_R - state["vy"] <= PADDLE_Y
                and state["px"] - BALL_R <= state["bx"] <= state["px"] + w + BALL_R
            ):
                half = w // 2
                rel = ((state["bx"] - (state["px"] + half)) * 100) // (half + BALL_R)
                rel = max(-100, min(100, rel))
                state["by"] = PADDLE_Y - BALL_R
                state["vx"] = (rel * MAX_VX) // 100
                if state["vx"] == 0:
                    state["vx"] = 6 if state["tick"] % 2 == 0 else -6
                state["vy"] = -ball_speed(state)
            elif state["by"] - BALL_R > HEIGHT:
                state["lives"] -= 1
                if state["lives"] <= 0:
                    state["over"] = True
                    state["cause"] = "out"
                else:
                    state["attach"] = ATTACH_TICKS
        items = state["items"]
        for i in range(len(items) - 1, -1, -1):
            item = items[i]
            item["y"] += ITEM_SPEED
            if PADDLE_Y <= item["y"] <= PADDLE_Y + 150 and state["px"] <= item["x"] <= state["px"] + w:
                if item["type"] == 0:
                    state["wide"] = WIDE_TICKS
                    clamp_paddle(state)
                elif item["type"] == 1:
                    if state["lives"] < MAX_LIVES:
                        state["lives"] += 1
                else:
                    state["score"] += 50
                items.pop(i)
            elif item["y"] > HEIGHT:
                items.pop(i)
        state["tick"] += 1

    @classmethod
    def random_payload(cls, rng, state):
        return [rng.randint(0, WIDTH)]

    @classmethod
    def demo_policy(cls, rng, skill, options=None):
        """راکت را زیر توپ نگه می‌دارد (با کمی جابه‌جایی تا زاویه‌ها عوض شوند)."""
        aim = {"offset": 0, "last": None, "vy": 0}
        lag = 0 if skill >= 100 else 60 if skill >= 97 else 420

        def policy(state, tick):
            if tick % 2 or state["pause"] > 0:
                return None
            if state["vy"] < 0 <= aim["vy"]:
                aim["offset"] = rng.randint(-260, 260)  # بعد از هر برخورد با راکت، نقطه‌ی هدف عوض می‌شود
            aim["vy"] = state["vy"]
            if state["attach"] > 0:
                return None
            target = state["bx"] + aim["offset"] + (rng.randint(-lag, lag) if lag else 0)
            target = max(0, min(WIDTH, target))
            if aim["last"] is not None and abs(target - aim["last"]) < 20:
                return None
            aim["last"] = target
            return [target]

        return policy
