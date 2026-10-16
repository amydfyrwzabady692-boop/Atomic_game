import random

from games.engine.registry import all_games
from games.plugins.quick_math import QuickMathGame, make_problem

from .fakes import FakeContext


def test_registered():
    assert all_games()["quick_math"] is QuickMathGame


def test_problems_get_harder_and_answers_are_correct():
    rng = random.Random(7)
    previous_max = 0
    for level in (1, 3, 5, 7, 9):
        answers = []
        for _ in range(50):
            text, answer = make_problem(rng, level)
            expr = text.replace("×", "*").replace("−", "-")
            assert eval(expr) == answer  # noqa: S307
            answers.append(abs(answer))
        assert max(answers) > previous_max
        previous_max = max(answers) // 2


async def test_first_correct_answer_wins_round():
    ctx = FakeContext(n_players=3, options={"rounds": 2})
    game = QuickMathGame(ctx)
    await game.start()
    assert "راند ۱ از ۲" in ctx.last_text
    answer = game.answer

    await game.on_message(ctx.msg(0, str(answer + 1)))  # غلط
    assert game.scores[1] == 0
    await game.on_message(ctx.msg(1, f" {answer} "))  # درست
    assert game.scores[2] == 10
    await game.on_message(ctx.msg(2, str(answer)))  # دیر رسید
    assert game.scores[3] == 0
    assert "round" not in ctx.timers and "gap" in ctx.timers


async def test_persian_digits_accepted():
    ctx = FakeContext(options={"rounds": 1})
    game = QuickMathGame(ctx)
    await game.start()
    persian = str(game.answer).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    await game.on_message(ctx.msg(0, persian))
    assert game.scores[1] == 10


async def test_timeout_reveals_answer_and_moves_on():
    ctx = FakeContext(options={"rounds": 2})
    game = QuickMathGame(ctx)
    await game.start()
    first_answer = game.answer
    await ctx.fire("round")
    assert "وقت تمام شد" in ctx.last_text
    await game.on_message(ctx.msg(0, str(first_answer)))  # بعد از پایان راند
    assert game.scores[1] == 0
    await ctx.fire("gap")
    assert game.round_no == 2


async def test_full_game_ends_and_ranks_by_score_then_time():
    ctx = FakeContext(n_players=3, options={"rounds": 3})
    game = QuickMathGame(ctx)
    await game.start()
    for winner in (0, 1, 0):
        ctx.clock += 1
        await game.on_message(ctx.msg(winner, str(game.answer)))
        await ctx.fire("gap")
    assert ctx.ended
    standings = {s.user_id: s for s in await game.finish()}
    assert standings[1].score == 20 and standings[2].score == 10 and standings[3].score == 0
    assert standings[3].reached_at is None
    assert standings[2].reached_at < standings[1].reached_at


def test_answers_are_never_negative():
    for seed in range(3000):
        rng = random.Random(seed)
        for level in range(1, 10):
            text, answer = make_problem(rng, level)
            assert answer >= 0, text
            assert eval(text.replace("×", "*").replace("−", "-")) == answer  # noqa: S307


def test_parse_int_accepts_every_minus_form():
    from core.textutils import parse_int

    assert parse_int("-83") == -83
    assert parse_int("−۸۳") == -83
    assert parse_int("۸۳-") == -83
    assert parse_int("۱٬۲۰۰") == 1200
    assert parse_int("8-3") is None and parse_int("--5") is None
