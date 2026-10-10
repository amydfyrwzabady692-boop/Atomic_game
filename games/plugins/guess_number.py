from core import texts
from core.textutils import fa_num, parse_int
from games.engine.base import IncomingMessage
from games.engine.registry import register_game
from games.engine.rounds import RoundGame


@register_game
class GuessNumberGame(RoundGame):
    key = "guess_number"
    title_fa = "حدس عدد"
    emoji = "🔢"
    description_fa = "ربات عددی بین ۱ تا ۱۰۰۰ انتخاب می‌کند و می‌گوید حدس شما بزرگ‌تر است یا کوچک‌تر."
    rounds = 3
    round_seconds = 90
    points = 10
    low_bound = 1
    high_bound = 1000

    def _board(self, last: str = "") -> str:
        return texts.NUMBER_BOARD.format(
            header=self.header(), low=fa_num(self.low), high=fa_num(self.high), last=last
        )

    async def begin_round(self) -> None:
        self.target = self.ctx.rng.randint(self.low_bound, self.high_bound)
        self.low, self.high = self.low_bound, self.high_bound
        self.message_id = await self.ctx.send(self._board())

    async def on_message(self, msg: IncomingMessage) -> None:
        if not self.round_open:
            return
        guess = parse_int(msg.text)
        if guess is None or not self.low_bound <= guess <= self.high_bound:
            return
        if guess == self.target:
            self.add_score(msg.player.user_id, self.points)
            await self.ctx.send(
                texts.ROUND_WON.format(name=msg.player.mention, answer=fa_num(guess), points=fa_num(self.points))
            )
            await self.close_round()
            return
        # بازه‌ی شناخته‌شده روی یک پیام ثابت به‌روز می‌شود تا گروه با جواب‌های ربات شلوغ نشود
        if guess < self.target:
            self.low = max(self.low, guess + 1)
            last = texts.NUMBER_HIGHER.format(name=msg.player.name, guess=fa_num(guess))
        else:
            self.high = min(self.high, guess - 1)
            last = texts.NUMBER_LOWER.format(name=msg.player.name, guess=fa_num(guess))
        await self.ctx.edit(self.message_id, self._board(last))

    async def on_round_timeout(self) -> None:
        await self.ctx.send(texts.ROUND_TIMEOUT.format(answer=fa_num(self.target)))
