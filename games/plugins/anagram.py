from core import texts
from core.textutils import normalize_fa
from games.engine.base import IncomingMessage
from games.engine.registry import register_game
from games.engine.rounds import RoundGame


def scramble(word: str, rng) -> str:
    letters = list(word)
    for _ in range(20):
        rng.shuffle(letters)
        if "".join(letters) != word:
            break
    return "".join(letters)


@register_game
class AnagramGame(RoundGame):
    key = "anagram"
    title_fa = "حروف درهم"
    emoji = "🔀"
    description_fa = "حروف یک کلمه به‌هم ریخته؛ اولین نفری که کلمه را درست بنویسد امتیاز می‌گیرد."
    rounds = 6
    round_seconds = 30
    points = 10

    async def start(self) -> None:
        self.words = await self.ctx.content.random_words(self.total_rounds, 4, 7)
        await self.next_round()

    def _question(self, hint: str = "") -> str:
        return texts.ANAGRAM_QUESTION.format(header=self.header(), letters="  ".join(self.scrambled), hint=hint)

    async def begin_round(self) -> None:
        self.word = self.words[self.round_no - 1]
        self.scrambled = scramble(self.word, self.ctx.rng)
        self.message_id = await self.ctx.send(self._question())
        self.ctx.set_timer("hint", self.round_seconds / 2, self._hint)

    async def _hint(self) -> None:
        """اگر تا نیمه‌ی وقت جوابی نیامده باشد، حرف اول نمایش داده می‌شود."""
        if self.round_open:
            hint = "\n\n" + texts.HINT_FIRST_LETTER.format(letter=self.word[0])
            await self.ctx.edit(self.message_id, self._question(hint), urgent=True)

    async def _is_correct(self, text: str) -> bool:
        guess = normalize_fa(text, keep_spaces=False)
        if guess == self.word:
            return True
        # کلمه‌ی معتبر دیگری با همین حروف هم قبول است (مثل «مار» و «رام»)
        return sorted(guess) == sorted(self.word) and await self.ctx.content.is_valid_word(guess)

    async def on_message(self, msg: IncomingMessage) -> None:
        if not self.round_open or not await self._is_correct(msg.text):
            return
        self.add_score(msg.player.user_id, self.points)
        await self.ctx.send(
            texts.ROUND_WON.format(name=msg.player.mention, answer=self.word, points=texts.fa_num(self.points))
        )
        await self.close_round()

    async def on_round_timeout(self) -> None:
        await self.ctx.send(texts.ROUND_TIMEOUT.format(answer=self.word))
