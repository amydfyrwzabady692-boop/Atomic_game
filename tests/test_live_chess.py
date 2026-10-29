"""شطرنج زنده‌ی مینی‌اپ (قوانین، API و اجرای آن در ربات) و بازی «دوز چهارتایی»."""

import json
import time

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

from arcade import board
from arcade.auth import sign_init_data
from bot.runner import MatchManager
from core.models import TelegramGroup, TelegramUser
from core.redis import reset_clients
from games.catalog import get_info
from games.chess import live
from games.chess.engine import START_FEN, Position
from games.models import Match, MatchStatus
from games.plugins.connect4 import COLUMNS, ConnectFourGame, winning_cells
from wallet.models import TxType
from wallet.services import apply_transaction

from .fake_telegram import FakeApplication
from .fakes import FakeContext
from .test_chess import sq

PNG = b"\x89PNG\r\n\x1a\n"
JPEG = b"\xff\xd8\xff"


# ------------------------------------------------------------------ قوانین (بدون جنگو)
def play(state, moves, now=1000.0):
    for text in moves:
        mover = state[live.position_of(state).turn]
        live.apply_move(state, mover, sq(text[:2]), sq(text[2:4]), text[4:], now)


def test_fen_round_trip():
    assert Position.initial().fen() == START_FEN
    fen = "r3k2r/pp1b1ppp/2n5/2pPp3/8/5N2/PPP2PPP/R3K2R w KQkq c6 0 12"
    assert Position.from_fen(fen).fen() == fen
    assert Position.from_fen("8/8/8/8/8/8/8/K6k b - - 7 40").fen() == "8/8/8/8/8/8/8/K6k b - - 7 40"


def test_moves_are_validated_and_turns_alternate():
    state = live.new_state(1, 2, 1000.0)
    with pytest.raises(live.LiveError, match="not_your_turn"):
        live.apply_move(state, 2, sq("e7"), sq("e5"), "", 1000.0)
    with pytest.raises(live.LiveError, match="illegal_move"):
        live.apply_move(state, 1, sq("e2"), sq("e5"), "", 1000.0)
    with pytest.raises(live.LiveError, match="not_a_player"):
        live.apply_move(state, 3, sq("e2"), sq("e4"), "", 1000.0)
    with pytest.raises(live.LiveError, match="illegal_move"):
        live.apply_move(state, 1, 99, 5, "", 1000.0)
    assert state["version"] == 1 and state["moves"] == []
    live.apply_move(state, 1, sq("e2"), sq("e4"), "", 1005.0)
    assert state["moves"] == ["e2e4"] and state["san"] == ["e4"] and state["last"] == [sq("e2"), sq("e4")]
    # اولین حرکت سیاه هم مهلت جداگانه دارد و از ساعتش کم نمی‌شود
    assert state["deadline"] == 1005.0 + live.FIRST_MOVE_SECONDS and state["version"] == 2

    mine = live.view(state, 2, 1010.0)
    assert mine["you"] == "b" and mine["turn"] == "b" and len(mine["legal"]) == 10 and mine["seconds_left"] == 55
    assert mine["first_move"] and mine["running"] is None and mine["clock"] == {"w": 300_000, "b": 300_000}
    assert (mine["control"], mine["base"], mine["inc"]) == ("blitz5", 300, 3)
    assert sq("e5") in mine["legal"][str(sq("e7"))]
    theirs = live.view(state, 1, 1010.0)
    assert theirs["you"] == "w" and theirs["legal"] == {}  # نوبت او نیست
    assert live.view(state, 77, 1010.0)["you"] is None and len(mine["board"]) == 64


def test_fools_mate_ends_the_game_for_black():
    state = live.new_state(1, 2, 1000.0)
    play(state, ["f2f3", "e7e5", "g2g4", "d8h4"])
    assert state["over"] == {"reason": "checkmate", "side": "b", "winner": 2}
    assert state["deadline"] is None
    with pytest.raises(live.LiveError, match="game_over"):
        live.apply_move(state, 1, sq("a2"), sq("a3"), "", 1000.0)
    assert live.view(state, 1, 1000.0)["legal"] == {}


def test_promotion_piece_can_be_chosen():
    state = live.new_state(1, 2, 0.0)
    state["fen"] = "8/P6k/8/8/8/8/8/K7 w - - 0 1"
    live.apply_move(state, 1, sq("a7"), sq("a8"), "n", 0.0)
    assert live.position_of(state).board[sq("a8")] == "N" and state["moves"] == ["a7a8n"]
    state = live.new_state(1, 2, 0.0)
    state["fen"] = "8/P6k/8/8/8/8/8/K7 w - - 0 1"
    live.apply_move(state, 1, sq("a7"), sq("a8"), "", 0.0)  # پیش‌فرض: وزیر
    assert live.position_of(state).board[sq("a8")] == "Q"
    state = live.new_state(1, 2, 0.0)
    state["fen"] = "8/P6k/8/8/8/8/8/K7 w - - 0 1"
    with pytest.raises(live.LiveError, match="illegal_move"):
        live.apply_move(state, 1, sq("a7"), sq("a8"), "k", 0.0)


def test_timeout_resign_draw_offer_and_repetition():
    state = live.new_state(1, 2, 1000.0)
    assert not live.check_timeout(state, 1000.0 + live.FIRST_MOVE_SECONDS - 1)
    assert live.check_timeout(state, 1000.0 + live.FIRST_MOVE_SECONDS + 1)
    assert state["over"] == {"reason": "timeout", "side": "b", "winner": 2}

    state = live.new_state(1, 2, 1000.0)
    with pytest.raises(live.LiveError, match="game_over"):
        live.apply_move(state, 1, sq("e2"), sq("e4"), "", 2000.0)  # حرکتِ بعد از مهلت قبول نیست
    assert state["over"]["reason"] == "timeout"

    state = live.new_state(1, 2, 1000.0)
    live.resign(state, 1)
    assert state["over"] == {"reason": "resign", "side": "b", "winner": 2}
    with pytest.raises(live.LiveError):
        live.resign(state, 2)

    state = live.new_state(1, 2, 1000.0)
    assert live.offer_draw(state, 1) is False and live.view(state, 2, 1000.0)["draw_offer"] == "opponent"
    assert live.view(state, 1, 1000.0)["draw_offer"] == "you"
    version = state["version"]
    assert live.offer_draw(state, 1) is False and state["version"] == version  # تکرار پیشنهاد اثری ندارد
    play(state, ["e2e4"])
    assert state["draw_offer"] == 1  # حرکت خودِ پیشنهاددهنده آن را پس نمی‌گیرد
    play(state, ["e7e5"])
    assert state["draw_offer"] is None  # حرکت حریف یعنی رد
    live.offer_draw(state, 2)
    assert live.offer_draw(state, 1) is True and state["over"] == {"reason": "agreed", "side": None, "winner": None}

    state = live.new_state(1, 2, 1000.0)
    play(state, ["g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6", "f3g1"])
    assert state["over"] is None
    play(state, ["f6g8"])
    assert state["over"]["reason"] == "repetition" and state["over"]["winner"] is None


def test_chess_clock_runs_like_international_time_controls():
    """۳+۲: اولین حرکت هر طرف مجانی؛ بعد از آن وقت مصرف‌شده کم و ۲ ثانیه افزایش اضافه می‌شود."""
    state = live.new_state(1, 2, 0.0, control="blitz3")
    assert state["clock"] == {"w": 180.0, "b": 180.0} and state["deadline"] == live.FIRST_MOVE_SECONDS
    live.apply_move(state, 1, sq("e2"), sq("e4"), "", 10.0)
    live.apply_move(state, 2, sq("e7"), sq("e5"), "", 20.0)
    assert state["clock"] == {"w": 180.0, "b": 180.0} and state["deadline"] == 200.0  # ساعت سفید از حالا می‌رود
    view = live.view(state, 1, 30.0)
    assert view["running"] == "w" and view["clock"] == {"w": 170_000, "b": 180_000} and not view["first_move"]
    live.apply_move(state, 1, sq("g1"), sq("f3"), "", 50.0)
    assert state["clock"]["w"] == 152.0 and state["deadline"] == 50.0 + 180.0
    assert live.view(state, 2, 60.0)["clock"] == {"w": 152_000, "b": 170_000}
    live.apply_move(state, 2, sq("b8"), sq("c6"), "", 100.0)
    assert state["clock"]["b"] == 132.0 and state["deadline"] == 252.0
    assert state["san"] == ["e4", "e5", "Nf3", "Nc6"]
    assert not live.check_timeout(state, 252.0)
    assert live.check_timeout(state, 252.5)
    assert state["over"] == {"reason": "timeout", "side": "b", "winner": 2} and state["clock"]["w"] == 0.0
    # کلید ناشناخته = پیش‌فرض؛ None = بدون ساعت (تمرین با کامپیوتر)
    assert live.new_state(1, 2, 0.0, control="nonsense")["control"] == live.DEFAULT_CONTROL
    untimed = live.new_state(1, 2, 0.0, control=None)
    assert untimed["deadline"] is None and not live.check_timeout(untimed, 10**9)
    assert live.view(untimed, 1, 10**9)["clock"] is None


def test_flag_fall_against_a_lone_king_is_a_draw():
    """قانون ۶.۹ فیده: اگر حریف فقط شاه دارد و با هیچ حرکتی نمی‌تواند مات کند، پایان وقت مساوی است."""
    state = live.new_state(1, 2, 0.0, control="bullet")
    state["fen"] = "7k/8/8/8/8/8/8/KQ6 w - - 0 1"  # نوبت سفید که وزیر دارد؛ سیاه فقط شاه
    assert live.check_timeout(state, 1000.0)
    assert state["over"] == {"reason": "timeout_draw", "side": None, "winner": None}
    state = live.new_state(1, 2, 0.0, control="bullet")
    state["fen"] = "7k/8/8/8/8/8/8/KN6 b - - 0 1"  # سیاهِ تنها وقتش تمام شد؛ سفید با اسب هنوز (کمکی) مات دارد
    assert live.check_timeout(state, 1000.0) and state["over"]["winner"] == 1


def test_san_notation():
    from games.chess.engine import Move

    start = Position.initial()
    assert start.san(Move(sq("g1"), sq("f3"))) == "Nf3" and start.san(Move(sq("e2"), sq("e4"))) == "e4"
    knights = Position.from_fen("4k3/8/8/8/8/5N2/8/1N2K3 w - - 0 1")
    assert knights.san(Move(sq("b1"), sq("d2"))) == "Nbd2" and knights.san(Move(sq("f3"), sq("d2"))) == "Nfd2"
    rooks = Position.from_fen("4k3/8/8/R7/8/8/8/R3K3 w - - 0 1")
    assert rooks.san(Move(sq("a1"), sq("a3"))) == "R1a3" and rooks.san(Move(sq("a5"), sq("a3"))) == "R5a3"
    castle = Position.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert castle.san(Move(sq("e1"), sq("g1"))) == "O-O" and castle.san(Move(sq("e1"), sq("c1"))) == "O-O-O"
    assert Position.from_fen("8/P6k/8/8/8/8/8/K7 w - - 0 1").san(Move(sq("a7"), sq("a8"), "Q")) == "a8=Q"
    passant = Position.from_fen("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    assert passant.san(Move(sq("e5"), sq("d6"))) == "exd6"
    state = live.new_state(1, 2, 1000.0)
    play(state, ["f2f3", "e7e5", "g2g4", "d8h4"])
    assert state["san"] == ["f3", "e5", "g4", "Qh4#"]
    assert live.new_state(1, 2, 0.0)["san"] == []
    from games.chess.text import notation

    assert notation("Qh4#", 3) == "\u200e۲… ♕h4#" and notation("Nf3", 0) == "\u200e۱. ♘f3"


def test_state_saved_before_the_chess_clock_still_works():
    """بازی‌هایی که با قالب قدیمی (مهلت ثابت هر حرکت) ذخیره شده‌اند بعد از به‌روزرسانی خراب نمی‌شوند."""
    old = {
        "game": "chess", "w": 1, "b": 2, "fen": START_FEN, "moves": [], "last": None,
        "deadline": 1090.0, "move_seconds": 90, "draw_offer": None, "over": None, "version": 1,
    }  # fmt: skip
    play(old, ["e2e4", "e7e5", "g1f3"], now=1050.0)
    assert old["san"] == ["e4", "e5", "Nf3"] and old["control"] == "rapid10" and "move_seconds" not in old
    assert live.view(old, 2, 1060.0)["clock"]["b"] == 590_000
    practice = {
        "game": "chess", "w": 1, "b": 0, "fen": START_FEN, "moves": [], "last": None,
        "deadline": 1000.0 + 10**8, "move_seconds": 10**8, "draw_offer": None, "over": None, "version": 1,
    }  # fmt: skip
    assert live.view(practice, 1, 2000.0)["clock"] is None and practice["deadline"] is None


def test_board_state_uses_the_chosen_time_control():
    assert board.new_state("chess", [1, 2], 0.0, options={"variant": "rapid15"})["base"] == 900
    assert board.new_state("chess", [1, 2], 0.0)["control"] == live.DEFAULT_CONTROL


# ------------------------------------------------------------------ API مینی‌اپ
def init_data(user: TelegramUser) -> str:
    fields = {"auth_date": int(time.time()), "user": {"id": user.tg_id, "first_name": user.first_name}}
    return sign_init_data(fields, settings.BOT_TOKEN)


def post(client, path, user, **body):
    body["initData"] = init_data(user)
    response = client.post(f"/arcade/api/{path}", data=json.dumps(body), content_type="application/json")
    return response.status_code, response.json()


@pytest.fixture
def chess_match(db, group, make_user):
    white, black, watcher = make_user(first_name="سفید"), make_user(first_name="سیاه"), make_user()
    match = Match.objects.create(
        group=group,
        creator=white,
        game_type="chess",
        status=MatchStatus.RUNNING,
        min_players=2,
        max_players=2,
        join_deadline=timezone.now(),
    )
    board.start(match.pk, live.new_state(white.pk, black.pk, time.time()))
    match.refresh_from_db()
    return match, white, black, watcher


def test_board_page_and_piece_images(client, chess_match):
    match, *_ = chess_match
    page = client.get(f"/arcade/board/{match.token}/")
    assert page.status_code == 200 and 'id="board"' in page.content.decode() and "chess.js" in page.content.decode()
    # لینک مستقیم مسابقه (همان آدرس مینی‌اپ) هم صفحه‌ی شطرنج را باز می‌کند
    direct = client.get(f"/arcade/?tgWebAppStartParam={match.token}")
    assert direct.status_code == 200 and 'id="board"' in direct.content.decode()
    assert client.get("/arcade/board/nope/").status_code == 404
    for code in ("wk", "bq", "wp", "bn"):
        response = client.get(f"/arcade/piece/{code}.png")
        assert response.status_code == 200 and response.content[:8] == PNG
        assert "immutable" in response["Cache-Control"]
    assert client.get("/arcade/piece/xx.png").status_code == 404


def test_board_api_plays_a_game_and_only_players_can_move(client, chess_match):
    match, white, black, watcher = chess_match
    status, data = post(client, "board/state", white, match_token=match.token)
    assert status == 200 and data["state"]["you"] == "w" and data["state"]["players"] == {"w": "سفید", "b": "سیاه"}
    assert len(data["state"]["legal"]) == 10 and data["state"]["version"] == 1
    status, same = post(client, "board/state", white, match_token=match.token, version=1)
    assert set(same) == {"ok", "changed", "seconds_left", "left_ms"} and same["changed"] is False
    assert 50 < same["seconds_left"] <= live.FIRST_MOVE_SECONDS and same["left_ms"] // 1000 == same["seconds_left"]

    assert post(client, "board/move", black, match_token=match.token, src=sq("e7"), dst=sq("e5")) == (
        409,
        {"ok": False, "error": "not_your_turn"},
    )
    assert post(client, "board/move", watcher, match_token=match.token, src=sq("e2"), dst=sq("e4"))[1]["error"] == "not_a_player"
    assert post(client, "board/move", white, match_token=match.token, src="12", dst=28)[0] == 400
    assert post(client, "board/move", white, match_token="nope", src=12, dst=28)[0] == 404
    assert post(client, "board/state", watcher, match_token=match.token)[1]["state"]["you"] is None  # تماشاچی

    for user, move in [(white, "f2f3"), (black, "e7e5"), (white, "g2g4"), (black, "d8h4")]:
        status, data = post(client, "board/move", user, match_token=match.token, src=sq(move[:2]), dst=sq(move[2:]))
        assert status == 200, data
    assert data["state"]["over"] == {"reason": "checkmate", "side": "b", "winner": black.pk}
    # حرکت‌ها برای مرور بازی و سطح بازیکن‌ها برای نوار بالا/پایین تخته
    assert data["state"]["uci"] == ["f2f3", "e7e5", "g2g4", "d8h4"] and data["state"]["san"][-1] == "Qh4#"
    assert data["state"]["profiles"] == {"w": {"level": 1, "emoji": "", "title": ""}, "b": {"level": 1, "emoji": "", "title": ""}}
    assert post(client, "board/move", white, match_token=match.token, src=sq("a2"), dst=sq("a3"))[1]["error"] == "game_over"
    assert post(client, "board/action", white, match_token=match.token, action="resign")[1]["error"] == "game_over"
    match.refresh_from_db()
    assert match.state["board"]["moves"] == ["f2f3", "e7e5", "g2g4", "d8h4"]


def test_board_api_actions_and_auth(client, chess_match):
    match, white, black, _ = chess_match
    assert post(client, "board/action", white, match_token=match.token, action="dance")[0] == 400
    status, data = post(client, "board/action", white, match_token=match.token, action="draw")
    assert status == 200 and data["state"]["draw_offer"] == "you" and data["state"]["over"] is None
    status, data = post(client, "board/action", black, match_token=match.token, action="draw")
    assert data["state"]["over"]["reason"] == "agreed"
    bad = client.post("/arcade/api/board/state", data=json.dumps({"initData": "x", "match_token": match.token}), content_type="application/json")
    assert bad.status_code == 401
    # info همان مینی‌اپ آرکید، کلاینت را به صفحه‌ی شطرنج می‌فرستد
    status, info = post(client, "info", white, match_token=match.token)
    assert info == {"ok": True, "mode": "board", "url": f"/arcade/board/{match.token}/"}


def test_tick_closes_an_expired_game(chess_match):
    match, white, black, _ = chess_match
    assert board.tick(match.pk)["over"] is None
    state = board.tick(match.pk, now=match.state["board"]["deadline"] + 1)
    assert state["over"] == {"reason": "timeout", "side": "b", "winner": black.pk}
    assert board.tick(999999) is None


# ------------------------------------------------------------------ اجرای شطرنج زنده در ربات
CHAT_ID = -100901


@pytest.fixture
def _fresh_redis():
    reset_clients()
    yield
    reset_clients()


@sync_to_async
def make_world():
    group = TelegramGroup.objects.create(chat_id=CHAT_ID, title="شطرنج")
    users = [TelegramUser.objects.create(tg_id=8100 + i, first_name=f"شطرنج‌باز{i}", started_bot=True) for i in range(2)]
    for user in users:
        apply_transaction(user, 500, TxType.ADMIN_GRANT, f"chess-test:{user.pk}")
    return group, users


async def start_chess(app):
    group, users = await make_world()
    manager = MatchManager(app)
    active = await manager.create_lobby(group, users[0], get_info("chess"), fee=50, split=[100], join_seconds=60, options={})
    for user in users:
        await manager.join(active, user)
    await app.job_queue.fire("lobby_close")
    return manager, active, users


@pytest.mark.django_db(transaction=True)
async def test_bot_runs_chess_through_the_mini_app_and_pays_the_winner(_fresh_redis):
    app = FakeApplication()
    manager, active, users = await start_chess(app)
    assert active.phase == "running" and active.game is None  # نسخه‌ی داخل گفت‌وگو اجرا نمی‌شود
    opening = app.bot.sent[-1]
    assert opening["photo"][:3] == JPEG and "صفحه‌ی شطرنج باز شود" in opening["text"]
    state = (await sync_to_async(Match.objects.get)(pk=active.match_id)).state
    assert state["board_message_id"] == active.board_message_id and state["board"]["version"] == 1

    by_side = {"w": state["board"]["w"], "b": state["board"]["b"]}
    for side, move in [("w", "f2f3"), ("b", "e7e5"), ("w", "g2g4")]:
        await sync_to_async(board.update)(
            active.match_id, lambda s, side=side, move=move: live.apply_move(s, by_side[side], sq(move[:2]), sq(move[2:]), "", time.time())
        )
    edits_before = len(app.bot.edits)
    await manager.poll_live(active)
    assert len(app.bot.edits) == edits_before + 1 and "آخرین حرکت" in app.bot.edits[-1]["text"]
    await manager.poll_live(active)  # تغییری نبوده: ویرایش تازه‌ای نمی‌شود
    assert len(app.bot.edits) == edits_before + 1

    await sync_to_async(board.update)(
        active.match_id, lambda s: live.apply_move(s, by_side["b"], sq("d8"), sq("h4"), "", time.time())
    )
    await manager.poll_live(active)
    assert active.phase == "done" and not manager.in_chat(CHAT_ID)
    assert "کیش و مات" in app.bot.edits[-1]["text"]
    assert "پایان شطرنج" in app.bot.sent[-1]["text"] and "🥇" in app.bot.sent[-1]["text"]
    match = await sync_to_async(Match.objects.get)(pk=active.match_id)
    assert match.status == MatchStatus.FINISHED
    winner = await sync_to_async(TelegramUser.objects.get)(pk=by_side["b"])
    assert winner.wins == 1


@pytest.mark.django_db(transaction=True)
async def test_live_chess_times_out_and_survives_a_restart(_fresh_redis):
    app = FakeApplication()
    manager, active, users = await start_chess(app)
    # ری‌استارت ربات: بازی از دیتابیس ادامه پیدا می‌کند
    restarted = MatchManager(FakeApplication())
    await restarted.recover()
    resumed = restarted.in_chat(CHAT_ID)[0]
    assert resumed.phase == "running" and resumed.board_message_id == active.board_message_id
    assert len(resumed.players_by_tg) == 2

    def expire(state):
        state["deadline"] = 1.0
        state["version"] += 1

    await sync_to_async(board.update)(active.match_id, expire)
    await restarted.poll_live(resumed)
    assert resumed.phase == "done"
    match = await sync_to_async(Match.objects.get)(pk=active.match_id)
    assert match.status == MatchStatus.FINISHED and match.state["board"]["over"]["reason"] == "timeout"


@pytest.mark.django_db(transaction=True)
async def test_chess_stays_in_chat_when_the_mini_app_is_not_set_up(_fresh_redis, settings):
    settings.MINIAPP_BASE_URL = ""
    app = FakeApplication()
    manager, active, users = await start_chess(app)
    assert active.game is not None and app.bot.sent[-1]["photo"][:3] == JPEG


# ------------------------------------------------------------------ دوز چهارتایی
def test_connect4_line_detection():
    def filled(mark, cells):
        grid = [""] * 42
        for cell in cells:
            grid[cell] = mark
        return grid

    assert sorted(winning_cells(filled("R", [0, 1, 2, 3]), 3)) == [0, 1, 2, 3]  # افقی
    assert sorted(winning_cells(filled("Y", [2, 9, 16, 23]), 9)) == [2, 9, 16, 23]  # عمودی
    assert sorted(winning_cells(filled("R", [0, 8, 16, 24]), 16)) == [0, 8, 16, 24]  # مورب بالا-راست
    assert sorted(winning_cells(filled("R", [3, 9, 15, 21]), 21)) == [3, 9, 15, 21]  # مورب بالا-چپ
    assert winning_cells(filled("R", [0, 1, 2]), 2) == []
    assert winning_cells(filled("R", [5, 6, 7, 8]), 6) == []  # خط از لبه‌ی صفحه رد نمی‌شود


async def start_c4():
    ctx = FakeContext(n_players=2)
    game = ConnectFourGame(ctx)
    await game.start()
    return ctx, game, ctx.players.index(game.red), ctx.players.index(game.yellow)


async def test_connect4_discs_fall_and_four_in_a_row_wins():
    ctx, game, red, yellow = await start_c4()
    first = ctx.sent[-1]
    assert len(first["buttons"]) == 1 and len(first["buttons"][0]) == COLUMNS
    assert first["text"].count("⚪️") == 42 and "چهار مهره" in first["text"]
    wrong = ctx.cb(yellow, "c:0")
    await game.on_callback(wrong)
    assert wrong.answers[-1][0] == "نوبت تو نیست!"

    for player, column in [(red, 0), (yellow, 0), (red, 1), (yellow, 1), (red, 2), (yellow, 2)]:
        await game.on_callback(ctx.cb(player, f"c:{column}"))
    assert game.board[0] == "R" and game.board[COLUMNS] == "Y"  # مهره‌ی دوم روی اولی نشسته
    assert not ctx.ended
    await game.on_callback(ctx.cb(red, "c:3"))
    assert ctx.ended and game.scores[game.red.user_id] == 1
    final = ctx.edits[-1]
    assert "برد" in final["text"] and final["text"].count("🟥") == 4 and final["buttons"] is None


async def test_connect4_full_column_and_timeout():
    ctx, game, red, yellow = await start_c4()
    for index in range(6):
        await game.on_callback(ctx.cb(red if index % 2 == 0 else yellow, "c:6"))
    full = ctx.cb(red, "c:6")
    await game.on_callback(full)
    assert full.answers[-1][0] == "این ستون پر است!" and not ctx.ended
    outside = ctx.cb(red, "c:7")
    await game.on_callback(outside)
    assert outside.answers == []
    await ctx.fire("move")  # وقت قرمز تمام شد
    assert ctx.ended and game.scores[game.yellow.user_id] == 1 and "وقت" in ctx.edits[-1]["text"]


# ------------------------------------------------------------------ دوز و دوز چهارتایی در مینی‌اپ
def test_grid_tictactoe_rules():
    from games import gridlive

    state = gridlive.new_state("tictactoe", 1, 2, 1000.0)
    assert gridlive.view(state, 1, 1000.0)["legal"] == list(range(9)) and gridlive.view(state, 2, 1000.0)["legal"] == []
    assert gridlive.view(state, 1, 1010.5)["left_ms"] == 19_500
    with pytest.raises(live.LiveError, match="not_your_turn"):
        gridlive.apply_move(state, 2, 0, 0, "", 1000.0)
    for user, cell in [(1, 0), (2, 3), (1, 1), (2, 4)]:
        gridlive.apply_move(state, user, cell, 0, "", 1000.0)
    with pytest.raises(live.LiveError, match="illegal_move"):
        gridlive.apply_move(state, 1, 3, 0, "", 1000.0)
    gridlive.apply_move(state, 1, 2, 0, "", 1000.0)
    assert state["over"] == {"reason": "line", "side": "X", "winner": 1} and state["win"] == [0, 1, 2]
    with pytest.raises(live.LiveError, match="game_over"):
        gridlive.apply_move(state, 2, 5, 0, "", 1000.0)

    state = gridlive.new_state("tictactoe", 1, 2, 1000.0)
    for user, cell in [(1, 0), (2, 1), (1, 2), (2, 4), (1, 3), (2, 5), (1, 7), (2, 6), (1, 8)]:
        gridlive.apply_move(state, user, cell, 0, "", 1000.0)
    assert state["over"] == {"reason": "full", "side": None, "winner": None}
    with pytest.raises(live.LiveError, match="bad_action"):
        gridlive.offer_draw(state, 1)


def test_grid_connect4_gravity_timeout_and_resign():
    from games import gridlive

    state = gridlive.new_state("connect4", 1, 2, 1000.0)
    assert gridlive.apply_move(state, 1, 3, 0, "", 1000.0) == 3
    assert gridlive.apply_move(state, 2, 3, 0, "", 1000.0) == 10  # روی مهره‌ی قبلی می‌نشیند
    for user, column in [(1, 0), (2, 6), (1, 1), (2, 6), (1, 2)]:
        gridlive.apply_move(state, user, column, 0, "", 1000.0)
    assert state["over"]["winner"] == 1 and state["win"] == [0, 1, 2, 3]
    with pytest.raises(live.LiveError, match="illegal_move"):
        gridlive.apply_move(gridlive.new_state("connect4", 1, 2, 0.0), 1, 7, 0, "", 0.0)

    state = gridlive.new_state("connect4", 1, 2, 1000.0)
    assert gridlive.check_timeout(state, 1031.0) and state["over"] == {"reason": "timeout", "side": "Y", "winner": 2}
    state = gridlive.new_state("connect4", 1, 2, 1000.0)
    gridlive.resign(state, 2)
    assert state["over"]["winner"] == 1


def test_grid_page_and_api(client, group, make_user):
    red, yellow = make_user(first_name="قرمز"), make_user(first_name="زرد")
    match = Match.objects.create(
        group=group,
        creator=red,
        game_type="connect4",
        status=MatchStatus.RUNNING,
        min_players=2,
        max_players=2,
        join_deadline=timezone.now(),
    )
    board.start(match.pk, board.new_state("connect4", [red.pk, yellow.pk], time.time()))
    page = client.get(f"/arcade/board/{match.token}/").content.decode()
    assert 'id="grid"' in page and "grid.js" in page
    status, data = post(client, "board/state", red, match_token=match.token)
    assert data["state"]["game"] == "connect4" and data["state"]["players"] == {"R": "قرمز", "Y": "زرد"}
    assert data["state"]["cols"] == 7 and data["state"]["legal"] == list(range(7))
    status, data = post(client, "board/move", red, match_token=match.token, src=3)
    assert status == 200 and data["state"]["cells"][3] == "R" and data["state"]["turn"] == "Y"
    assert post(client, "board/move", red, match_token=match.token, src=3)[1]["error"] == "not_your_turn"
    assert post(client, "board/action", yellow, match_token=match.token, action="draw")[0] == 409
    status, data = post(client, "board/action", yellow, match_token=match.token, action="resign")
    assert data["state"]["over"]["winner"] == red.pk


@pytest.mark.django_db(transaction=True)
async def test_bot_runs_tictactoe_through_the_mini_app(_fresh_redis):
    from games import gridlive

    app = FakeApplication()
    group, users = await make_world()
    manager = MatchManager(app)
    active = await manager.create_lobby(
        group, users[0], get_info("tictactoe"), fee=50, split=[100], join_seconds=60, options={}
    )
    for user in users:
        await manager.join(active, user)
    await app.job_queue.fire("lobby_close")
    opening = app.bot.sent[-1]
    assert active.game is None and "photo" not in opening and "دوز ۳×۳" in opening["text"]
    assert opening["text"].count("▫️") == 9 and "صفحه‌ی بازی باز شود" in opening["text"]
    state = (await sync_to_async(Match.objects.get)(pk=active.match_id)).state["board"]
    x, o = state["sides"]["X"], state["sides"]["O"]
    for user, cell in [(x, 0), (o, 3), (x, 1), (o, 4), (x, 2)]:
        await sync_to_async(board.update)(
            active.match_id, lambda s, user=user, cell=cell: gridlive.apply_move(s, user, cell, 0, "", time.time())
        )
    await manager.poll_live(active)
    assert active.phase == "done" and "برد" in app.bot.edits[-1]["text"] and "❎❎❎" in app.bot.edits[-1]["text"]
    assert "پایان دوز" in app.bot.sent[-1]["text"]
    winner = await sync_to_async(TelegramUser.objects.get)(pk=x)
    assert winner.wins == 1


# ------------------------------------------------------------------ شطرنج با کامپیوتر
def test_computer_finds_mate_and_does_not_blunder():
    import random

    from games.chess import ai

    mate = Position.from_fen("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4")
    for level in ("medium", "hard"):
        assert str(ai.choose_move(mate, level, random.Random(3))) == "h5f7"
    # وزیر سیاه را بی‌دفاع زدن: کامپیوتر متوسط آن را می‌زند
    free_queen = Position.from_fen("rnb1kbnr/pppp1ppp/8/4p3/3qP3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3")
    assert str(ai.choose_move(free_queen, "medium", random.Random(3))) == "f3d4"
    assert ai.choose_move(Position.from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"), "hard") is None  # پات: حرکتی نیست
    assert ai.choose_move(Position.initial(), "easy", random.Random(1)) in Position.initial().legal_moves()


def test_practice_chess_api_plays_against_the_computer(client, make_user):
    from arcade.models import ChessPractice

    user = make_user(first_name="تمرین")
    assert client.get("/arcade/chess/").status_code == 200
    status, data = post(client, "practice/chess/state", user)
    assert data == {"ok": True, "changed": False, "none": True}
    status, data = post(client, "practice/chess/new", user, level="easy")
    state = data["state"]
    assert status == 200 and state["practice"] and state["level"] == "easy"
    assert state["players"][state["you"]] == "تمرین" and "کامپیوتر" in state["players"]["b" if state["you"] == "w" else "w"]
    assert state["turn"] == state["you"]  # اگر کامپیوتر سفید بود، حرکت اولش را زده است
    game_id = state["game_id"]
    for _ in range(3):
        src = next(iter(state["legal"]))
        dst = state["legal"][src][0]
        status, data = post(client, "practice/chess/move", user, game_id=game_id, src=int(src), dst=dst)
        state = data["state"]
        assert status == 200 and (state["over"] or state["turn"] == state["you"])
    assert post(client, "practice/chess/state", user)[1]["state"]["game_id"] == game_id  # ادامه‌ی بازی
    other = make_user()
    assert post(client, "practice/chess/move", other, game_id=game_id, src=12, dst=28)[0] == 404
    status, data = post(client, "practice/chess/action", user, game_id=game_id, action="resign")
    assert data["state"]["over"]["reason"] == "resign" and ChessPractice.objects.get(pk=game_id).finished
    assert post(client, "practice/chess/state", user)[1].get("none") is True
    post(client, "practice/chess/new", user, level="nonsense")
    assert ChessPractice.objects.filter(user=user, finished=False).get().level == "medium"


def test_undo_rebuilds_the_position_and_only_works_without_a_clock():
    state = live.new_state(1, 2, 1000.0, control=None)
    play(state, ["f2f3", "e7e5", "g2g4", "d8h4"])
    assert state["over"]["reason"] == "checkmate"
    version = state["version"]
    assert live.undo(state, 1) == 1 and state["over"] is None and state["version"] == version + 1
    assert state["moves"] == ["f2f3", "e7e5", "g2g4"] and state["san"] == ["f3", "e5", "g4"]
    assert state["last"] == [sq("g2"), sq("g4")] and live.position_of(state).turn == "b"
    assert live.undo(state, 10) == 3 and state["fen"] == START_FEN and state["last"] is None and state["san"] == []
    assert live.undo(state, 1) == 0
    with pytest.raises(live.LiveError, match="bad_action"):
        live.undo(live.new_state(1, 2, 1000.0), 1)  # بازی با ساعت برگشت ندارد


def test_practice_hint_and_undo(client, make_user):
    from arcade.board_views import COMPUTER_ID
    from arcade.models import ChessPractice

    user = make_user(first_name="تمرین", level=4)
    game = ChessPractice.objects.create(user=user, level="easy", state=live.new_state(user.pk, COMPUTER_ID, time.time(), control=None))
    body = {"game_id": game.pk}
    status, data = post(client, "practice/chess/action", user, action="undo", **body)
    assert status == 409 and data["error"] == "bad_action"  # هنوز حرکتی نشده
    status, data = post(client, "practice/chess/action", user, action="hint", **body)
    src, dst = data["hint"]
    assert status == 200 and dst in data["state"]["legal"][str(src)] and data["state"]["plies"] == 0
    assert data["state"]["profiles"]["w"]["level"] == 4 and data["state"]["profiles"]["b"]["emoji"] == "🤖"
    status, data = post(client, "practice/chess/move", user, src=src, dst=dst, **body)
    assert data["state"]["plies"] == 2 and data["state"]["turn"] == "w" and len(data["state"]["uci"]) == 2
    # برگشت: حرکت کامپیوتر و حرکت خود بازیکن هر دو برمی‌گردند
    status, data = post(client, "practice/chess/action", user, action="undo", **body)
    assert status == 200 and data["state"]["plies"] == 0 and data["state"]["turn"] == "w" and data["state"]["uci"] == []
    assert ChessPractice.objects.get(pk=game.pk).state["moves"] == []

    # بعد از مات شدن هم می‌شود برگشت و بازی را ادامه داد، ولی تسلیم برگشت ندارد
    state = live.new_state(COMPUTER_ID, user.pk, time.time(), control=None)
    play(state, ["f2f3", "e7e5", "g2g4"])
    live.apply_move(state, user.pk, sq("d8"), sq("h4"), "", time.time())
    game = ChessPractice.objects.create(user=user, level="easy", state=state, finished=True)
    status, data = post(client, "practice/chess/action", user, action="hint", game_id=game.pk)
    assert data["error"] == "not_your_turn"
    status, data = post(client, "practice/chess/action", user, action="undo", game_id=game.pk)
    assert status == 200 and data["state"]["plies"] == 3 and data["state"]["over"] is None and data["state"]["turn"] == "b"
    assert not ChessPractice.objects.get(pk=game.pk).finished
    post(client, "practice/chess/action", user, action="resign", game_id=game.pk)
    status, data = post(client, "practice/chess/action", user, action="undo", game_id=game.pk)
    assert status == 409 and data["error"] == "bad_action"


def test_practice_menu_has_a_chess_tile(client):
    page = client.get("/arcade/").content.decode()
    assert 'chessPractice: "/arcade/chess/"' in page
