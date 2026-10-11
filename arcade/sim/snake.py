"""«مار کلاسیک» — معادل دقیق ``static/arcade/snake/core.js``."""

from .base import ArcadeSimulator, register_simulator
from .rng import MASK, Mulberry32

COLS, ROWS = 15, 20
DX = [0, 1, 0, -1]
DY = [-1, 0, 1, 0]


def place_food(state: dict) -> bool:
    free = COLS * ROWS - len(state["body"])
    if free <= 0:
        return False
    target = state["rng"].int(free)
    occupied = state["occupied"]
    for cell in range(COLS * ROWS):
        if occupied[cell]:
            continue
        if target == 0:
            state["food"] = cell
            return True
        target -= 1
    return False


def step_every(foods: int) -> int:
    return max(4, 9 - foods // 4)


@register_simulator
class SnakeSimulator(ArcadeSimulator):
    key = "snake"
    title_fa = "مار کلاسیک"
    emoji = "🐍"
    description_fa = "غذا بخور تا مار بلندتر و سریع‌تر شود؛ به دیوار و خودت نخور."
    howto_fa = "انگشتت را بکش تا مار جهت عوض کند."
    rules_fa = [
        "انگشتت را بکش تا مار جهت عوض کند.",
        "هر غذا ۱۰ امتیاز دارد و مار را بلندتر و سریع‌تر می‌کند.",
        "برخورد با دیوار یا بدن خودت یعنی پایان بازی.",
    ]
    category = "skill"
    suggested_minutes = 5
    TICK_MS = 16
    INPUT_ARITY = 2
    FIXTURE_MS = 60_000

    @classmethod
    def new_state(cls, seed, config):
        head = (ROWS // 2) * COLS + COLS // 2
        state = {
            "seed": seed & MASK,
            "rng": Mulberry32(seed),
            "tick": 0,
            "over": False,
            "cause": "",
            "score": 0,
            "level": 0,
            "body": [head - 2, head - 1, head],
            "occupied": [False] * (COLS * ROWS),
            "dir": 1,
            "queue": [],
            "counter": 0,
            "foods": 0,
            "food": -1,
        }
        for cell in state["body"]:
            state["occupied"][cell] = True
        place_food(state)
        return state

    @classmethod
    def apply_input(cls, state, event):
        direction = event[1]
        if state["over"] or direction not in (0, 1, 2, 3):
            return
        queue = state["queue"]
        if len(queue) >= 2:
            return
        last = queue[-1] if queue else state["dir"]
        if direction == last or direction == (last + 2) % 4:
            return
        queue.append(direction)

    @classmethod
    def step(cls, state):
        state["counter"] += 1
        if state["counter"] >= step_every(state["foods"]):
            state["counter"] = 0
            if state["queue"]:
                state["dir"] = state["queue"].pop(0)
            body, occupied = state["body"], state["occupied"]
            head = body[-1]
            x = head % COLS + DX[state["dir"]]
            y = head // COLS + DY[state["dir"]]
            if x < 0 or x >= COLS or y < 0 or y >= ROWS:
                state["over"] = True
                state["cause"] = "wall"
            else:
                nxt = y * COLS + x
                eating = nxt == state["food"]
                if not eating:
                    occupied[body.pop(0)] = False
                if occupied[nxt]:
                    state["over"] = True
                    state["cause"] = "self"
                else:
                    body.append(nxt)
                    occupied[nxt] = True
                    if eating:
                        state["foods"] += 1
                        state["score"] += 10
                        state["level"] = state["foods"]
                        if not place_food(state):
                            state["over"] = True
                            state["cause"] = "win"
        state["tick"] += 1

    @classmethod
    def random_payload(cls, rng, state):
        return [rng.randint(0, 3)]

    @classmethod
    def demo_policy(cls, rng, skill, options=None):
        """حریصانه به سمت غذا، با بررسی فضای آزاد تا مار خودش را گیر نیندازد."""

        def reachable(occupied, start, limit):
            seen = {start}
            stack = [start]
            while stack and len(seen) < limit:
                cell = stack.pop()
                cx, cy = cell % COLS, cell // COLS
                for d in range(4):
                    x, y = cx + DX[d], cy + DY[d]
                    if 0 <= x < COLS and 0 <= y < ROWS:
                        nxt = y * COLS + x
                        if nxt not in seen and not occupied[nxt]:
                            seen.add(nxt)
                            stack.append(nxt)
            return len(seen)

        def policy(state, tick):
            # درست قبل از حرکت بعدی مار تصمیم می‌گیرد
            if state["counter"] != step_every(state["foods"]) - 1 or state["queue"]:
                return None
            head = state["body"][-1]
            hx, hy = head % COLS, head // COLS
            fx, fy = state["food"] % COLS, state["food"] // COLS
            current = state["dir"]
            if skill < 95 and rng.random() < 0.03:
                return [(current + rng.choice([1, 3])) % 4]
            best, best_key = None, None
            for d in (current, (current + 1) % 4, (current + 3) % 4):
                x, y = hx + DX[d], hy + DY[d]
                if not (0 <= x < COLS and 0 <= y < ROWS):
                    continue
                nxt = y * COLS + x
                if state["occupied"][nxt] and nxt != state["body"][0]:
                    continue
                room = reachable(state["occupied"], nxt, len(state["body"]) + 12)
                key = (room < len(state["body"]) + 2, abs(x - fx) + abs(y - fy))
                if best_key is None or key < best_key:
                    best, best_key = d, key
            if best is None or best == current:
                return None
            return [best]

        return policy
