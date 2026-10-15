from core import texts
from core.textutils import fa_num, normalize_fa
from games.engine.base import IncomingMessage
from games.engine.registry import register_game
from games.engine.rounds import RoundGame


@register_game
class HangmanGame(RoundGame):
    key = "hangman"
    title_fa = "حدس کلمه"
    emoji = "🪢"
    description_fa = "حرف‌به‌حرف کلمه را پیدا کنید. حدس غلط از جان مشترک گروه کم می‌کند."
    rounds = 4
    rules_fa = [
        "یک حرف بفرست یا کل کلمه را حدس بزن.",
        "حرف درست {letter_points} امتیاز و کلمه‌ی کامل {word_points} امتیاز دارد.",
        "هر حدس غلط یکی از {lives_per_round} جان مشترک گروه را کم می‌کند؛ {rounds} راند.",
    ]
    round_seconds = 90
    lives_per_round = 6
    letter_points = 2
    word_points = 10

    async def start(self) -> None:
        self.words = await self.ctx.content.random_words(self.total_rounds, 4, 8)
        await self.next_round()

    def pattern(self) -> str:
        return " ".join(ch if ch in self.revealed else "_" for ch in self.word)

    def _board(self, note: str = "") -> str:
        return texts.HANGMAN_BOARD.format(
            header=self.header(),
            pattern=self.pattern(),
            lives="❤️" * self.lives + "🖤" * (self.lives_per_round - self.lives),
            wrong="، ".join(self.wrong) or "—",
            note=note,
            letter_points=texts.fa_num(self.letter_points),
            word_points=texts.fa_num(self.word_points),
        )

    async def begin_round(self) -> None:
        self.word = self.words[self.round_no - 1]
        self.revealed: set[str] = set()
        self.wrong: list[str] = []
        self.lives = self.lives_per_round
        self.message_id = await self.ctx.send(self._board())

    async def _miss(self, msg: IncomingMessage, guess: str) -> None:
        self.lives -= 1
        if self.lives <= 0:
            await self.ctx.edit(self.message_id, self._board(), urgent=True)
            await self.ctx.send(texts.HANGMAN_DEAD.format(word=self.word))
            await self.close_round()
            return
        note = texts.HANGMAN_LETTER_BAD.format(name=msg.player.name, guess=guess)
        await self.ctx.edit(self.message_id, self._board(note))

    async def on_message(self, msg: IncomingMessage) -> None:
        if not self.round_open:
            return
        guess = normalize_fa(msg.text, keep_spaces=False)
        uid = msg.player.user_id

        if len(guess) == 1 and guess.isalpha():
            if guess in self.revealed or guess in self.wrong:
                return
            if guess not in self.word:
                self.wrong.append(guess)
                await self._miss(msg, guess)
                return
            self.revealed.add(guess)
            self.add_score(uid, self.letter_points)
            if all(ch in self.revealed for ch in self.word):
                await self.ctx.edit(self.message_id, self._board(), urgent=True)
                await self.ctx.send(texts.HANGMAN_COMPLETED.format(word=self.word))
                await self.close_round()
                return
            note = texts.HANGMAN_LETTER_OK.format(
                name=msg.player.name, letter=guess, points=fa_num(self.letter_points)
            )
            await self.ctx.edit(self.message_id, self._board(note))
            return

        # حدس کل کلمه: فقط پیام هم‌طول با کلمه حدس حساب می‌شود (بقیه گپ معمولی‌اند)
        if len(guess) != len(self.word):
            return
        if guess == self.word:
            self.revealed.update(self.word)
            self.add_score(uid, self.word_points)
            await self.ctx.edit(self.message_id, self._board(), urgent=True)
            await self.ctx.send(
                texts.HANGMAN_SOLVED.format(name=msg.player.mention, word=self.word, points=fa_num(self.word_points))
            )
            await self.close_round()
        else:
            await self._miss(msg, guess)

    async def on_round_timeout(self) -> None:
        await self.ctx.send(texts.ROUND_TIMEOUT.format(answer=self.word))
