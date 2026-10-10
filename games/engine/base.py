"""قرارداد بین موتور و پلاگین‌های بازی.

پلاگین‌ها هیچ وابستگی مستقیمی به تلگرام یا دیتابیس ندارند؛ فقط با ``GameContext``
حرف می‌زنند. به همین خاطر منطق هر بازی بدون تلگرام و با یک context ساختگی تست می‌شود.
"""

from __future__ import annotations

import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import ClassVar, Protocol

from .payout import Standing

Buttons = list[list[tuple[str, str]]]  # ردیف‌هایی از (متن، داده‌ی callback محلی بازی)


@dataclass(frozen=True)
class Player:
    user_id: int  # کلید اصلی TelegramUser
    tg_id: int
    name: str

    @property
    def mention(self) -> str:
        from html import escape

        return f'<a href="tg://user?id={self.tg_id}">{escape(self.name)}</a>'


@dataclass
class IncomingMessage:
    """پیام متنی یک بازیکنِ عضو مسابقه (فوروارد، ادیت و پیام ربات‌ها قبلاً حذف شده‌اند)."""

    player: Player
    text: str
    message_id: int = 0
    date: float = 0.0


@dataclass
class IncomingCallback:
    """کلیک دکمه‌ی اینلاین مربوط به بازی. ``player`` برای غیرعضوها None است."""

    player: Player | None
    data: str
    message_id: int = 0
    answer: Callable[..., Awaitable[None]] | None = None
    answered: bool = field(default=False, repr=False)

    async def reply(self, text: str = "", alert: bool = False) -> None:
        self.answered = True
        if self.answer is not None:
            await self.answer(text, alert)


class ContentProvider(Protocol):
    async def random_words(self, count: int, min_len: int = 3, max_len: int = 8) -> list[str]: ...
    async def is_valid_word(self, word: str) -> bool: ...
    async def has_word_starting_with(self, letter: str, exclude: set[str]) -> bool: ...
    async def questions(self, category: str | None, count: int) -> list[dict]: ...
    async def emoji_puzzles(self, count: int) -> list[dict]: ...
    async def sentences(self, count: int) -> list[str]: ...


class GameContext(Protocol):
    players: list[Player]
    options: dict
    rng: random.Random
    content: ContentProvider

    def now(self) -> float: ...
    async def send(self, text: str, buttons: Buttons | None = None) -> int: ...
    async def edit(
        self, message_id: int, text: str, buttons: Buttons | None = None, urgent: bool = False
    ) -> None: ...
    async def send_photo(self, image: bytes, caption: str = "") -> int: ...
    async def send_dice(self, emoji: str) -> int: ...
    async def flash(self, text: str, seconds: int = 6) -> None: ...
    def set_timer(self, name: str, seconds: float, callback: Callable[[], Awaitable[None]]) -> None: ...
    def cancel_timer(self, name: str) -> None: ...
    async def end_game(self) -> None: ...


class BaseGame:
    """کلاس پایه‌ی همه‌ی بازی‌های متنی.

    برای ساخت بازی جدید یک فایل در ``games/plugins`` بسازید، از این کلاس ارث ببرید
    و با ``@register_game`` ثبتش کنید.
    """

    key: ClassVar[str] = ""
    title_fa: ClassVar[str] = ""
    description_fa: ClassVar[str] = ""
    emoji: ClassVar[str] = "🎮"
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 20
    rounds: ClassVar[int] = 5
    # گزینه‌ای که موقع ساخت بازی پرسیده می‌شود (مثل دسته‌ی کوییز): {مقدار: برچسب}
    variant_title_fa: ClassVar[str] = ""
    variants: ClassVar[dict[str, str]] = {}

    def __init__(self, ctx: GameContext):
        self.ctx = ctx
        self.players: list[Player] = list(ctx.players)
        self.by_id: dict[int, Player] = {p.user_id: p for p in self.players}
        self.scores: dict[int, int] = {p.user_id: 0 for p in self.players}
        self.reached_at: dict[int, float] = {}
        self.total_rounds: int = int(ctx.options.get("rounds") or self.rounds)
        self.round_no = 0
        self.finished = False

    # ------------------------------------------------------------ امتیاز
    def add_score(self, user_id: int, points: int) -> None:
        if points == 0:
            return
        self.scores[user_id] = self.scores.get(user_id, 0) + points
        self.reached_at[user_id] = self.ctx.now()

    def scoreboard_lines(self, limit: int = 10) -> list[str]:
        from core.textutils import fa_num

        order = sorted(self.players, key=lambda p: -self.scores[p.user_id])
        return [f"{p.name}: {fa_num(self.scores[p.user_id])}" for p in order[:limit]]

    # ------------------------------------------------------------ چرخه
    async def start(self) -> None:
        await self.next_round()

    async def on_message(self, msg: IncomingMessage) -> None:  # pragma: no cover - پیش‌فرض
        return None

    async def on_callback(self, cb: IncomingCallback) -> None:  # pragma: no cover - پیش‌فرض
        return None

    async def next_round(self) -> None:
        raise NotImplementedError

    async def finish(self) -> list[Standing]:
        """نتیجه‌ی نهایی. رتبه‌بندی و تقسیم جایزه را موتور انجام می‌دهد."""
        self.finished = True
        return [Standing(p.user_id, self.scores[p.user_id], self.reached_at.get(p.user_id)) for p in self.players]
