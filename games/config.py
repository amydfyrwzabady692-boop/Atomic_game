"""تنظیمات سراسری هر بازی که از پنل ادمین عوض می‌شود: فعال/غیرفعال و تعداد شرکت‌کننده.

مقادیر در حافظه کش می‌شوند تا کد async ربات هم (که اجازه‌ی کوئری مستقیم ندارد) بتواند
بدون رفتن به دیتابیس آن‌ها را بخواند. ربات کش را با ``reload`` تازه نگه می‌دارد.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, replace

logger = logging.getLogger(__name__)

CACHE_SECONDS = 10


@dataclass(frozen=True)
class GameOverride:
    enabled: bool
    min_players: int
    max_players: int


_cache: dict = {"at": None, "data": {}}


def _in_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def reload() -> dict[str, GameOverride]:
    """تنظیمات را از دیتابیس می‌خواند (همگام؛ در کد async با ``db(config.reload)`` صدا بزنید)."""
    from .models import GameSetting

    data = {
        s.game_key: GameOverride(s.is_enabled, s.min_players, s.max_players) for s in GameSetting.objects.all()
    }
    _cache["at"] = time.monotonic()
    _cache["data"] = data
    return data


def invalidate() -> None:
    _cache["at"] = None


def reset() -> None:
    """کش را خالی می‌کند (برای تست‌ها)."""
    _cache["at"] = None
    _cache["data"] = {}


def overrides() -> dict[str, GameOverride]:
    stale = _cache["at"] is None or time.monotonic() - _cache["at"] > CACHE_SECONDS
    if stale and not _in_event_loop():
        try:
            reload()
        except Exception:  # دیتابیس هنوز آماده نیست (مثلاً قبل از migrate): با آخرین مقادیر ادامه می‌دهیم
            logger.debug("game settings unavailable", exc_info=True)
    return _cache["data"]


def clamp_players(info, min_players: int, max_players: int) -> tuple[int, int]:
    """تعداد شرکت‌کننده را در بازه‌ی مجاز همان بازی نگه می‌دارد."""
    max_players = max(info.floor, min(info.ceiling, max_players))
    min_players = max(info.floor, min(max_players, min_players))
    return min_players, max_players


def apply(info, override: GameOverride | None):
    if override is None:
        return info
    min_players, max_players = clamp_players(info, override.min_players, override.max_players)
    return replace(info, min_players=min_players, max_players=max_players, enabled=override.enabled)


def sync_rows() -> int:
    """برای هر بازی کاتالوگ یک ردیف تنظیمات می‌سازد (اگر نباشد). تعداد ردیف‌های تازه را برمی‌گرداند."""
    from .catalog import defaults
    from .models import GameSetting

    existing = set(GameSetting.objects.values_list("game_key", flat=True))
    new = [
        GameSetting(game_key=key, min_players=info.default_min, max_players=info.default_max)
        for key, info in defaults().items()
        if key not in existing
    ]
    if new:
        GameSetting.objects.bulk_create(new, ignore_conflicts=True)
        invalidate()
    return len(new)
