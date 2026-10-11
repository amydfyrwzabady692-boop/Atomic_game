"""تصویر صفحه‌ی شطرنج برای پیام گروه: طراحی تیره‌ی تمیز با هایلایت آخرین حرکت، مهره‌ی
انتخاب‌شده، خانه‌های مجاز و کیش."""

import io
import os
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .engine import FILES, Move, Position

SQUARE = 86
MARGIN = 38
BOARD = SQUARE * 8
SIZE = BOARD + MARGIN * 2

FRAME = (20, 24, 52)
FRAME_EDGE = (62, 70, 128)
LIGHT = (233, 237, 248)
DARK = (122, 139, 198)
LAST_MOVE = (255, 214, 102, 120)
SELECTED = (110, 231, 255, 150)
TARGET_DOT = (20, 24, 52, 110)
CHECK = (255, 70, 110)
COORD = (165, 176, 222)

# حروف یکسان (مهره‌های توپر) برای هر دو رنگ؛ رنگ پرکردن تعیین می‌کند سفید است یا سیاه
GLYPHS = {"K": "♚", "Q": "♛", "R": "♜", "B": "♝", "N": "♞", "P": "♟"}

FONT_CANDIDATES = [
    os.environ.get("CHESS_FONT_PATH", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "C:/Windows/Fonts/seguisym.ttf",
    "/System/Library/Fonts/Apple Symbols.ttf",
]


@lru_cache(maxsize=4)
def piece_font(size: int):
    for path in FONT_CANDIDATES:
        if path and Path(path).is_file():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return None


@lru_cache(maxsize=4)
def label_font(size: int):
    from games.content.typing_image import load_font

    try:
        return load_font(size)
    except RuntimeError:  # pragma: no cover
        return ImageFont.load_default()


def _square_xy(index: int) -> tuple[int, int]:
    """گوشه‌ی بالا-چپ خانه روی تصویر (سفید همیشه پایین است)."""
    rank, file = divmod(index, 8)
    return MARGIN + file * SQUARE, MARGIN + (7 - rank) * SQUARE


def _draw_piece(draw: ImageDraw.ImageDraw, piece: str, x: int, y: int) -> None:
    white = piece.isupper()
    font = piece_font(int(SQUARE * 0.78))
    cx, cy = x + SQUARE // 2, y + SQUARE // 2
    if font is None:  # بدون فونت نمادها: حرف مهره
        text_font = label_font(34)
        draw.text((cx, cy), piece.upper(), font=text_font, anchor="mm", fill=(255, 255, 255) if white else (20, 24, 52))
        return
    glyph = GLYPHS[piece.upper()]
    # سایه‌ی نرم زیر مهره
    draw.text((cx + 2, cy + 4), glyph, font=font, anchor="mm", fill=(10, 12, 30, 90))
    if white:
        draw.text((cx, cy), glyph, font=font, anchor="mm", fill=(255, 255, 255), stroke_width=3, stroke_fill=(30, 34, 70))
    else:
        draw.text((cx, cy), glyph, font=font, anchor="mm", fill=(26, 30, 58), stroke_width=3, stroke_fill=(240, 243, 255))


def render_board(
    position: Position,
    last_move: Move | None = None,
    selected: int | None = None,
    targets: tuple[int, ...] = (),
) -> bytes:
    image = Image.new("RGBA", (SIZE, SIZE), FRAME + (255,))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([4, 4, SIZE - 5, SIZE - 5], radius=26, outline=FRAME_EDGE, width=3)

    for index in range(64):
        x, y = _square_xy(index)
        rank, file = divmod(index, 8)
        draw.rectangle([x, y, x + SQUARE - 1, y + SQUARE - 1], fill=LIGHT if (rank + file) % 2 else DARK)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    if last_move is not None:
        for index in (last_move.src, last_move.dst):
            x, y = _square_xy(index)
            odraw.rectangle([x, y, x + SQUARE - 1, y + SQUARE - 1], fill=LAST_MOVE)
    if selected is not None:
        x, y = _square_xy(selected)
        odraw.rectangle([x, y, x + SQUARE - 1, y + SQUARE - 1], fill=SELECTED)
    image = Image.alpha_composite(image, overlay)

    # هاله‌ی قرمز دور شاهِ کیش‌شده
    if position.in_check():
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(glow)
        x, y = _square_xy(position.king_square(position.turn))
        gdraw.ellipse([x + 6, y + 6, x + SQUARE - 6, y + SQUARE - 6], fill=CHECK + (210,))
        image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(10)))

    draw = ImageDraw.Draw(image)
    for index, piece in enumerate(position.board):
        if piece != ".":
            x, y = _square_xy(index)
            _draw_piece(draw, piece, x, y)

    # نقطه‌ی خانه‌های مجاز (حلقه برای خانه‌ی دارای مهره‌ی حریف)
    marks = Image.new("RGBA", image.size, (0, 0, 0, 0))
    mdraw = ImageDraw.Draw(marks)
    for index in targets:
        x, y = _square_xy(index)
        cx, cy = x + SQUARE // 2, y + SQUARE // 2
        if position.board[index] != "." or (position.ep == index and selected is not None):
            mdraw.ellipse([x + 5, y + 5, x + SQUARE - 6, y + SQUARE - 6], outline=TARGET_DOT, width=7)
        else:
            mdraw.ellipse([cx - 13, cy - 13, cx + 13, cy + 13], fill=TARGET_DOT)
    image = Image.alpha_composite(image, marks)

    draw = ImageDraw.Draw(image)
    font = label_font(22)
    for i in range(8):
        cx = MARGIN + i * SQUARE + SQUARE // 2
        draw.text((cx, MARGIN // 2 + 1), FILES[i], font=font, anchor="mm", fill=COORD)
        draw.text((cx, SIZE - MARGIN // 2 - 1), FILES[i], font=font, anchor="mm", fill=COORD)
        cy = MARGIN + (7 - i) * SQUARE + SQUARE // 2
        draw.text((MARGIN // 2, cy), str(i + 1), font=font, anchor="mm", fill=COORD)
        draw.text((SIZE - MARGIN // 2, cy), str(i + 1), font=font, anchor="mm", fill=COORD)

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
