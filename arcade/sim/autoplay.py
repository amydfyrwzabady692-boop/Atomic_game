"""بازیکن خودکار برای ساخت لاگ‌های ورودی آزمایشی (fixtureهای تست تطابق JS/Python).

هر شبیه‌ساز می‌تواند ``demo_policy`` داشته باشد: تابعی که در هر تیک وضعیت را می‌بیند و
payload ورودی (بدون زمان) یا ``None`` برمی‌گرداند. این کد فقط برای تست است و در کلاینت
وجود ندارد.
"""

import random

from .base import ArcadeSimulator


def autoplay(sim: type[ArcadeSimulator], seed: int, policy, max_ms: int, options: dict | None = None):
    """بازی را با ``policy`` جلو می‌برد و ``(inputs, duration_ms)`` برمی‌گرداند."""
    state = sim.new_state(seed, sim.config(seed, options))
    tick_ms = sim.TICK_MS
    inputs: list[list[int]] = []
    tick = 0
    while not state["over"] and tick * tick_ms < max_ms:
        payload = policy(state, tick)
        if payload is not None:
            event = [tick * tick_ms, *payload]
            inputs.append(event)
            sim.apply_input(state, event)
            if state["over"]:
                break
        sim.step(state)
        tick += 1
    return inputs, tick * tick_ms


def random_policy(rng: random.Random, sim: type[ArcadeSimulator], every_ticks: int = 20):
    """ورودی‌های تصادفی با فاصله‌ی انسانی؛ برای پوشش مسیرهای باخت."""
    next_at = [rng.randint(5, every_ticks)]

    def policy(state, tick):
        if tick < next_at[0]:
            return None
        next_at[0] = tick + rng.randint(max(4, every_ticks // 2), every_ticks * 2)
        return sim.random_payload(rng, state)

    return policy


def build_cases(sim: type[ArcadeSimulator], count: int = 6) -> list[dict]:
    """چند لاگ ورودی ثابت + نتیجه‌ی مورد انتظار برای این بازی می‌سازد."""
    cases = []
    variants = list(sim.variants) or [""]
    for i in range(count):
        rng = random.Random(f"{sim.key}:{i}")
        seed = rng.randint(1, 2**31 - 2)
        options = {"variant": variants[i % len(variants)]} if variants[0] else {}
        max_ms = min(sim.MAX_DURATION_MS, sim.FIXTURE_MS)
        if i < count - 2:
            skill = [100, 97, 90, 100][i % 4]
            policy = sim.demo_policy(rng, skill, options)
            kind = f"demo-{skill}"
        elif i == count - 2:
            policy = random_policy(rng, sim)
            kind = "random"
        else:

            def policy(state, tick):
                return None

            max_ms = min(max_ms, 20_000)
            kind = "idle"
        inputs, duration_ms = autoplay(sim, seed, policy, max_ms, options)
        result = sim.simulate(seed, inputs, duration_ms, options)
        cases.append(
            {
                "kind": kind,
                "seed": seed,
                "options": options,
                "duration_ms": duration_ms,
                "inputs": inputs,
                "expected": result.as_dict(),
            }
        )
    return cases
