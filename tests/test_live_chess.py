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
    assert state["moves"] == ["e2e4"] and state["last"] == [sq("e2"), sq("e4")]
    assert state["deadline"] == 1005.0 + state["move_seconds"] and state["version"] == 2

    mine = live.view(state, 2, 1010.0)
    assert mine["you"] == "b" and mine["turn"] == "b" and len(mine["legal"]) == 10 and mine["seconds_left"] == 85
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
    assert not live.check_timeout(state, 1089.0)
    assert live.check_timeout(state, 1091.0) and state["over"] == {"reason": "timeout", "side": "b", "winner": 2}

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
    assert same == {"ok": True, "changed": False, "seconds_left": same["seconds_left"]} and same["seconds_left"] > 80

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
    return group, users


async def start_chess(app):
    group, users = await make_world()
    manager = MatchManager(app)
    active = await manager.create_lobby(group, users[0], get_info("chess"), fee=0, split=[100], join_seconds=60, options={})
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
    assert active.phase == "done" and CHAT_ID not in manager.active
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
    resumed = restarted.active[CHAT_ID]
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
