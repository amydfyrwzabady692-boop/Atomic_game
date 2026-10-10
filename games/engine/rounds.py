from typing import ClassVar

from .base import BaseGame


class RoundGame(BaseGame):
    """پایه‌ی بازی‌های راندی: هر راند یک تایمر دارد و بعد از مکثی کوتاه راند بعد شروع می‌شود."""

    round_seconds: ClassVar[int] = 25
    gap_seconds: ClassVar[int] = 3

    def __init__(self, ctx):
        super().__init__(ctx)
        self.round_open = False
        self.round_started_at = 0.0

    async def begin_round(self) -> None:
        raise NotImplementedError

    async def on_round_timeout(self) -> None:
        return None

    async def next_round(self) -> None:
        if self.round_no >= self.total_rounds:
            await self.ctx.end_game()
            return
        self.round_no += 1
        self.round_open = True
        self.round_started_at = self.ctx.now()
        await self.begin_round()
        if self.round_open:
            self.ctx.set_timer("round", self.round_seconds, self._round_timeout)

    async def _round_timeout(self) -> None:
        if not self.round_open:
            return
        self.round_open = False
        self.ctx.cancel_timer("hint")
        await self.on_round_timeout()
        self._schedule_next()

    async def close_round(self) -> None:
        """راند را (مثلاً بعد از جواب درست) می‌بندد و راند بعد را زمان‌بندی می‌کند."""
        if not self.round_open:
            return
        self.round_open = False
        self.ctx.cancel_timer("round")
        self.ctx.cancel_timer("hint")
        self._schedule_next()

    def _schedule_next(self) -> None:
        self.ctx.set_timer("gap", self.gap_seconds, self.next_round)

    def header(self) -> str:
        from core import texts

        return texts.ROUND_HEADER.format(n=texts.fa_num(self.round_no), total=texts.fa_num(self.total_rounds))
