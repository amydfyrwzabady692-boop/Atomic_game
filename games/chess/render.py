"""تصویر صفحه‌ی شطرنج برای پیام گروه: صفحه‌ی چوبی با قاب، مهره‌های استانتون حجم‌دار با سایه، و
هایلایت آخرین حرکت، مهره‌ی انتخاب‌شده، خانه‌های مجاز و کیش.

صفحه‌ی خالی (چوب، قاب و مختصات) فقط یک بار ساخته و نگه داشته می‌شود؛ هر تصویر فقط چسباندن چند
لایه‌ی آماده است.
"""

import io
import random
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from core.imaging import wood

from .engine import FILES, Move, Position
from .pieces import piece_sprite, shadow_sprite

SQUARE = 86
MARGIN = 38
BOARD = SQUARE * 8
SIZE = BOARD + MARGIN * 2

LIGHT_WOOD = (236, 213, 170)
DARK_WOOD = (156, 103, 62)
FRAME_WOOD = (74, 44, 26)
INLAY = (214, 170, 92)
COORD = (236, 214, 176)
LAST_MOVE = (255, 221, 70, 105)
SELECTED = (72, 190, 255, 125)
TARGET_DOT = (18, 14, 10, 105)
CHECK = (232, 30, 60)


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


@lru_cache(maxsize=1)
def _empty_board() -> Image.Image:
    image = Image.new("RGB", (SIZE, SIZE), FRAME_WOOD)
    # قاب: چوب تیره با پخ نور و سایه
    image.paste(wood(SIZE, SIZE, FRAME_WOOD, seed=7, horizontal=True), (0, 0))
    frame = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    fdraw = ImageDraw.Draw(frame)
    for inset, color in ((0, (0, 0, 0, 150)), (2, (255, 220, 170, 46)), (5, (0, 0, 0, 0))):
        fdraw.rounded_rectangle([inset, inset, SIZE - 1 - inset, SIZE - 1 - inset], radius=22 - inset, outline=color, width=3)
    # فرورفتگی صفحه داخل قاب و نوار طلایی دور آن
    fdraw.rectangle([MARGIN - 7, MARGIN - 7, MARGIN + BOARD + 6, MARGIN + BOARD + 6], fill=(20, 10, 4, 170))
    fdraw.rectangle([MARGIN - 4, MARGIN - 4, MARGIN + BOARD + 3, MARGIN + BOARD + 3], outline=INLAY + (255,), width=2)
    image.paste(frame, (0, 0), frame)

    light = wood(BOARD, BOARD, LIGHT_WOOD, seed=11)
    dark = wood(BOARD, BOARD, DARK_WOOD, seed=23, horizontal=True)
    rng = random.Random(5)
    draw = ImageDraw.Draw(image)
    for index in range(64):
        x, y = _square_xy(index)
        rank, file = divmod(index, 8)
        sheet = light if (rank + file) % 2 else dark
        # هر خانه تکه‌ای از جای دیگری از ورق است تا رگه‌ها یک‌دست و تکراری نباشند
        sx, sy = rng.randrange(0, BOARD - SQUARE), rng.randrange(0, BOARD - SQUARE)
        image.paste(sheet.crop((sx, sy, sx + SQUARE, sy + SQUARE)), (x, y))
    # درز باریک بین خانه‌ها
    seams = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(seams)
    for i in range(1, 8):
        offset = MARGIN + i * SQUARE
        sdraw.line([(offset, MARGIN), (offset, MARGIN + BOARD)], fill=(40, 20, 8, 70), width=1)
        sdraw.line([(MARGIN, offset), (MARGIN + BOARD, offset)], fill=(40, 20, 8, 70), width=1)
    # سایه‌ی لبه‌ی قاب روی صفحه (نور از بالا-چپ)
    for depth in range(7):
        alpha = 62 - depth * 9
        sdraw.line([(MARGIN, MARGIN + depth), (MARGIN + BOARD, MARGIN + depth)], fill=(0, 0, 0, alpha), width=1)
        sdraw.line([(MARGIN + depth, MARGIN), (MARGIN + depth, MARGIN + BOARD)], fill=(0, 0, 0, alpha), width=1)
    image.paste(seams, (0, 0), seams)

    # نور ملایم صحنه: روشن‌تر در بالا-چپ، تیره‌تر در گوشه‌ی مقابل
    glow = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(glow).ellipse([-SIZE * 0.4, -SIZE * 0.45, SIZE * 0.75, SIZE * 0.6], fill=44)
    image.paste((255, 244, 220), (0, 0), glow.filter(ImageFilter.GaussianBlur(SIZE * 0.12)))
    shade = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(shade).ellipse([SIZE * 0.35, SIZE * 0.45, SIZE * 1.5, SIZE * 1.55], fill=58)
    image.paste((16, 8, 2), (0, 0), shade.filter(ImageFilter.GaussianBlur(SIZE * 0.14)))

    # مختصات حک‌شده روی قاب
    draw = ImageDraw.Draw(image)
    font = label_font(21)
    for i in range(8):
        cx = MARGIN + i * SQUARE + SQUARE // 2
        cy = MARGIN + (7 - i) * SQUARE + SQUARE // 2
        for x, y, text in (
            (cx, MARGIN // 2 - 2, FILES[i]),
            (cx, SIZE - MARGIN // 2 + 1, FILES[i]),
            (MARGIN // 2 - 2, cy, str(i + 1)),
            (SIZE - MARGIN // 2 + 2, cy, str(i + 1)),
        ):
            draw.text((x + 1, y + 1), text, font=font, anchor="mm", fill=(20, 10, 4))
            draw.text((x, y), text, font=font, anchor="mm", fill=COORD)
    return image.convert("RGBA")


def render_board(
    position: Position,
    last_move: Move | None = None,
    selected: int | None = None,
    targets: tuple[int, ...] = (),
) -> bytes:
    """تصویر JPEG صفحه (کم‌حجم، تا هر حرکت سریع بارگذاری شود)."""
    image = _empty_board().copy()

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    if last_move is not None:
        for index in (last_move.src, last_move.dst):
            x, y = _square_xy(index)
            odraw.rectangle([x, y, x + SQUARE - 1, y + SQUARE - 1], fill=LAST_MOVE)
    if selected is not None:
        x, y = _square_xy(selected)
        odraw.rectangle([x, y, x + SQUARE - 1, y + SQUARE - 1], fill=SELECTED)
        odraw.rectangle([x + 1, y + 1, x + SQUARE - 2, y + SQUARE - 2], outline=(255, 255, 255, 150), width=2)
    image = Image.alpha_composite(image, overlay)

    # هاله‌ی قرمز زیر شاهِ کیش‌شده
    if position.in_check():
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        x, y = _square_xy(position.king_square(position.turn))
        ImageDraw.Draw(glow).ellipse([x + 4, y + 4, x + SQUARE - 4, y + SQUARE - 4], fill=CHECK + (235,))
        image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(11)))

    # اول همه‌ی سایه‌ها، بعد مهره‌ها (سایه‌ی یک مهره روی مهره‌ی کناری نمی‌افتد)
    shadow = shadow_sprite(SQUARE)
    occupied = [(index, piece) for index, piece in enumerate(position.board) if piece != "."]
    for index, _ in occupied:
        x, y = _square_xy(index)
        image.alpha_composite(shadow, (x + 3, y + 3))
    for index, piece in occupied:
        image.alpha_composite(piece_sprite(piece, SQUARE), _square_xy(index))

    # نقطه‌ی خانه‌های مجاز (حلقه برای خانه‌ی دارای مهره‌ی حریف)
    marks = Image.new("RGBA", image.size, (0, 0, 0, 0))
    mdraw = ImageDraw.Draw(marks)
    for index in targets:
        x, y = _square_xy(index)
        cx, cy = x + SQUARE // 2, y + SQUARE // 2
        if position.board[index] != "." or (position.ep == index and selected is not None):
            mdraw.ellipse([x + 4, y + 4, x + SQUARE - 5, y + SQUARE - 5], outline=(225, 40, 60, 215), width=6)
        else:
            mdraw.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=TARGET_DOT)
            mdraw.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], outline=(255, 255, 255, 70), width=2)
    image = Image.alpha_composite(image, marks)

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=90, optimize=True)
    return buffer.getvalue()
