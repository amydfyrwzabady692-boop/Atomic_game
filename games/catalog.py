"""فهرست یکپارچه‌ی همه‌ی بازی‌ها (متنی + آرکید) برای منوی ساخت مسابقه و تنظیمات گروه.

تعداد شرکت‌کننده و فعال/غیرفعال بودن هر بازی از پنل ادمین قابل‌تغییر است (``games.config``)؛
مقادیر کلاس بازی فقط پیش‌فرض‌اند.
"""

from dataclasses import dataclass, field

from . import config

ARCADE_PREFIX = "arcade_"
ARCADE_CATEGORIES = {"speed": "سرعتی", "skill": "مهارتی", "stage": "مرحله‌ای"}
ARCADE_DEFAULT_MAX = 30
ARCADE_CEILING = 50


@dataclass(frozen=True)
class GameInfo:
    key: str
    title_fa: str
    emoji: str
    description_fa: str
    min_players: int
    max_players: int
    kind: str = "text"  # text | arcade
    category: str = ""  # فقط آرکید: speed | skill | stage
    variant_title_fa: str = ""
    variants: dict = field(default_factory=dict)
    suggested_minutes: int = 5
    # پیش‌فرض‌ها و بازه‌ی مجاز تنظیم تعداد شرکت‌کننده از پنل ادمین
    default_min: int = 2
    default_max: int = 20
    floor: int = 2
    ceiling: int = 50
    enabled: bool = True

    @property
    def is_arcade(self) -> bool:
        return self.kind == "arcade"

    @property
    def arcade_key(self) -> str:
        return self.key[len(ARCADE_PREFIX) :] if self.is_arcade else ""

    @property
    def fixed_players(self) -> bool:
        """بازی‌هایی مثل شطرنج که تعداد بازیکنشان قابل‌تغییر نیست."""
        return self.floor == self.ceiling


def defaults() -> dict[str, GameInfo]:
    from arcade.sim import all_simulators
    from games.engine.registry import all_games

    games: dict[str, GameInfo] = {}
    for key, cls in all_games().items():
        games[key] = GameInfo(
            key=key,
            title_fa=cls.title_fa,
            emoji=cls.emoji,
            description_fa=cls.description_fa,
            min_players=cls.min_players,
            max_players=cls.max_players,
            variant_title_fa=cls.variant_title_fa,
            variants=dict(cls.variants),
            default_min=cls.min_players,
            default_max=cls.max_players,
            floor=cls.players_floor,
            ceiling=max(cls.players_ceiling, cls.players_floor),
        )
    for key, sim in all_simulators().items():
        full_key = ARCADE_PREFIX + key
        games[full_key] = GameInfo(
            key=full_key,
            title_fa=sim.title_fa,
            emoji=sim.emoji,
            description_fa=sim.description_fa,
            min_players=2,
            max_players=ARCADE_DEFAULT_MAX,
            kind="arcade",
            category=sim.category,
            variant_title_fa=sim.variant_title_fa,
            variants=dict(sim.variants),
            suggested_minutes=sim.suggested_minutes,
            default_min=2,
            default_max=ARCADE_DEFAULT_MAX,
            floor=2,
            ceiling=ARCADE_CEILING,
        )
    return games


def catalog(include_disabled: bool = False) -> dict[str, GameInfo]:
    """بازی‌ها با تنظیمات پنل ادمین. بازی‌های غیرفعال فقط با ``include_disabled`` برمی‌گردند."""
    games = {}
    overrides = config.overrides()
    for key, info in defaults().items():
        info = config.apply(info, overrides.get(key))
        if info.enabled or include_disabled:
            games[key] = info
    return games


def arcade_enabled(arcade_key: str) -> bool:
    """آیا این بازی آرکید (با کلید شبیه‌ساز، بدون پیشوند) از پنل ادمین فعال است؟"""
    override = config.overrides().get(ARCADE_PREFIX + arcade_key)
    return override is None or override.enabled


def get_info(key: str) -> GameInfo | None:
    """اطلاعات یک بازی، حتی اگر غیرفعال شده باشد (برای مسابقه‌های در جریان و گزارش‌ها)."""
    return catalog(include_disabled=True).get(key)
