"""شطرنج: درستی قوانین با اعداد مرجع perft و جریان بازی در گروه."""

import pytest

from games.catalog import catalog
from games.chess.engine import Move, Position, parse_square, perft
from games.chess.pieces import piece_sprite
from games.chess.render import render_board
from games.plugins.chess import ChessGame

from .fakes import FakeContext

# اعداد مرجع استاندارد (chessprogramming.org)
PERFT_CASES = [
    ("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", [20, 400, 8902]),
    ("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", [48, 2039]),
    ("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", [14, 191, 2812]),
    ("r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", [6, 264, 9467]),
    ("rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", [44, 1486]),
]


@pytest.mark.parametrize(("fen", "counts"), PERFT_CASES)
def test_perft_matches_reference(fen, counts):
    position = Position.from_fen(fen)
    assert [perft(position, depth) for depth in range(1, len(counts) + 1)] == counts


def sq(name):
    return parse_square(name)


def play(position, *moves):
    for text in moves:
        position = position.push(Move(sq(text[:2]), sq(text[2:4]), text[4:]))
    return position


def test_outcomes():
    mate = play(Position.initial(), "f2f3", "e7e5", "g2g4", "d8h4")
    assert mate.outcome() == "checkmate" and mate.in_check()
    assert Position.from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1").outcome() == "stalemate"
    assert Position.from_fen("8/8/4k3/8/8/2B5/4K3/8 w - - 0 1").outcome() == "insufficient"
    assert Position.from_fen("8/8/4k3/8/8/2R5/4K3/8 w - - 100 80").outcome() == "fifty"
    assert Position.initial().outcome() is None


def test_special_moves():
    # قلعه‌ی کوتاه رخ را هم جابه‌جا می‌کند و حق قلعه را می‌گیرد
    castled = play(Position.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"), "e1g1")
    assert castled.board[sq("g1")] == "K" and castled.board[sq("f1")] == "R" and "K" not in castled.castling
    # از خانه‌ی تهدیدشده نمی‌شود قلعه رفت
    attacked = Position.from_fen("4kr2/8/8/8/8/8/8/4K2R w K - 0 1")
    assert Move(sq("e1"), sq("g1")) not in attacked.legal_moves()
    # آن‌پاسان
    ep = play(Position.initial(), "e2e4", "a7a6", "e4e5", "d7d5")
    assert ep.ep == sq("d6")
    after = play(ep, "e5d6")
    assert after.board[sq("d5")] == "." and after.board[sq("d6")] == "P"
    # ارتقا
    promo = Position.from_fen("8/P7/8/8/8/8/8/k6K w - - 0 1")
    assert {m.promo for m in promo.moves_from(sq("a7"))} == {"Q", "R", "B", "N"}
    # مهره‌ی سنجاق‌شده نمی‌تواند حرکت کند
    pinned = Position.from_fen("4r1k1/8/8/8/8/8/4B3/4K3 w - - 0 1")
    assert pinned.moves_from(sq("e2")) == []


JPEG = b"\xff\xd8\xff"


def test_board_image_renders():
    position = play(Position.initial(), "e2e4", "e7e5")
    image = render_board(position, Move(sq("e7"), sq("e5")), sq("g1"), (sq("f3"), sq("h3")))
    assert image[:3] == JPEG and 20_000 < len(image) < 400_000  # کم‌حجم، تا هر حرکت سریع بارگذاری شود
    # هایلایت‌ها و کیش تصویر را عوض می‌کنند
    plain = render_board(position)
    assert plain != image
    mate = Position.from_fen("r1bqkbnr/pppp1Qpp/2n5/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4")
    assert mate.in_check() and render_board(mate) != plain


def test_every_piece_has_its_own_drawn_sprite():
    """مهره‌ها رویه‌ای کشیده می‌شوند (بدون فونت)؛ هر ۱۲ مهره باید شکل و رنگ خودش را داشته باشد."""
    sprites = {letter: piece_sprite(letter, 86) for letter in "KQRBNPkqrbnp"}
    for letter, sprite in sprites.items():
        assert sprite.size == (86, 86) and sprite.mode == "RGBA"
        alpha = sprite.getchannel("A")
        covered = sum(alpha.histogram()[129:])
        assert 900 < covered < 5200, letter  # نه خالی، نه کل خانه
        assert alpha.getpixel((2, 2)) == 0 and alpha.getpixel((83, 2)) == 0  # گوشه‌ها شفاف
    assert len({sprite.tobytes() for sprite in sprites.values()}) == 12
    # شاه بلندتر از سرباز است و مهره‌ی سفید روشن‌تر از سیاه
    assert sprites["K"].getbbox()[1] < sprites["P"].getbbox()[1]
    white_mid = sprites["R"].convert("L").getpixel((43, 60))
    black_mid = sprites["r"].convert("L").getpixel((43, 60))
    assert white_mid > black_mid + 60


# ====================================================================== بازی در گروه
async def start_game():
    ctx = FakeContext(n_players=2)
    game = ChessGame(ctx)
    await game.start()
    white = ctx.players.index(game.white)
    black = ctx.players.index(game.black)
    return ctx, game, white, black


async def tap(ctx, game, player, square):
    cb = ctx.cb(player, f"q:{sq(square)}" if len(square) == 2 else square)
    await game.on_callback(cb)
    return cb


async def move(ctx, game, player, src, dst):
    await tap(ctx, game, player, src)
    await tap(ctx, game, player, dst)


def test_chess_registered_as_two_player_game():
    info = catalog()["chess"]
    assert info.min_players == info.max_players == 2 and not info.is_arcade


async def test_start_sends_board_photo_with_8x8_keyboard():
    ctx, game, white, black = await start_game()
    first = ctx.sent[0]
    assert first["photo"][:3] == JPEG
    assert len(first["buttons"]) == 9 and all(len(row) == 8 for row in first["buttons"][:8])
    assert first["buttons"][7][4][1] == f"q:{sq('e1')}"  # ردیف آخر = ردیف ۱، ستون e
    assert "نوبت" in first["text"] and "شطرنج" in first["text"]
    assert "move" in ctx.timers


async def test_select_shows_targets_and_wrong_turn_is_rejected():
    ctx, game, white, black = await start_game()
    wrong = await tap(ctx, game, black, "e7")
    assert wrong.answers[-1][0] == "نوبت تو نیست!"
    await tap(ctx, game, white, "e2")
    assert game.selected == sq("e2")
    keyboard = ctx.edits[-1]["buttons"]
    labels = {keyboard[7 - (s // 8)][s % 8][0] for s in (sq("e3"), sq("e4"))}
    assert labels == {"•"} and keyboard[6][4][0] == "◉"
    enemy = await tap(ctx, game, white, "e7")
    assert game.selected is None and enemy.answers[-1][0] == "یکی از مهره‌های خودت را انتخاب کن."


async def test_fools_mate_ends_game_with_winner():
    ctx, game, white, black = await start_game()
    await move(ctx, game, white, "f2", "f3")
    await move(ctx, game, black, "e7", "e5")
    await move(ctx, game, white, "g2", "g4")
    await move(ctx, game, black, "d8", "h4")
    assert ctx.ended and game.finished
    standings = {s.user_id: s.score for s in await game.finish()}
    assert standings[game.black.user_id] == 1 and standings[game.white.user_id] == 0
    final = ctx.edits[-1]
    assert "مات" in final["text"] and final["buttons"] is None


async def test_resign_draw_and_timeout():
    ctx, game, white, black = await start_game()
    await tap(ctx, game, black, "resign")
    assert ctx.ended and game.scores[game.white.user_id] == 1

    ctx, game, white, black = await start_game()
    await tap(ctx, game, white, "draw")
    assert not ctx.ended and "پیشنهاد مساوی" in ctx.edits[-1]["text"]
    await tap(ctx, game, black, "draw")
    assert ctx.ended and sum(game.scores.values()) == 0 and "توافق" in ctx.edits[-1]["text"]

    ctx, game, white, black = await start_game()
    await move(ctx, game, white, "e2", "e4")
    await ctx.fire("move")  # وقت سیاه تمام شد
    assert ctx.ended and game.scores[game.white.user_id] == 1


async def test_in_chat_chess_uses_the_chosen_time_control():
    ctx = FakeContext(n_players=2, options={"variant": "blitz3"})
    game = ChessGame(ctx)
    await game.start()
    white, black = ctx.players.index(game.white), ctx.players.index(game.black)
    caption = ctx.sent[0]["text"]
    assert "برق‌آسا \u200e۳+۲" in caption and "۳:۰۰" in caption and "اولین حرکت" in caption
    assert ctx.timers["move"][0] == ctx.clock + game.first_move_seconds
    await move(ctx, game, white, "e2", "e4")
    await move(ctx, game, black, "e7", "e5")
    assert game.clock == {"w": 180.0, "b": 180.0}  # اولین حرکت‌ها مجانی‌اند
    ctx.clock += 30
    await move(ctx, game, white, "g1", "f3")
    assert game.clock["w"] == 152.0 and "۲:۳۲" in ctx.edits[-1]["text"] and "♘f3" in ctx.edits[-1]["text"]
    assert ctx.timers["move"][0] == ctx.clock + 180.0  # ساعت سیاه
    await ctx.fire("move")
    assert ctx.ended and game.scores[game.white.user_id] == 1 and "وقت" in ctx.edits[-1]["text"]


def test_time_control_labels_never_flip_in_right_to_left_text():
    """بدون نشانه‌ی چپ‌به‌راست، «۳+۲» بعد از حرف فارسی برعکس («۲+۳») نمایش داده می‌شود."""
    import re

    from core import texts
    from games.chess import live

    assert set(texts.CHESS_CONTROLS) == set(live.TIME_CONTROLS)
    for line in [*texts.CHESS_CONTROLS.values(), *ChessGame.rules(), ChessGame.description_fa]:
        for match in re.finditer(r"[۰-۹]+\+[۰-۹]+", line):
            assert line[match.start() - 1] == "\u200e", line


async def test_in_chat_chess_flag_against_lone_king_draws():
    ctx, game, white, black = await start_game()
    game.position = Position.from_fen("7k/8/8/8/8/8/8/KQ6 w - - 0 1")
    await ctx.fire("move")
    assert ctx.ended and sum(game.scores.values()) == 0 and "مساوی" in ctx.edits[-1]["text"]


async def test_outsiders_cannot_play_and_threefold_repetition_draws():
    ctx, game, white, black = await start_game()
    outsider = await tap(ctx, game, None, "e2")
    assert outsider.answers[-1] == ("تو عضو این مسابقه نیستی.", True)
    for _ in range(2):
        await move(ctx, game, white, "g1", "f3")
        await move(ctx, game, black, "g8", "f6")
        await move(ctx, game, white, "f3", "g1")
        await move(ctx, game, black, "f6", "g8")
    assert ctx.ended and "تکرار" in ctx.edits[-1]["text"]


async def test_pawn_promotes_to_queen_automatically():
    ctx, game, white, black = await start_game()
    game.position = Position.from_fen("8/P6k/8/8/8/8/8/K7 w - - 0 1")
    if game.position.turn == "w" and game.current is not game.white:
        pytest.skip()
    await move(ctx, game, white, "a7", "a8")
    assert game.position.board[sq("a8")] == "Q"
