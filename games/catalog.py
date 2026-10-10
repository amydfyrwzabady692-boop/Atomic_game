"""فهرست یکپارچه‌ی همه‌ی بازی‌ها (متنی + آرکید) برای منوی ساخت مسابقه و تنظیمات گروه."""

from dataclasses import dataclass, field

ARCADE_PREFIX = "arcade_"
ARCADE_CATEGORIES = {"speed": "سرعتی", "skill": "مهارتی", "stage": "مرحله‌ای"}


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

    @property
    def is_arcade(self) -> bool:
        return self.kind == "arcade"

    @property
    def arcade_key(self) -> str:
        return self.key[len(ARCADE_PREFIX) :] if self.is_arcade else ""


def catalog() -> dict[str, GameInfo]:
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
        )
    for key, sim in all_simulators().items():
        full_key = ARCADE_PREFIX + key
        games[full_key] = GameInfo(
            key=full_key,
            title_fa=sim.title_fa,
            emoji=sim.emoji,
            description_fa=sim.description_fa,
            min_players=2,
            max_players=30,
            kind="arcade",
            category=sim.category,
            variant_title_fa=sim.variant_title_fa,
            variants=dict(sim.variants),
            suggested_minutes=sim.suggested_minutes,
        )
    return games


def get_info(key: str) -> GameInfo | None:
    return catalog().get(key)
