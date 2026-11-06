"""شبیه‌سازهای سمت سرور بازی‌های آرکید.

هر بازی یک ``core.js`` (کلاینت) و یک ماژول پایتونی در همین پوشه دارد که دقیقاً همان
منطق قطعی را پیاده می‌کند. برای اضافه کردن بازی جدید فقط همین دو فایل لازم است.
"""

import importlib
import pkgutil

from .base import ArcadeSimulator, SimResult, register_simulator, registry

_loaded = False

# بازی‌هایی که فعلاً از ربات و مینی‌اپ برداشته شده‌اند تا منو خلوت‌تر باشد. کدشان (شبیه‌ساز، core.js و صفحه) سر جایش
# است و مسابقه‌های در جریان و آمارهای قبلی‌شان کار می‌کند؛ برای برگرداندن هر کدام کافی است از همین فهرست حذفش کنی.
RETIRED = frozenset({"colorswitch", "g2048", "helix", "stack", "jumper", "runner", "timing", "breakout"})


def load_simulators() -> None:
    global _loaded
    if _loaded:
        return
    for module in pkgutil.iter_modules(__path__):
        if module.name not in ("base", "rng", "autoplay") and not module.name.startswith("_"):
            importlib.import_module(f"{__name__}.{module.name}")
    _loaded = True


def all_simulators(include_retired: bool = False) -> dict[str, type[ArcadeSimulator]]:
    """شبیه‌سازهای فعال؛ با ``include_retired`` بازی‌های کنار گذاشته‌شده (``RETIRED``) هم می‌آیند."""
    load_simulators()
    return {k: v for k, v in registry.items() if include_retired or k not in RETIRED}


def get_simulator(key: str) -> type[ArcadeSimulator] | None:
    load_simulators()
    return registry.get(key)


__all__ = ["RETIRED", "ArcadeSimulator", "SimResult", "all_simulators", "get_simulator", "register_simulator"]
