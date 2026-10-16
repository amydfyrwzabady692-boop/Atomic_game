"""دکمه‌های رنگی، قوانین بازی‌ها، تاریخ شمسی و پردازش هم‌زمان به‌روزرسانی‌ها."""

import asyncio
import re
from datetime import datetime
from types import SimpleNamespace

import pytest
from telegram import InlineKeyboardMarkup

from bot import render, ui
from bot.concurrency import PerChatUpdateProcessor
from bot.tg import EditQueue
from core import texts
from core.textutils import fa_date, to_jalali
from games.catalog import defaults
from games.engine.base import DANGER, PRIMARY, SUCCESS, BaseGame, Button, format_rules
from games.plugins.chess import ChessGame
from games.plugins.dice_games import DiceGame
from games.plugins.quick_math import QuickMathGame
from games.plugins.quiz import QuizGame
from games.plugins.tictactoe import TicTacToeGame

from .fakes import FakeContent, FakeContext
from .test_chess import sq

ALL_GAMES = sorted(defaults())


# ------------------------------------------------------------------ دکمه‌ی رنگی
def test_button_sends_the_style_field_to_telegram():
    plain = ui.button("ساده", "a")
    green = ui.button("سبز", "b", style=ui.SUCCESS)
    link = ui.button("لینک", url="https://t.me/x", style=ui.PRIMARY)
    assert "style" not in plain.to_dict()
    assert green.to_dict() == {"text": "سبز", "callback_data": "b", "style": "success"}
    assert link.to_dict()["style"] == "primary" and ui.style_of(link) == "primary"
    # رنگ ناشناخته فرستاده نمی‌شود تا تلگرام پیام را رد نکند
    assert "style" not in ui.button("؟", "c", style="rainbow").to_dict()
    markup = InlineKeyboardMarkup([[green]]).to_dict()
    assert markup["inline_keyboard"][0][0]["style"] == "success"


def test_button_styles_can_be_switched_off(settings):
    settings.BUTTON_STYLES = False
    assert "style" not in ui.button("سبز", "b", style=ui.SUCCESS).to_dict()
    assert "style" not in str(render.lobby_keyboard(1, "bot", "chess").to_dict())


def test_game_button_behaves_like_a_text_data_pair():
    cell = Button("متن", "data", DANGER)
    text, data = cell
    assert (text, data, cell[1], cell.style, len(cell)) == ("متن", "data", "data", DANGER, 2)
    assert Button("متن", "data").style == "" and cell == ("متن", "data")


async def test_text_games_colour_their_buttons():
    ctx = FakeContext(n_players=2)
    xo = TicTacToeGame(ctx)
    await xo.start()
    x = ctx.players.index(xo.x)
    await xo.on_callback(ctx.cb(x, "m:4"))
    board = [cell for row in ctx.edits[-1]["buttons"] for cell in row]
    assert board[4].style == DANGER and board[0].style == ""
    await xo.on_callback(ctx.cb(1 - x, "m:0"))
    board = [cell for row in ctx.edits[-1]["buttons"] for cell in row]
    assert board[0].style == PRIMARY

    ctx = FakeContext(n_players=2, content=FakeContent())
    quiz = QuizGame(ctx)
    await quiz.start()
    assert {cell.style for row in ctx.sent[-1]["buttons"] for cell in row} == {PRIMARY}

    ctx = FakeContext(n_players=2)
    dice = DiceGame(ctx)
    await dice.start()
    assert ctx.sent[-1]["buttons"][0][0].style == SUCCESS


async def test_chess_keyboard_highlights_selection_moves_and_captures():
    ctx = FakeContext(n_players=2)
    game = ChessGame(ctx)
    await game.start()
    white = ctx.players.index(game.white)
    first = ctx.sent[-1]["buttons"]
    assert [cell.style for cell in first[8]] == [DANGER, PRIMARY]  # تسلیم قرمز، مساوی آبی
    assert {cell.style for row in first[:8] for cell in row} == {""}

    await game.on_callback(ctx.cb(white, f"q:{sq('e2')}"))
    grid = {cell[1]: cell for row in ctx.edits[-1]["buttons"][:8] for cell in row}
    assert grid[f"q:{sq('e2')}"].style == PRIMARY
    assert grid[f"q:{sq('e4')}"].style == SUCCESS and grid[f"q:{sq('e3')}"].style == SUCCESS
    assert grid[f"q:{sq('a1')}"].style == ""


async def test_dice_falls_back_to_a_fair_roll_when_telegram_sends_nothing():
    ctx = FakeContext(n_players=2, options={"variant": "dice", "rounds": 1}, dice=[0, 0])
    game = DiceGame(ctx)
    await game.start()
    first = game.current
    await game.on_callback(ctx.cb(ctx.players.index(first), "t:0"))
    assert 1 <= game.scores[first.user_id] <= 6


# ------------------------------------------------------------------ قوانین
@pytest.mark.parametrize("key", ALL_GAMES)
def test_every_game_has_three_short_clear_rules(key):
    info = defaults()[key]
    assert len(info.rules) == 3
    for line in info.rules:
        assert line.strip() == line and line.endswith(".") and "{" not in line and "}" not in line
        assert not re.search(r"[0-9]", line), "عددها باید فارسی باشند"
    alert = render.rules_alert(info)
    assert len(alert.encode("utf-16-le")) // 2 <= render.ALERT_CHARS and not alert.endswith("…")
    full = render.rules_text(info)
    assert info.title_fa in full and all(line in full for line in info.rules)
    assert len(full) < 1000


def test_rule_numbers_come_from_the_game_constants():
    class Faster(QuickMathGame):
        points = 25
        rounds = 3

    assert "۲۵ امتیاز" in Faster.rules()[1] and "۳ راند" in Faster.rules()[2]
    assert "۱۰ امتیاز" in QuickMathGame.rules()[1]
    assert format_rules(SimpleNamespace(size=1500, label="تند"), ["{size} واحد {label}"]) == ("۱٬۵۰۰ واحد تند",)
    assert BaseGame.rules() == ()


def test_rules_text_mentions_player_counts_and_falls_back_to_the_description():
    games = defaults()
    assert "۲ بازیکن" in render.rules_text(games["chess"])
    assert "۲ تا ۲۰ بازیکن" in render.rules_text(games["quiz"])
    bare = SimpleNamespace(
        rules=(), style="نوبتی.", description_fa="توضیح کوتاه.", emoji="🎮", title_fa="آزمایشی", min_players=2, max_players=4, is_arcade=False
    )
    assert "توضیح کوتاه." in render.rules_text(bare) and render.rules_alert(bare) == "• توضیح کوتاه."


def test_general_texts_keep_the_virtual_coin_rule():
    for text in (texts.START_NEW, texts.HELP_PRIVATE, texts.RULES):
        assert texts.COINS_NOTE in text
    assert "مجازی" in texts.COINS_NOTE and "ممکن نیست" in texts.COINS_NOTE


def test_texts_use_one_written_tone():
    """فعل‌های محاوره‌ای («می‌شه»، «تموم»، «توی») نباید به متن‌ها برگردند."""
    banned = ("می‌شه", "تموم", "توی ", " رو ", "اومد", "می‌تونی", "می‌تونن", "نیومد", " یه ", "کوچیک", "هستن.", "بنداز")
    for name, value in vars(texts).items():
        if name.isupper() and isinstance(value, str):
            for word in banned:
                assert word not in value, f"{name}: {word}"


# ------------------------------------------------------------------ فهرست نام‌ها
def test_names_line_shortens_long_names_and_caps_the_list():
    names = [f"بازیکن{i}" for i in range(40)]
    line = render.names_line(names)
    assert "بازیکن29" in line and "بازیکن30" not in line and "۱۰ نفر دیگر" in line
    assert render.names_line(["<b>" + "ا" * 60]).startswith("&lt;b&gt;") and len(render.names_line(["ا" * 60])) == 24
    assert render.names_line(["الف", "ب"]) == "الف، ب"


# ------------------------------------------------------------------ تاریخ شمسی
@pytest.mark.parametrize(
    ("gregorian", "jalali"),
    [
        ((2026, 3, 21), (1405, 1, 1)),
        ((2025, 3, 20), (1403, 12, 30)),  # سال کبیسه
        ((2026, 3, 20), (1404, 12, 29)),
        ((2026, 10, 11), (1405, 7, 19)),
        ((2027, 1, 1), (1405, 10, 11)),
        ((2000, 1, 1), (1378, 10, 11)),
    ],
)
def test_jalali_conversion(gregorian, jalali):
    assert to_jalali(*gregorian) == jalali


def test_fa_date_is_short_and_persian():
    assert fa_date(datetime(2026, 10, 11, 14, 5)) == "۱۹ مهر ۱۴:۰۵"


# ------------------------------------------------------------------ پردازش هم‌زمان
def chat_update(chat_id):
    return SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id))


async def test_updates_of_one_chat_keep_their_order_while_chats_run_together():
    processor = PerChatUpdateProcessor(8)
    log = []
    release = asyncio.Event()

    async def slow(name):
        log.append(f"{name}:start")
        await release.wait()
        log.append(f"{name}:end")

    async def quick(name):
        log.append(name)

    tasks = [
        asyncio.create_task(processor.process_update(chat_update(1), slow("a1"))),
        asyncio.create_task(processor.process_update(chat_update(1), quick("a2"))),
        asyncio.create_task(processor.process_update(chat_update(1), quick("a3"))),
        asyncio.create_task(processor.process_update(chat_update(2), quick("b1"))),
    ]
    await asyncio.sleep(0.05)
    # چت ۲ منتظر چت ۱ نمانده است، ولی پیام‌های بعدی چت ۱ پشت پیام اول مانده‌اند
    assert log == ["a1:start", "b1"]
    release.set()
    await asyncio.gather(*tasks)
    assert log == ["a1:start", "b1", "a1:end", "a2", "a3"]
    assert processor._locks == {} and processor._users == {}


async def test_a_failing_update_does_not_block_its_chat():
    processor = PerChatUpdateProcessor(4)
    seen = []

    async def boom():
        raise RuntimeError("x")

    async def fine():
        seen.append("ok")

    with pytest.raises(RuntimeError):
        await processor.process_update(chat_update(5), boom())
    await processor.process_update(chat_update(5), fine())
    await processor.process_update(SimpleNamespace(effective_chat=None), fine())
    assert seen == ["ok", "ok"] and processor._locks == {}


# ------------------------------------------------------------------ صف ویرایش
async def test_edit_queue_close_cancels_waiting_edits():
    calls = []

    async def edit_message_text(**kwargs):
        calls.append(kwargs["text"])

    queue = EditQueue(SimpleNamespace(edit_message_text=edit_message_text), interval=30)
    queue.edit(1, 10, "اول", urgent=True)
    await asyncio.sleep(0.01)
    queue.edit(1, 10, "دوم")  # تا ۳۰ ثانیه‌ی دیگر در صف می‌ماند
    await asyncio.sleep(0.01)
    assert calls == ["اول"] and queue._tasks
    await queue.close()
    assert calls == ["اول"] and not queue._tasks and not queue._pending
