from difflib import SequenceMatcher
from html import escape

from core import texts
from core.textutils import fa_digits, fa_num, normalize_fa
from games.content.typing_image import render_sentence
from games.engine.base import IncomingMessage
from games.engine.registry import register_game
from games.engine.rounds import RoundGame


def accuracy(typed: str, sentence: str) -> float:
    return SequenceMatcher(None, normalize_fa(typed), normalize_fa(sentence)).ratio()


@register_game
class TypingRaceGame(RoundGame):
    key = "typing_race"
    title_fa = "مسابقه‌ی تایپ"
    emoji = "⌨️"
    description_fa = "جمله به‌صورت تصویر فرستاده می‌شود؛ هر چه دقیق‌تر و سریع‌تر تایپ کنی امتیاز بیشتری می‌گیری."
    rounds = 4
    rules_fa = [
        "جمله به‌صورت تصویر می‌آید؛ همان را دقیق تایپ کن و بفرست.",
        "دقت بیشتر امتیاز بیشتر دارد و نفرهای سریع‌تر جایزه‌ی سرعت می‌گیرند.",
        "{rounds} راند، هر راند {round_seconds} ثانیه؛ فقط اولین پیام هر نفر حساب می‌شود.",
    ]
    round_seconds = 45
    gap_seconds = 4
    min_accuracy = 0.8
    speed_bonus = (5, 3, 1)  # برای سه نفر اولِ با دقت بالا
    bonus_accuracy = 0.95

    async def start(self) -> None:
        self.sentences = await self.ctx.content.sentences(self.total_rounds)
        await self.next_round()

    async def begin_round(self) -> None:
        self.sentence = self.sentences[self.round_no - 1]
        self.submissions: dict[int, tuple[float, float, int]] = {}  # uid → (دقت، ثانیه، امتیاز)
        self.fast_finishers = 0
        image = render_sentence(self.sentence, noise_seed=self.ctx.rng.randint(0, 10**6))
        await self.ctx.send_photo(
            image, texts.TYPING_CAPTION.format(header=self.header(), seconds=fa_num(self.round_seconds))
        )
        self.round_started_at = self.ctx.now()

    async def on_message(self, msg: IncomingMessage) -> None:
        uid = msg.player.user_id
        if not self.round_open or uid in self.submissions:
            return
        # پیام‌های خیلی کوتاه گپ معمولی‌اند، نه تلاش برای تایپ جمله
        if len(normalize_fa(msg.text)) < len(normalize_fa(self.sentence)) * 0.5:
            return
        acc = accuracy(msg.text, self.sentence)
        points = 0
        if acc >= self.min_accuracy:
            points = round(acc * 10)
            if acc >= self.bonus_accuracy and self.fast_finishers < len(self.speed_bonus):
                points += self.speed_bonus[self.fast_finishers]
                self.fast_finishers += 1
        self.submissions[uid] = (acc, self.ctx.now() - self.round_started_at, points)
        self.add_score(uid, points)
        if len(self.submissions) >= len(self.players):
            await self._results()
            await self.close_round()

    async def _results(self) -> None:
        if not self.submissions:
            lines = texts.TYPING_NOBODY
        else:
            ordered = sorted(self.submissions.items(), key=lambda item: -item[1][2])
            lines = "\n".join(
                texts.TYPING_LINE.format(
                    name=escape(self.by_id[uid].name),
                    accuracy=fa_num(round(acc * 100)),
                    seconds=fa_digits(f"{seconds:.1f}"),
                    points=fa_num(points),
                )
                for uid, (acc, seconds, points) in ordered
            )
        await self.ctx.send(texts.TYPING_RESULT.format(sentence=escape(self.sentence), lines=lines))

    async def on_round_timeout(self) -> None:
        await self._results()
