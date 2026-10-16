from core import texts
from core.textutils import fa_digits, parse_int
from games.engine.base import IncomingMessage
from games.engine.registry import register_game
from games.engine.rounds import RoundGame


def make_problem(rng, level: int) -> tuple[str, int]:
    """مسئله‌ای با سختی ``level`` (از ۱) می‌سازد: (متن، جواب). جواب هیچ‌وقت منفی نیست؛ تایپ عدد منفی با
    کیبورد فارسی (علامت منفی آخر عدد) گیج‌کننده است و جواب درست را غلط حساب می‌کرد."""
    if level <= 2:
        a, b = rng.randint(5, 40), rng.randint(5, 40)
        return f"{a} + {b}", a + b
    if level <= 4:
        a, b = rng.randint(30, 200), rng.randint(10, 120)
        if rng.random() < 0.5:
            a, b = max(a, b), min(a, b)
            return f"{a} − {b}", a - b
        return f"{a} + {b}", a + b
    if level <= 6:
        a, b = rng.randint(3, 12), rng.randint(3, 15)
        return f"{a} × {b}", a * b
    if level <= 8:
        a, b, c = rng.randint(4, 15), rng.randint(4, 15), rng.randint(10, 99)
        if rng.random() < 0.5 or c > a * b:
            return f"{a} × {b} + {c}", a * b + c
        return f"{a} × {b} − {c}", a * b - c
    a, b, c = rng.randint(11, 25), rng.randint(6, 19), rng.randint(3, 9)
    d = rng.randint(2, 9)
    if c * d > a * b:
        return f"{a} × {b} + {c} × {d}", a * b + c * d
    return f"{a} × {b} − {c} × {d}", a * b - c * d


@register_game
class QuickMathGame(RoundGame):
    key = "quick_math"
    title_fa = "حساب سریع"
    emoji = "🧮"
    description_fa = "اولین نفری که جواب درست را بفرستد امتیاز می‌گیرد. هر راند سخت‌تر می‌شود."
    rounds = 7
    rules_fa = [
        "یک مسئله‌ی حساب فرستاده می‌شود؛ جواب را با عدد بفرست.",
        "فقط اولین جواب درست {points} امتیاز می‌گیرد.",
        "{rounds} راند، هر راند {round_seconds} ثانیه؛ مسئله‌ها کم‌کم سخت‌تر می‌شوند.",
    ]
    round_seconds = 25
    points = 10

    async def begin_round(self) -> None:
        self.problem, self.answer = make_problem(self.ctx.rng, self.round_no)
        await self.ctx.send(texts.MATH_QUESTION.format(header=self.header(), problem=fa_digits(self.problem)))

    async def on_message(self, msg: IncomingMessage) -> None:
        if not self.round_open or parse_int(msg.text) != self.answer:
            return
        self.add_score(msg.player.user_id, self.points)
        await self.ctx.send(
            texts.ROUND_WON.format(
                name=msg.player.mention, answer=fa_digits(self.answer), points=texts.fa_num(self.points)
            )
        )
        await self.close_round()

    async def on_round_timeout(self) -> None:
        await self.ctx.send(texts.ROUND_TIMEOUT.format(answer=fa_digits(self.answer)))
