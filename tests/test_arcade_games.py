"""قواعد و ناورداهای منطق بازی‌های آرکید (شبیه‌ساز پایتون)."""

import json
import random

import pytest

from arcade.sim import (
    all_simulators,
    breakout,
    colorswitch,
    flappy,
    g2048,
    get_simulator,
    helix,
    jumper,
    pins,
    runner,
    snake,
    stack,
    tiles,
    timber,
    timing,
    whack,
)
from arcade.sim.autoplay import autoplay
from arcade.sim.rng import Mulberry32

SIMS = all_simulators()
SEEDS = (7, 1234, 987654, 2_000_000_011)


def run(sim, seed, inputs, duration_ms, options=None):
    return sim.simulate(seed, inputs, duration_ms, options)


# ====================================================================== مشترک
def test_mulberry32_reference_values():
    """مقادیر مرجع mulberry32؛ همین اعداد در JS هم باید بیرون بیاید (تست تطابق این را پوشش می‌دهد)."""
    rng = Mulberry32(1)
    values = [rng.next_u32() for _ in range(3)]
    assert values == [2693262067, 11749833, 2265367787]
    assert all(0 <= Mulberry32(s).int(10) < 10 for s in range(50))
    assert {Mulberry32(s).range(3, 5) for s in range(200)} == {3, 4, 5}


@pytest.mark.parametrize("key", sorted(SIMS))
def test_simulation_is_deterministic_and_bounded(key):
    sim = SIMS[key]
    rng = random.Random(key)
    inputs, duration = autoplay(sim, 4242, sim.demo_policy(rng, 100), 15_000)
    first = run(sim, 4242, inputs, duration)
    second = run(sim, 4242, inputs, duration)
    assert first == second
    assert first.score >= 0 and first.duration_ms <= duration
    # کوتاه کردن مدت، بازی را زودتر متوقف می‌کند و هیچ‌وقت امتیاز بیشتری نمی‌دهد
    half = run(sim, 4242, inputs, duration // 2)
    assert half.duration_ms <= duration // 2 + sim.TICK_MS


@pytest.mark.parametrize("key", sorted(SIMS))
def test_garbage_payloads_never_crash_the_server_simulator(key):
    """کلاینت دستکاری‌شده هر عددی می‌تواند بفرستد؛ شبیه‌ساز نباید خطا بدهد."""
    sim = SIMS[key]
    rng = random.Random(f"fuzz:{key}")
    for round_ in range(6):
        t = 0
        inputs = []
        for _ in range(120):
            t += rng.randint(0, 400)
            payload = [rng.choice([-9_999_999, -3, -1, 0, 1, 2, 3, 4, 7, 9, 64, 5000, 9_999_999]) for _ in range(sim.INPUT_ARITY - 1)]
            inputs.append([t, *payload])
        duration = min(t + 2000, sim.MAX_DURATION_MS)
        inputs = [e for e in inputs if e[0] <= duration]
        assert sim.validate_inputs(inputs, duration) is None
        result = run(sim, 1000 + round_, inputs, duration)
        assert result.score >= 0


@pytest.mark.parametrize("key", sorted(SIMS))
def test_inputs_after_game_over_are_ignored(key):
    sim = SIMS[key]
    rng = random.Random(1)
    inputs, duration = autoplay(sim, 99, sim.demo_policy(rng, 100), 8000)
    base = run(sim, 99, inputs, duration)
    if base.over:
        extra = inputs + [[duration + 16 * i, *([0] * (sim.INPUT_ARITY - 1))] for i in range(1, 30)]
        assert run(sim, 99, extra, duration + 2000).score == base.score


def test_validate_inputs_limits():
    sim = get_simulator("pins")
    assert sim.validate_inputs([[0], [16], [16]], 1000) is None
    assert sim.validate_inputs([[0]] * (sim.MAX_INPUTS + 1), 1000) == "bad_inputs"
    assert sim.validate_inputs([], sim.MAX_DURATION_MS + 1) == "bad_duration"
    assert sim.validate_inputs([], -1) == "bad_duration"
    assert sim.validate_inputs([], 1.5) == "bad_duration"
    assert sim.validate_inputs([[1.5]], 100) == "bad_inputs"


# ====================================================================== سیخ‌زن
def test_pins_has_50_handmade_levels_with_bosses():
    levels = pins.load_levels()
    assert len(levels) >= 50
    for index, level in enumerate(levels):
        assert level["pins"] >= 3 and level["speed"] > 0 and level["pattern"]
        assert bool(level.get("boss")) == (index % 5 == 4)  # هر ۵ مرحله یک باس
        assert len(set(level["pre"])) == len(level["pre"])
    # سختی کم‌کم بیشتر می‌شود
    assert levels[-1]["speed"] > levels[0]["speed"] and levels[-1]["pins"] > levels[0]["pins"]


@pytest.mark.parametrize("seed", SEEDS)
def test_every_handmade_and_procedural_level_is_solvable(seed):
    """بازیکن کامل باید هر مرحله (۵۰ دست‌ساز + ۲۰ رویه‌ای) را در زمان معقول تمام کند."""
    sim = get_simulator("pins")
    for index in range(70):
        state = sim.new_state(seed, {})
        state["level"] = index
        pins.load_level(state)
        policy = sim.demo_policy(random.Random(1), 100)
        tick = 0
        while state["level"] == index and not state["over"] and tick < 60_000 // sim.TICK_MS:
            if policy(state, tick) is not None:
                sim.apply_input(state, [tick * sim.TICK_MS])
            sim.step(state)
            tick += 1
        assert state["level"] == index + 1, f"level {index + 1} not solvable for seed {seed}"


def test_pins_collision_is_pure_angular_distance():
    sim = get_simulator("pins")
    state = sim.new_state(5, {})
    state["pins"] = [(pins.BOTTOM - state["angle"]) % pins.CIRCLE]  # سیخی دقیقاً در نقطه‌ی فرود
    state["lv"]["speed"] = 0
    sim.apply_input(state, [0])
    for _ in range(pins.FLIGHT_TICKS + 1):
        sim.step(state)
    assert state["over"] and state["cause"] == "hit"


def test_higher_pins_level_always_scores_more():
    """کسی که مرحله‌ی بالاتری را تمام کرده، از کسی که در مرحله‌ی قبل باخته امتیاز بیشتری دارد."""
    levels = pins.load_levels()
    best_if_failed_here = 0  # بیشترین امتیاز ممکن تا قبل از تمام کردن این مرحله
    least_if_cleared = 0  # کمترین امتیاز ممکن بعد از تمام کردن مرحله‌ی قبل
    for number, level in enumerate(levels, start=1):
        fail_max = best_if_failed_here + (level["pins"] - 1) * pins.PIN_POINTS
        clear_min = least_if_cleared + level["pins"] * pins.PIN_POINTS + 100 + 20 * number
        clear_max = best_if_failed_here + level["pins"] * pins.PIN_POINTS + 100 + 20 * number + 20
        assert clear_min > fail_max
        best_if_failed_here, least_if_cleared = clear_max, clear_min


# ====================================================================== هیزم‌شکن
@pytest.mark.parametrize("seed", SEEDS)
def test_timber_never_generates_adjacent_opposite_branches(seed):
    state = get_simulator("timber").new_state(seed, {})
    branches = [seg["b"] for seg in state["segs"]]
    for _ in range(3000):
        branches.append(timber.generate(state)["b"])
    assert branches[:3] == [0, 0, 0]
    for below, above in zip(branches, branches[1:], strict=False):
        assert not (below and above and below != above)
    assert {0, 1, 2} <= set(branches)


def test_timber_branch_kills_and_time_runs_out():
    sim = get_simulator("timber")
    state = sim.new_state(3, {})
    state["segs"][1] = {"b": 1, "c": 0}
    sim.apply_input(state, [0, 0])  # ضربه از چپ؛ شاخه‌ی چپ روی سرش می‌افتد
    assert state["over"] and state["cause"] == "branch" and state["score"] == 1

    idle = sim.new_state(3, {})
    sim.apply_input(idle, [0, 1])
    for _ in range(2000):
        sim.step(idle)
        if idle["over"]:
            break
    assert idle["cause"] == "time"


def test_timber_clock_item_adds_time():
    sim = get_simulator("timber")
    state = sim.new_state(3, {})
    state["time"] = 1000
    state["segs"][0] = {"b": 0, "c": 2}
    sim.apply_input(state, [0, 1])
    assert state["time"] == 1000 + timber.CLOCK_GAIN + timber.GAIN


# ====================================================================== دونده
@pytest.mark.parametrize("seed", SEEDS)
def test_runner_always_has_a_reachable_safe_path(seed):
    state = get_simulator("runner").new_state(seed, {})
    while len(state["rows"]) < 600:
        runner.generate(state)
    previous = {0, 1, 2}
    for row in state["rows"]:
        safe = {lane for lane in range(3) if row[lane] in (0, 3)}
        assert safe
        # از یکی از خط‌های امن ردیف قبل، با حداکثر یک جابه‌جایی به خط امن این ردیف می‌رسیم
        assert any(abs(a - b) <= 1 for a in previous for b in safe)
        previous = safe


def test_runner_jump_clears_low_obstacle_but_not_high():
    sim = get_simulator("runner")
    for cell, survives in ((1, True), (2, False)):
        state = sim.new_state(1, {})
        state["rows"][0] = [cell, cell, cell]
        ticks = runner.row_z(state, 0) // runner.speed_for(0)
        for tick in range(ticks + 3):
            if tick == ticks - 10:
                sim.apply_input(state, [0, 2])
            sim.step(state)
        assert state["over"] is not survives


# ====================================================================== پرش ابرها
@pytest.mark.parametrize("seed", SEEDS)
def test_jumper_platforms_are_always_reachable(seed):
    state = get_simulator("jumper").new_state(seed, {})
    while state["made"] < 400:
        jumper.generate(state)
    max_height = jumper.JUMP * jumper.JUMP // (2 * jumper.GRAVITY)
    plats = state["plats"]
    for below, above in zip(plats[1:], plats[2:], strict=False):
        assert 0 < above["y"] - below["y"] < max_height - 300
        shift = (above["x"] - below["x"]) % jumper.WIDTH
        assert min(shift, jumper.WIDTH - shift) <= jumper.MAX_SHIFT


def test_jumper_fragile_platform_breaks_after_one_bounce():
    sim = get_simulator("jumper")
    state = sim.new_state(1, {})
    state["plats"] = [{"y": 0, "x": 0, "w": jumper.WIDTH, "type": 2, "spring": False, "phase": 0, "alive": True}]
    state["topY"] = 10**9  # سکوی دیگری ساخته نشود
    sim.apply_input(state, [0, 1])
    sim.step(state)
    assert state["vy"] == jumper.JUMP and state["plats"][0]["alive"] is False
    for _ in range(400):
        sim.step(state)
        if state["over"]:
            break
    assert state["cause"] == "fall"


# ====================================================================== ۲۰۴۸
def test_2048_same_seed_and_moves_give_same_tiles():
    sim = get_simulator("g2048")
    moves = [[100 + i * 200, d] for i, d in enumerate([2, 3, 2, 1, 0, 3, 2, 2, 3, 1] * 3)]
    a, b, c = sim.new_state(77, {}), sim.new_state(77, {}), sim.new_state(78, {})
    for move in moves:
        for state in (a, b, c):
            sim.apply_input(state, move)
    assert a["grid"] == b["grid"] and a["score"] == b["score"]
    assert a["grid"] != c["grid"]
    assert sum(1 for v in sim.new_state(5, {})["grid"] if v) == 2


def test_2048_merge_rules_and_time_limit():
    grid = [2, 2, 2, 2, 4, 0, 4, 0, 2, 4, 8, 16, 0, 0, 0, 0]
    moved, gained = g2048.slide(grid, 3)
    assert moved and gained == 16
    assert grid[:8] == [4, 4, 0, 0, 8, 0, 0, 0] and grid[8:12] == [2, 4, 8, 16]
    assert g2048.slide([2, 4, 8, 16] * 4, 3) == (False, 0)
    assert g2048.stuck([2, 4, 2, 4, 4, 2, 4, 2, 2, 4, 2, 4, 4, 2, 4, 2])
    result = run(get_simulator("g2048"), 1, [], 121_000)
    assert result.over and result.cause == "time" and result.duration_ms == 120_000


# ====================================================================== بقیه‌ی بازی‌ها
def test_stack_perfect_keeps_width_and_miss_ends():
    sim = get_simulator("stack")
    state = sim.new_state(1, {})
    state["cur"]["x"] = state["blocks"][0]["x"] + 20  # در محدوده‌ی «دقیق»
    sim.apply_input(state, [0])
    assert state["blocks"][1] == state["blocks"][0] and state["combo"] == 1
    state["cur"]["x"] = state["blocks"][-1]["x"] + 500
    sim.apply_input(state, [16])
    assert state["blocks"][-1]["w"] == stack.BASE_W - 500 and state["combo"] == 0
    state["cur"]["x"] = -5000
    sim.apply_input(state, [32])
    assert state["over"] and state["cause"] == "miss"


def test_flappy_gaps_stay_inside_field_and_get_tighter():
    assert flappy.gap_for(0) > flappy.gap_for(100) >= 1250
    assert flappy.speed_for(0) < flappy.speed_for(100)
    sim = get_simulator("flappy")
    inputs, duration = autoplay(sim, 5, sim.demo_policy(random.Random(2), 100), 40_000)
    state = sim.new_state(5, {})
    seen = 0
    for tick in range(duration // sim.TICK_MS):
        for event in [e for e in inputs if e[0] // sim.TICK_MS == tick]:
            sim.apply_input(state, event)
        sim.step(state)
        for pipe in state["pipes"]:
            seen += 1
            assert 0 < pipe["gapY"] and pipe["gapY"] + pipe["gapH"] < flappy.FIELD_H
    assert seen > 0
    assert run(sim, 5, [[100]], 20_000).cause == "ground"  # یک پرش و بعد سقوط


def test_timing_hit_miss_and_lives():
    sim = get_simulator("timing")
    state = sim.new_state(4, {})
    zone = state["zone"]
    state["pos"] = zone["s"] + zone["w"] // 2
    sim.apply_input(state, [0])
    assert state["score"] == 20 and state["level"] == 1  # وسط ناحیه = امتیاز دوبرابر
    state["pos"] = state["zone"]["s"] + 1
    sim.apply_input(state, [16])
    assert state["score"] == 30
    for i in range(timing.LIVES):
        state["pos"] = (state["zone"]["s"] + state["zone"]["w"] + 200) % timing.BAR
        if state["zone"]["s"] <= state["pos"] <= state["zone"]["s"] + state["zone"]["w"]:
            state["pos"] = state["zone"]["s"] - 100
        sim.apply_input(state, [32 + i * 16])
    assert state["over"] and state["cause"] == "miss"


def test_tiles_modes():
    sim = get_simulator("tiles")
    endless = sim.new_state(9, {"variant": "endless"})
    wrong = (endless["cols"][0] + 1) % 4
    sim.apply_input(endless, [0, wrong])
    assert endless["over"] and endless["cause"] == "wrong"

    missed = sim.new_state(9, {})
    sim.apply_input(missed, [0, missed["cols"][0]])
    for _ in range(600):
        sim.step(missed)
        if missed["over"]:
            break
    assert missed["cause"] == "miss" and missed["score"] == 1

    fifty = sim.new_state(9, {"variant": "fifty"})
    for i in range(tiles.TARGET):
        sim.apply_input(fifty, [i * 160, fifty["cols"][fifty["hits"]]])
        for _ in range(10):
            sim.step(fifty)
    assert fifty["over"] and fifty["cause"] == "done"
    assert fifty["score"] == 1000 + (30000 - 49 * 160) // 10
    assert fifty["score"] > tiles.TARGET * 10  # تمام کردن همیشه از نیمه‌کاره ماندن بهتر است


def test_whack_scoring_and_bomb_penalty():
    sim = get_simulator("whack")
    state = sim.new_state(2, {})
    state["holes"][0] = {"type": 1, "until": 999, "born": 0}
    state["holes"][1] = {"type": 3, "until": 999, "born": 0}
    state["holes"][2] = {"type": 2, "until": 999, "born": 0}
    sim.apply_input(state, [0, 2])  # بمب با امتیاز صفر: منفی نمی‌شود
    assert state["score"] == 0
    sim.apply_input(state, [16, 0])
    sim.apply_input(state, [32, 1])
    assert state["score"] == 40 and state["hits"] == 2
    sim.apply_input(state, [48, 0])  # سوراخ خالی
    state["holes"][3] = {"type": 2, "until": 999, "born": 0}
    sim.apply_input(state, [64, 3])
    assert state["score"] == 25
    assert run(sim, 2, [], 61_000).cause == "time"
    assert whack.LIMIT_TICKS * sim.TICK_MS == 60_000


def test_snake_rules():
    sim = get_simulator("snake")
    state = sim.new_state(3, {})
    sim.apply_input(state, [0, 3])  # برگشت ۱۸۰ درجه مجاز نیست
    assert state["queue"] == []
    head = state["body"][-1]
    state["food"] = head + 1
    for _ in range(snake.step_every(0)):
        sim.step(state)
    assert state["score"] == 10 and len(state["body"]) == 4 and state["food"] != head + 1
    assert state["food"] not in state["body"]
    wall = run(sim, 3, [], 60_000)
    assert wall.over and wall.cause == "wall"


def test_helix_safe_start_and_fire_mode():
    sim = get_simulator("helix")
    for seed in SEEDS:
        state = sim.new_state(seed, {})
        first = state["floors"][0]
        assert first["reds"] == []
        local = (helix.BALL_ANGLE - state["rot"]) % helix.CIRCLE
        assert helix.sector(first, local) == 1  # توپ روی سکو شروع می‌کند، نه روی شکاف
        idle = run(sim, seed, [], 20_000)
        assert not idle.over and idle.score == 0  # بدون ورودی فقط بالا و پایین می‌پرد

    state = sim.new_state(1, {})
    floor = state["floors"][1]
    floor["reds"] = [[0, helix.CIRCLE - 1]]  # تقریباً تمام طبقه قرمز
    floor["gapSize"] = 1000
    state["rot"] = (helix.BALL_ANGLE - (floor["gapStart"] + 180000)) % helix.CIRCLE
    normal = dict(state, floorIdx=2, y=2 * helix.FLOOR_H - 10, vy=20, streak=0)
    sim.step(normal)
    assert normal["over"] and normal["cause"] == "red"
    fiery = dict(state, floorIdx=2, y=2 * helix.FLOOR_H - 10, vy=20, streak=helix.FIRE_STREAK)
    sim.step(fiery)
    assert not fiery["over"] and fiery["floorIdx"] == 3 and fiery["streak"] == 0


def test_colorswitch_color_always_changes_and_wrong_color_kills():
    sim = get_simulator("colorswitch")
    state = sim.new_state(8, {})
    for k in range(60):
        spec = colorswitch.spec_of(state, k)
        assert spec["type"] in (0, 1, 2) and 0 <= spec["next"] <= 2
        assert (state["color"] + 1 + spec["next"]) % 4 != state["color"]
    assert colorswitch.spec_of(state, 0)["type"] == 0 and colorswitch.spec_of(state, 1)["type"] == 0
    # پریدنِ بی‌وقفه بدون توجه به رنگ دیر یا زود به رنگ اشتباه می‌خورد
    reckless = run(sim, 8, [[i * 200] for i in range(1, 200)], 40_000)
    assert reckless.over and reckless.cause == "color"
    assert run(sim, 8, [], 20_000).score == 0


def test_breakout_levels_and_lives():
    levels = breakout.load_levels()
    assert len(levels) >= 10
    for layout in levels:
        assert 1 <= len(layout) <= breakout.ROWS
        assert all(len(row) == breakout.COLS and set(row) <= set("0123") for row in layout)
        assert any(ch != "0" for row in layout for ch in row)
    sim = get_simulator("breakout")
    # راکتی که هیچ‌وقت تکان نمی‌خورد و گوشه مانده، بالاخره هر سه جان را از دست می‌دهد
    lost = run(sim, 6, [[0, 0]], 300_000)
    assert lost.over and lost.cause == "out"
    state = sim.new_state(6, {})
    assert state["remaining"] == sum(ch != "0" for row in levels[0] for ch in row)
    state["bricks"] = [0] * 64
    state["bricks"][0] = 1
    state["remaining"] = 1
    breakout.damage(state, 0)
    assert state["level"] == 1 and state["pause"] == breakout.PAUSE_TICKS


def test_fixture_files_cover_every_registered_game():
    from tests.test_arcade_parity import FIXTURES

    files = {path.stem for path in FIXTURES.glob("*.json")}
    assert files == set(SIMS)
    for key in SIMS:
        cases = json.loads((FIXTURES / f"{key}.json").read_text(encoding="utf-8"))
        assert {c["kind"] for c in cases} >= {"random", "idle"}
