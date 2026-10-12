"""«۲۰۴۸ سرعتی» — معادل دقیق ``static/arcade/g2048/core.js``."""

from .base import ArcadeSimulator, register_simulator
from .rng import MASK, Mulberry32

LIMIT_TICKS = 7500


def cell_index(direction: int, line: int, k: int) -> int:
    if direction == 3:
        return line * 4 + k
    if direction == 1:
        return line * 4 + (3 - k)
    if direction == 0:
        return k * 4 + line
    return (3 - k) * 4 + line


def spawn(state: dict) -> None:
    empty = [i for i in range(16) if state["grid"][i] == 0]
    if not empty:
        return
    cell = empty[state["rng"].int(len(empty))]
    state["grid"][cell] = 4 if state["rng"].int(10) == 0 else 2


def stuck(grid: list[int]) -> bool:
    for i in range(16):
        if grid[i] == 0:
            return False
        if i % 4 < 3 and grid[i] == grid[i + 1]:
            return False
        if i < 12 and grid[i] == grid[i + 4]:
            return False
    return True


def slide(grid: list[int], direction: int) -> tuple[bool, int]:
    """حرکت را روی grid اعمال می‌کند: (آیا چیزی جابه‌جا شد، امتیاز ادغام‌ها)."""
    moved, gained = False, 0
    for line in range(4):
        values = [v for k in range(4) if (v := grid[cell_index(direction, line, k)])]
        out = []
        k = 0
        while k < len(values):
            if k + 1 < len(values) and values[k] == values[k + 1]:
                out.append(values[k] * 2)
                gained += values[k] * 2
                k += 2
            else:
                out.append(values[k])
                k += 1
        for k in range(4):
            idx = cell_index(direction, line, k)
            value = out[k] if k < len(out) else 0
            if grid[idx] != value:
                moved = True
            grid[idx] = value
    return moved, gained


@register_simulator
class G2048Simulator(ArcadeSimulator):
    key = "g2048"
    title_fa = "۲۰۴۸ سرعتی"
    emoji = "🔢"
    description_fa = "کاشی‌های هم‌عدد را به هم بچسبان. ۲ دقیقه وقت داری و بیشترین امتیاز برنده است."
    howto_fa = "انگشتت را به چهار جهت بکش تا کاشی‌ها حرکت کنند."
    rules_fa = [
        "انگشتت را به چهار جهت بکش تا کاشی‌ها حرکت کنند.",
        "کاشی‌های هم‌عدد یکی می‌شوند و امتیاز می‌دهند.",
        "۲ دقیقه وقت داری؛ اگر حرکتی نماند بازی زودتر تمام می‌شود.",
    ]
    category = "speed"
    suggested_minutes = 5
    TICK_MS = 16
    INPUT_ARITY = 2
    MAX_DURATION_MS = 121_000
    FIXTURE_MS = 121_000

    @classmethod
    def new_state(cls, seed, config):
        state = {
            "seed": seed & MASK,
            "rng": Mulberry32(seed),
            "tick": 0,
            "over": False,
            "cause": "",
            "score": 0,
            "level": 1,
            "grid": [0] * 16,
        }
        spawn(state)
        spawn(state)
        return state

    @classmethod
    def apply_input(cls, state, event):
        direction = event[1]
        if state["over"] or direction not in (0, 1, 2, 3):
            return
        grid = state["grid"]
        moved, gained = slide(grid, direction)
        if not moved:
            return
        state["score"] += gained
        spawn(state)
        state["level"] = max(grid).bit_length() - 1
        if stuck(grid):
            state["over"] = True
            state["cause"] = "stuck"

    @classmethod
    def step(cls, state):
        state["tick"] += 1
        if state["tick"] >= LIMIT_TICKS:
            state["over"] = True
            state["cause"] = "time"

    @classmethod
    def random_payload(cls, rng, state):
        return [rng.randint(0, 3)]

    @classmethod
    def demo_policy(cls, rng, skill, options=None):
        wait = [20]

        def policy(state, tick):
            if tick < wait[0]:
                return None
            wait[0] = tick + (10 if skill >= 97 else 22)
            if skill < 100 and rng.randint(1, 100) > skill:
                return [rng.randint(0, 3)]
            # راهبرد ساده‌ی «گوشه»: پایین، چپ، راست و در آخر بالا
            for direction in (2, 3, 1, 0):
                if slide(list(state["grid"]), direction)[0]:
                    return [direction]
            return [0]

        return policy
