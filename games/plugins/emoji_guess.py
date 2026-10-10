from core import texts
from core.textutils import answers_match, normalize_fa
from games.engine.base import IncomingMessage
from games.engine.registry import register_game
from games.engine.rounds import RoundGame


@register_game
class EmojiGuessGame(RoundGame):
    key = "emoji_guess"
    title_fa = "حدس با ایموجی"
    emoji = "🤔"
    description_fa = "ایموجی‌ها اسم یک فیلم، ضرب‌المثل یا چیز معروف را نشان می‌دهند؛ اولین حدس درست برنده است."
    rounds = 6
    round_seconds = 35
    points = 10

    async def start(self) -> None:
        self.puzzles = await self.ctx.content.emoji_puzzles(self.total_rounds)
        await self.next_round()

    def _question(self, hint: str = "") -> str:
        return texts.EMOJI_QUESTION.format(header=self.header(), emojis=self.puzzle["emojis"], hint=hint)

    async def begin_round(self) -> None:
        self.puzzle = self.puzzles[self.round_no - 1]
        self.accepted = [self.puzzle["answer"], *self.puzzle.get("alt_answers", [])]
        self.message_id = await self.ctx.send(self._question())
        self.ctx.set_timer("hint", self.round_seconds / 2, self._hint)

    async def _hint(self) -> None:
        if self.round_open:
            answer = normalize_fa(self.puzzle["answer"], keep_spaces=False)
            hint = texts.EMOJI_HINT.format(count=texts.fa_num(len(answer)), letter=answer[0])
            await self.ctx.edit(self.message_id, self._question(hint), urgent=True)

    async def on_message(self, msg: IncomingMessage) -> None:
        if not self.round_open or not any(answers_match(msg.text, a) for a in self.accepted):
            return
        self.add_score(msg.player.user_id, self.points)
        await self.ctx.send(
            texts.ROUND_WON.format(
                name=msg.player.mention, answer=self.puzzle["answer"], points=texts.fa_num(self.points)
            )
        )
        await self.close_round()

    async def on_round_timeout(self) -> None:
        await self.ctx.send(texts.ROUND_TIMEOUT.format(answer=self.puzzle["answer"]))
