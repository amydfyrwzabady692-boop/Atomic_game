"""ثبت پلاگین‌های بازی. هر ماژول داخل ``games/plugins`` خودکار بارگذاری می‌شود."""

import importlib
import pkgutil

from .base import BaseGame

_REGISTRY: dict[str, type[BaseGame]] = {}
_loaded = False


def register_game(cls: type[BaseGame]) -> type[BaseGame]:
    if not cls.key:
        raise ValueError(f"{cls.__name__} کلید (key) ندارد")
    if cls.key in _REGISTRY and _REGISTRY[cls.key] is not cls:
        raise ValueError(f"کلید بازی تکراری است: {cls.key}")
    _REGISTRY[cls.key] = cls
    return cls


def load_plugins() -> None:
    global _loaded
    if _loaded:
        return
    from games import plugins

    for module in pkgutil.iter_modules(plugins.__path__):
        if not module.name.startswith("_"):
            importlib.import_module(f"games.plugins.{module.name}")
    _loaded = True


def all_games() -> dict[str, type[BaseGame]]:
    load_plugins()
    return dict(_REGISTRY)


def get_game(key: str) -> type[BaseGame] | None:
    load_plugins()
    return _REGISTRY.get(key)
