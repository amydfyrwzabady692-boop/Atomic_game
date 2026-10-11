from html import escape

from core import texts
from games.engine.base import PRIMARY, Button, IncomingCallback
from games.engine.registry import register_game
from games.engine.rounds import RoundGame


@register_game
class QuizGame(RoundGame):
    key = "quiz"
    title_fa = "کوییز"
    emoji = "❓"
    description_fa = "سوال چهارگزینه‌ای با دکمه. هر نفر فقط یک بار جواب می‌دهد و جواب سریع‌تر امتیاز بیشتری دارد."
    rounds = 7
    rules_fa = [
        "سؤال چهارگزینه‌ای است؛ جواب را با دکمه انتخاب کن.",
        "هر نفر فقط یک بار جواب می‌دهد؛ جواب درستِ سریع‌تر امتیاز بیشتری دارد.",
        "{rounds} سؤال، هر سؤال {round_seconds} ثانیه.",
    ]
    round_seconds = 15
    gap_seconds = 4
    base_points = 10
    speed_bonus = 10
    variant_title_fa = "دسته‌بندی"
    variants = dict(texts.QUIZ_CATEGORIES)

    async def start(self) -> None:
        category = self.ctx.options.get("variant") or "general"
        self.questions = await self.ctx.content.questions(category, self.total_rounds)
        await self.next_round()

    def _buttons(self):
        options = self.question["options"]
        cells = [Button(str(option), f"a:{self.round_no}:{index}", PRIMARY) for index, option in enumerate(options)]
        return [cells[i : i + 2] for i in range(0, len(cells), 2)]

    async def begin_round(self) -> None:
        self.question = self.questions[self.round_no - 1]
        self.answers: dict[int, int] = {}
        self.correct: list[int] = []
        self.message_id = await self.ctx.send(
            texts.QUIZ_QUESTION.format(
                header=self.header(),
                question=escape(self.question["text"]),
                seconds=texts.fa_num(self.round_seconds),
            ),
            self._buttons(),
        )

    def points_for(self, elapsed: float) -> int:
        remaining = max(0.0, 1 - elapsed / self.round_seconds)
        return self.base_points + int(self.speed_bonus * remaining)

    async def on_callback(self, cb: IncomingCallback) -> None:
        if cb.player is None:
            await cb.reply(texts.NOT_A_PLAYER, alert=True)
            return
        parts = cb.data.split(":")
        if len(parts) != 3 or parts[0] != "a" or not parts[2].isdigit():
            return
        if not self.round_open or parts[1] != str(self.round_no):
            await cb.reply(texts.QUIZ_CLOSED)
            return
        uid = cb.player.user_id
        if uid in self.answers:
            await cb.reply(texts.QUIZ_ALREADY)
            return
        choice = int(parts[2])
        self.answers[uid] = choice
        if choice == self.question["correct_index"]:
            self.correct.append(uid)
            self.add_score(uid, self.points_for(self.ctx.now() - self.round_started_at))
        await cb.reply(texts.QUIZ_SAVED)
        if len(self.answers) >= len(self.players):
            await self._reveal()
            await self.close_round()

    async def _reveal(self) -> None:
        if self.correct:
            names = "، ".join(self.by_id[uid].name for uid in self.correct)
            winners = texts.QUIZ_WINNERS.format(names=escape(names))
        else:
            winners = texts.QUIZ_NO_WINNER
        answer = self.question["options"][self.question["correct_index"]]
        await self.ctx.edit(
            self.message_id,
            texts.QUIZ_REVEAL.format(
                header=self.header(),
                question=escape(self.question["text"]),
                answer=escape(str(answer)),
                winners=winners,
            ),
            None,
            urgent=True,
        )

    async def on_round_timeout(self) -> None:
        await self._reveal()
