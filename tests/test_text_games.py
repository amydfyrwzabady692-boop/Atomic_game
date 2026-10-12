"""تست واحد منطق بازی‌های متنی، بدون تلگرام (با FakeContext)."""

import pytest

from core import texts
from games.catalog import catalog
from games.engine.registry import all_games
from games.plugins.anagram import AnagramGame, scramble
from games.plugins.dice_games import DiceGame
from games.plugins.emoji_guess import EmojiGuessGame
from games.plugins.guess_number import GuessNumberGame
from games.plugins.hangman import HangmanGame
from games.plugins.quiz import QuizGame
from games.plugins.tictactoe import TicTacToeGame, winner_of
from games.plugins.typing_race import TypingRaceGame, accuracy
from games.plugins.word_chain import WordChainGame

from .fakes import FakeContent, FakeContext


def test_all_ten_text_games_registered():
    expected = {
        "anagram",
        "word_chain",
        "hangman",
        "emoji_guess",
        "quiz",
        "quick_math",
        "guess_number",
        "typing_race",
        "dice_games",
        "tictactoe",
    }
    assert expected <= set(all_games())
    for key in expected:
        info = catalog()[key]
        assert info.title_fa and info.description_fa and info.min_players >= 2


# ====================================================================== حروف درهم
async def test_anagram_scramble_changes_word_but_keeps_letters():
    ctx = FakeContext()
    for word in ["کتاب", "باران", "مدرسه"]:
        mixed = scramble(word, ctx.rng)
        assert mixed != word and sorted(mixed) == sorted(word)


async def test_anagram_first_correct_wins_and_hint_at_half_time():
    ctx = FakeContext(options={"rounds": 2}, content=FakeContent(words=["کتاب", "باران"]))
    game = AnagramGame(ctx)
    await game.start()
    assert game.word == "کتاب"
    assert "کتاب" not in ctx.last_text  # خود کلمه لو نمی‌رود
    await ctx.fire("hint")
    assert "با «ک» شروع می‌شود" in ctx.edits[-1]["text"]

    await game.on_message(ctx.msg(1, "كتاب"))  # ک عربی
    assert game.scores[2] == 10
    await game.on_message(ctx.msg(0, "کتاب"))
    assert game.scores[1] == 0
    await ctx.fire("gap")
    assert game.round_no == 2 and game.word == "باران"


async def test_anagram_accepts_other_valid_word_with_same_letters():
    ctx = FakeContext(options={"rounds": 1}, content=FakeContent(words=["مار", "رام"]))
    game = AnagramGame(ctx)
    game.words = ["مار"]
    await game.next_round()
    await game.on_message(ctx.msg(0, "رما"))  # همان حروف ولی کلمه‌ی معتبری نیست
    assert game.scores[1] == 0
    await game.on_message(ctx.msg(0, "رام"))
    assert game.scores[1] == 10


async def test_anagram_timeout_reveals_word():
    ctx = FakeContext(options={"rounds": 1}, content=FakeContent(words=["کتاب"]))
    game = AnagramGame(ctx)
    await game.start()
    await ctx.fire("round")
    assert "کتاب" in ctx.last_text
    await ctx.fire("gap")
    assert ctx.ended


# ====================================================================== زنجیره‌ی کلمات
CHAIN_WORDS = ["کتاب", "باران", "نان", "نمک", "کلاه", "هوا", "اردک", "کبوتر", "رود", "دریا", "برف"]


async def start_chain(n_players=3):
    ctx = FakeContext(n_players=n_players, content=FakeContent(words=CHAIN_WORDS))
    game = WordChainGame(ctx)
    await game.start()
    return ctx, game


def index_of(ctx, player):
    return ctx.players.index(player)


async def test_chain_valid_word_passes_turn_and_sets_next_letter():
    ctx, game = await start_chain()
    first_player = game.current
    game.letter = "ب"
    await game.on_message(ctx.msg(index_of(ctx, first_player), "باران"))
    assert game.letter == "ن"
    assert game.current != first_player
    assert "باران" in ctx.last_text
    assert game.turn_seconds == game.start_seconds - 1


async def test_chain_rejects_wrong_letter_duplicate_invalid_and_other_players():
    ctx, game = await start_chain()
    current = index_of(ctx, game.current)
    other = (current + 1) % 3
    game.letter = "ب"
    game.used.add("برف")
    sent_before = len(ctx.sent)

    await game.on_message(ctx.msg(other, "باران"))  # نوبتش نیست
    await game.on_message(ctx.msg(current, "نان"))  # حرف غلط
    await game.on_message(ctx.msg(current, "برف"))  # تکراری
    await game.on_message(ctx.msg(current, "بلبلک"))  # خارج از لیست
    await game.on_message(ctx.msg(current, "نمک"))  # هشدار تکراری دوباره فرستاده نمی‌شود

    assert len(ctx.sent) == sent_before
    assert len(ctx.flashes) == 3
    assert index_of(ctx, game.current) == current


async def test_chain_timeout_eliminates_and_last_survivor_wins():
    ctx, game = await start_chain()
    first_out = game.current
    await ctx.fire("turn")
    assert first_out not in game.alive and "حذف شد" in ctx.last_text
    second_out = game.current
    await ctx.fire("turn")
    assert ctx.ended
    winner = game.alive[0]
    standings = {s.user_id: s.score for s in await game.finish()}
    assert standings[first_out.user_id] < standings[second_out.user_id] < standings[winner.user_id]


async def test_chain_picks_new_letter_when_no_words_left():
    ctx = FakeContext(n_players=2, content=FakeContent(words=["کتاب", "برف", "نان"]))
    game = WordChainGame(ctx)
    await game.start()
    game.letter = "ب"
    game.used = {"کتاب"}
    await game.on_message(ctx.msg(index_of(ctx, game.current), "برف"))
    # با «ف» کلمه‌ای نیست؛ حرف دیگری انتخاب می‌شود که کلمه داشته باشد
    assert game.letter == "ن"
    assert "حرف جدید" in ctx.last_text


async def test_chain_turn_timer_shrinks_to_minimum():
    words = ["اب"] + [f"ب{chr(0x0627 + i)}ب" for i in range(1, 30)]
    ctx = FakeContext(n_players=2, content=FakeContent(words=words))
    game = WordChainGame(ctx)
    await game.start()
    for word in words[1:20]:
        game.letter = "ب"
        await game.on_message(ctx.msg(index_of(ctx, game.current), word))
    assert game.turn_seconds == game.min_seconds


# ====================================================================== حدس کلمه
async def start_hangman(word="باران", n_players=2):
    ctx = FakeContext(n_players=n_players, options={"rounds": 1}, content=FakeContent(words=[word]))
    game = HangmanGame(ctx)
    await game.start()
    return ctx, game


async def test_hangman_pattern_and_letter_points():
    ctx, game = await start_hangman()
    assert game.pattern() == "_ _ _ _ _"
    await game.on_message(ctx.msg(0, "ا"))
    assert game.pattern() == "_ ا _ ا _"
    assert game.scores[1] == 2
    await game.on_message(ctx.msg(1, "ا"))  # تکراری: نه امتیاز نه جریمه
    assert game.scores[2] == 0 and game.lives == 6


async def test_hangman_wrong_guesses_cost_shared_lives_until_dead():
    ctx, game = await start_hangman()
    for i, letter in enumerate("پتثجچح"):
        await game.on_message(ctx.msg(i % 2, letter))
    assert game.lives == 0 and not game.round_open
    assert "جان گروه تمام شد" in ctx.last_text and "باران" in ctx.last_text


async def test_hangman_whole_word_guess_scores_high_and_wrong_word_costs_life():
    ctx, game = await start_hangman()
    await game.on_message(ctx.msg(0, "سلام خوبی"))  # گپ معمولی، طول متفاوت
    assert game.lives == 6
    await game.on_message(ctx.msg(0, "بازار"))  # هم‌طول ولی غلط
    assert game.lives == 5
    await game.on_message(ctx.msg(1, "باران"))
    assert game.scores[2] == 10 and not game.round_open


async def test_hangman_completing_by_letters_closes_round():
    ctx, game = await start_hangman("نان")
    await game.on_message(ctx.msg(0, "ن"))
    assert game.round_open
    await game.on_message(ctx.msg(1, "ا"))
    assert not game.round_open
    assert game.scores == {1: 2, 2: 2}


# ====================================================================== حدس با ایموجی
async def test_emoji_accepts_alternative_answers():
    ctx = FakeContext(options={"rounds": 2})
    game = EmojiGuessGame(ctx)
    await game.start()
    assert "🦁👑" in ctx.last_text
    await game.on_message(ctx.msg(0, "شیر"))
    assert game.scores[1] == 0
    await game.on_message(ctx.msg(0, "Lion King"))
    assert game.scores[1] == 10
    await ctx.fire("gap")
    await game.on_message(ctx.msg(1, "مرد‌عنکبوتی"))  # با نیم‌فاصله
    assert game.scores[2] == 10


async def test_emoji_hint_and_timeout():
    ctx = FakeContext(options={"rounds": 1})
    game = EmojiGuessGame(ctx)
    await game.start()
    await ctx.fire("hint")
    assert "با «ش» شروع می‌شود" in ctx.edits[-1]["text"]
    await ctx.fire("round")
    assert "شیر شاه" in ctx.last_text


# ====================================================================== کوییز
async def start_quiz(n_players=3, rounds=2):
    questions = [{"text": "پایتخت ایران؟", "options": ["تهران", "شیراز", "تبریز", "یزد"], "correct_index": 0}]
    ctx = FakeContext(
        n_players=n_players,
        options={"rounds": rounds, "variant": "general"},
        content=FakeContent(questions=questions),
    )
    game = QuizGame(ctx)
    await game.start()
    return ctx, game


async def test_quiz_uses_inline_buttons_and_one_answer_per_player():
    ctx, game = await start_quiz()
    buttons = ctx.sent[-1]["buttons"]
    assert [text for row in buttons for text, _ in row] == ["تهران", "شیراز", "تبریز", "یزد"]

    wrong = ctx.cb(0, "a:1:1")
    await game.on_callback(wrong)
    assert game.scores[1] == 0
    retry = ctx.cb(0, "a:1:0")  # تلاش دوباره قبول نیست
    await game.on_callback(retry)
    assert game.scores[1] == 0
    assert retry.answers[-1][0] == texts.QUIZ_ALREADY


async def test_quiz_faster_answer_scores_more():
    ctx, game = await start_quiz()
    ctx.clock += 1
    await game.on_callback(ctx.cb(0, "a:1:0"))
    ctx.clock += 9
    await game.on_callback(ctx.cb(1, "a:1:0"))
    assert game.scores[1] > game.scores[2] >= 10


async def test_quiz_round_closes_when_everyone_answered_and_reveals():
    ctx, game = await start_quiz()
    for i in range(3):
        await game.on_callback(ctx.cb(i, "a:1:0" if i == 0 else "a:1:2"))
    assert not game.round_open
    reveal = ctx.edits[-1]
    assert "جواب: <b>تهران</b>" in reveal["text"] and reveal["buttons"] is None
    assert "بازیکن1" in reveal["text"]


async def test_quiz_rejects_outsiders_and_stale_buttons():
    ctx, game = await start_quiz()
    outsider = ctx.cb(None, "a:1:0")
    await game.on_callback(outsider)
    assert outsider.answers[-1] == ("تو عضو این مسابقه نیستی.", True)
    await ctx.fire("round")
    assert "هیچ‌کس درست نگفت" in ctx.edits[-1]["text"]
    stale = ctx.cb(0, "a:1:0")
    await game.on_callback(stale)
    assert game.scores[1] == 0 and stale.answers[-1][0] == texts.QUIZ_CLOSED


def test_quiz_has_freefire_category():
    assert "freefire" in QuizGame.variants and "فری فایر" in QuizGame.variants["freefire"]


# ====================================================================== حدس عدد
async def test_guess_number_feedback_narrows_range_and_correct_guess_wins():
    ctx = FakeContext(options={"rounds": 1})
    game = GuessNumberGame(ctx)
    await game.start()
    target = game.target
    assert 1 <= target <= 1000

    low_guess = max(1, target - 5) if target > 1 else None
    if low_guess and low_guess != target:
        await game.on_message(ctx.msg(0, str(low_guess)))
        assert "عدد بزرگ‌تر است" in ctx.edits[-1]["text"] and game.low == low_guess + 1
    high_guess = min(1000, target + 5)
    if high_guess != target:
        await game.on_message(ctx.msg(1, str(high_guess)))
        assert "عدد کوچک‌تر است" in ctx.edits[-1]["text"] and game.high == high_guess - 1

    await game.on_message(ctx.msg(0, "سلام"))
    await game.on_message(ctx.msg(0, "5000"))  # خارج از بازه
    assert game.round_open
    await game.on_message(ctx.msg(2, str(target)))
    assert game.scores[3] == 10 and not game.round_open


# ====================================================================== مسابقه‌ی تایپ
def test_typing_accuracy_metric():
    assert accuracy("زندگی زیباست", "زندگی زیباست") == 1.0
    assert accuracy("زندگي  زيباست", "زندگی زیباست") == 1.0  # نرمال‌سازی
    assert 0.5 < accuracy("زندگی زیباس", "زندگی زیباست") < 1.0


async def test_typing_sends_image_not_text_and_scores_accuracy_and_speed():
    sentence = "امروز هوا خیلی خوب است"
    ctx = FakeContext(n_players=3, options={"rounds": 1}, content=FakeContent(sentences=[sentence]))
    game = TypingRaceGame(ctx)
    await game.start()
    photo = ctx.sent[-1]
    assert photo["photo"][:8] == b"\x89PNG\r\n\x1a\n"
    assert sentence not in photo["text"]  # جمله فقط داخل تصویر است

    await game.on_message(ctx.msg(0, "سلام"))  # خیلی کوتاه: نادیده
    assert 1 not in game.submissions
    ctx.clock += 5
    await game.on_message(ctx.msg(0, sentence))  # کامل و اول: ۱۰ + ۵
    await game.on_message(ctx.msg(0, sentence))  # فقط یک ارسال
    ctx.clock += 2
    await game.on_message(ctx.msg(1, sentence))  # کامل و دوم: ۱۰ + ۳
    await game.on_message(ctx.msg(2, "امروز هوا خیلی خوب"))  # ناقص
    assert game.scores[1] == 15 and game.scores[2] == 13
    assert 0 < game.scores[3] < 10
    assert not game.round_open
    assert "نتیجه‌ی راند" in ctx.last_text


async def test_typing_garbage_gets_zero():
    sentence = "امروز هوا خیلی خوب است"
    ctx = FakeContext(n_players=2, options={"rounds": 1}, content=FakeContent(sentences=[sentence]))
    game = TypingRaceGame(ctx)
    await game.start()
    await game.on_message(ctx.msg(0, "ققققق ققققق ققققق ققققق"))
    assert game.scores[1] == 0 and 1 in game.submissions


# ====================================================================== بازی‌های دایس
async def test_dice_only_bot_throws_on_current_players_button():
    ctx = FakeContext(n_players=2, options={"rounds": 2, "variant": "dice"}, dice=[6, 2, 5, 1])
    game = DiceGame(ctx)
    await game.start()
    first, second = game.order
    assert ctx.sent[-1]["buttons"][0][0][1] == "t:0"

    wrong = ctx.cb(ctx.players.index(second), "t:0")
    await game.on_callback(wrong)
    assert wrong.answers[-1][0] == "نوبت تو نیست!" and game.scores[second.user_id] == 0

    await game.on_callback(ctx.cb(ctx.players.index(first), "t:0"))
    assert ctx.sent[-1]["dice"] == "🎲"
    assert game.scores[first.user_id] == 6
    # کلیک دوباره روی همان دکمه بی‌اثر است
    await game.on_callback(ctx.cb(ctx.players.index(first), "t:0"))
    assert game.scores[first.user_id] == 6

    await ctx.fire("settle")
    await game.on_callback(ctx.cb(ctx.players.index(second), "t:1"))
    await ctx.fire("settle")
    await game.on_callback(ctx.cb(ctx.players.index(first), "t:2"))
    await ctx.fire("settle")
    await ctx.fire("turn")  # مهلت بازیکن دوم تمام شد: ربات خودش پرتاب می‌کند
    await ctx.fire("settle")
    assert ctx.ended
    assert game.scores == {first.user_id: 11, second.user_id: 3}


async def test_dice_ignores_messages_entirely():
    ctx = FakeContext(n_players=2, options={"variant": "dice"})
    game = DiceGame(ctx)
    await game.start()
    await game.on_message(ctx.msg(0, "🎲"))
    assert sum(game.scores.values()) == 0


@pytest.mark.parametrize(
    ("variant", "emoji", "value", "points"),
    [("basket", "🏀", 5, 1), ("basket", "🏀", 3, 0), ("football", "⚽", 3, 1), ("football", "⚽", 2, 0), ("bowling", "🎳", 6, 6), ("darts", "🎯", 4, 4)],
)
async def test_dice_variants_scoring(variant, emoji, value, points):
    ctx = FakeContext(n_players=2, options={"rounds": 1, "variant": variant}, dice=[value])
    game = DiceGame(ctx)
    await game.start()
    first = game.order[0]
    await game.on_callback(ctx.cb(ctx.players.index(first), "t:0"))
    assert ctx.sent[-1]["dice"] == emoji
    assert game.scores[first.user_id] == points


# ====================================================================== دوز
def test_xo_winner_detection():
    assert winner_of(["X", "X", "X", "", "", "", "", "", ""]) == "X"
    assert winner_of(["O", "X", "", "X", "O", "", "", "", "O"]) == "O"
    assert winner_of(["X", "O", "X", "X", "O", "O", "O", "X", "X"]) is None


def test_xo_winner_detection_on_a_four_by_four_board():
    empty = [""] * 16

    def board(mark, cells):
        filled = list(empty)
        for cell in cells:
            filled[cell] = mark
        return filled

    assert winner_of(board("X", [4, 5, 6, 7])) == "X"  # ردیف
    assert winner_of(board("O", [2, 6, 10, 14])) == "O"  # ستون
    assert winner_of(board("X", [0, 5, 10, 15])) == "X"  # قطر اصلی
    assert winner_of(board("O", [3, 6, 9, 12])) == "O"  # قطر فرعی
    assert winner_of(board("X", [0, 1, 2])) is None  # سه‌تایی در صفحه‌ی ۴×۴ کافی نیست
    assert winner_of(board("X", [0, 1, 2, 4])) is None
    assert winner_of(empty) is None


async def test_xo_four_by_four_needs_four_in_a_line():
    ctx, game, x, o = await start_xo("4")
    first = ctx.sent[-1]
    assert len(first["buttons"]) == 4 and all(len(row) == 4 for row in first["buttons"])
    assert "دوز ۴×۴" in first["text"] and "۴ علامت" in first["text"]
    # سه علامت پشت‌سرهم هنوز برد نیست
    for player, cell in [(x, 0), (o, 4), (x, 1), (o, 5), (x, 2), (o, 6)]:
        await game.on_callback(ctx.cb(player, f"m:{cell}"))
    assert not ctx.ended and "علامت را در یک ردیف" not in ctx.edits[-1]["text"]
    outside = ctx.cb(x, "m:16")
    await game.on_callback(outside)
    assert not ctx.ended and outside.answers == []
    await game.on_callback(ctx.cb(x, "m:3"))
    assert ctx.ended and game.scores[game.x.user_id] == 1 and "برد" in ctx.edits[-1]["text"]
    assert len(ctx.edits[-1]["buttons"]) == 4


async def test_xo_four_by_four_draw_and_default_size():
    ctx, game, x, o = await start_xo("4")
    # چیدمانی بدون هیچ خط کامل:  X X O O / O O X X / X X O O / O O X X
    x_cells, o_cells = [0, 1, 6, 7, 8, 9, 14, 15], [2, 3, 4, 5, 10, 11, 12, 13]
    for a, b in zip(x_cells, o_cells, strict=True):
        await game.on_callback(ctx.cb(x, f"m:{a}"))
        await game.on_callback(ctx.cb(o, f"m:{b}"))
    assert ctx.ended and "مساوی" in ctx.edits[-1]["text"]
    assert {s.score for s in await game.finish()} == {0}

    ctx, game, _, _ = await start_xo("nonsense")  # گزینه‌ی ناشناخته: همان ۳×۳
    assert game.size == 3 and "دوز ۳×۳" in ctx.sent[-1]["text"]


async def start_xo(variant=None):
    ctx = FakeContext(n_players=2, options={"variant": variant} if variant else None)
    game = TicTacToeGame(ctx)
    await game.start()
    return ctx, game, ctx.players.index(game.x), ctx.players.index(game.o)


async def test_xo_turns_and_win():
    ctx, game, x, o = await start_xo()
    assert len(ctx.sent[-1]["buttons"]) == 3 and len(ctx.sent[-1]["buttons"][0]) == 3

    not_turn = ctx.cb(o, "m:0")
    await game.on_callback(not_turn)
    assert not_turn.answers[-1][0] == "نوبت تو نیست!" and game.board[0] == ""

    for player, cell in [(x, 0), (o, 3), (x, 1), (o, 4)]:
        await game.on_callback(ctx.cb(player, f"m:{cell}"))
    taken = ctx.cb(x, "m:3")
    await game.on_callback(taken)
    assert taken.answers[-1][0] == texts.XO_TAKEN
    await game.on_callback(ctx.cb(x, "m:2"))
    assert ctx.ended
    assert game.scores[game.x.user_id] == 1 and game.scores[game.o.user_id] == 0
    assert "برد" in ctx.edits[-1]["text"]


async def test_xo_draw_is_a_tie():
    ctx, game, x, o = await start_xo()
    for player, cell in [(x, 0), (o, 1), (x, 2), (o, 4), (x, 3), (o, 5), (x, 7), (o, 6), (x, 8)]:
        await game.on_callback(ctx.cb(player, f"m:{cell}"))
    assert ctx.ended and "مساوی" in ctx.edits[-1]["text"]
    standings = await game.finish()
    assert {s.score for s in standings} == {0}
    assert all(s.reached_at is None for s in standings)


async def test_xo_move_timeout_loses():
    ctx, game, x, o = await start_xo()
    await game.on_callback(ctx.cb(x, "m:4"))
    await ctx.fire("move")  # نوبت O بود و وقتش تمام شد
    assert ctx.ended
    assert game.scores[game.x.user_id] == 1
    assert "وقت" in ctx.edits[-1]["text"]
