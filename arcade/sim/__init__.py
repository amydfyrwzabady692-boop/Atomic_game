"""شبیه‌سازهای سمت سرور بازی‌های آرکید.

هر بازی یک ``core.js`` (کلاینت) و یک ماژول پایتونی در همین پوشه دارد که دقیقاً همان
منطق قطعی را پیاده می‌کند. برای اضافه کردن بازی جدید فقط همین دو فایل لازم است.
"""

import importlib
import pkgutil

from .base import ArcadeSimulator, SimResult, register_simulator, registry

_loaded = False


def load_simulators() -> None:
    global _loaded
    if _loaded:
        return
    for module in pkgutil.iter_modules(__path__):
        if module.name not in ("base", "rng", "autoplay") and not module.name.startswith("_"):
            importlib.import_module(f"{__name__}.{module.name}")
    _loaded = True


def all_simulators() -> dict[str, type[ArcadeSimulator]]:
    load_simulators()
    return dict(registry)


def get_simulator(key: str) -> type[ArcadeSimulator] | None:
    load_simulators()
    return registry.get(key)


__all__ = ["ArcadeSimulator", "SimResult", "all_simulators", "get_simulator", "register_simulator"]
