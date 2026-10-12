"""تبدیل جمله‌ی مسابقه‌ی تایپ به تصویر، تا کپی‌-پیست ممکن نباشد."""

import io
import os
from functools import lru_cache
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    os.environ.get("TYPING_FONT_PATH", ""),
    str(Path(__file__).parent / "fonts" / "Vazirmatn-Regular.ttf"),
    "/usr/share/fonts/truetype/vazirmatn/Vazirmatn-Regular.ttf",
    "/usr/share/fonts/truetype/vazirmatn/Vazirmatn[wght].ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/Vazirmatn-Regular.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]

WIDTH = 900
OUTER = 26  # فاصله‌ی برگه از لبه‌ی تصویر (میز)
PADDING = 44
LINE_HEIGHT = 82
DESK = (86, 52, 30)
PAPER_TOP = (253, 249, 236)
PAPER_BOTTOM = (243, 235, 214)
INK = (30, 32, 48)
RULE = (120, 160, 205)
MARGIN_LINE = (222, 92, 92)


def _candidates() -> list[str]:
    # بسته‌ی fonts-vazirmatn در توزیع‌های مختلف نام فایل متفاوتی دارد
    found = sorted(str(p) for p in Path("/usr/share/fonts").rglob("Vazirmatn*Regular*.ttf")) if os.name != "nt" else []
    return [FONT_CANDIDATES[0], FONT_CANDIDATES[1], *found, *FONT_CANDIDATES[2:]]


@lru_cache(maxsize=32)
def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _candidates():
        if path and Path(path).is_file():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    raise RuntimeError("فونت فارسی پیدا نشد؛ مسیر را با TYPING_FONT_PATH مشخص کنید.")


def shape(text: str) -> str:
    """حروف فارسی را به شکل چسبان درمی‌آورد و ترتیب نمایش راست‌به‌چپ را می‌سازد."""
    return get_display(arabic_reshaper.reshape(text))


def wrap(text: str, font, max_width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and font.getlength(shape(candidate)) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def render_sentence(text: str, noise_seed: int = 0) -> bytes:
    """تصویر PNG جمله: یک برگه‌ی دفتر خط‌دار روی میز چوبی، با چند خط و لکه برای سخت‌تر شدن OCR خودکار."""
    import random

    from core.imaging import drop_shadow, vertical_gradient, wood

    font = load_font(46)
    text_right = WIDTH - OUTER - PADDING - 22  # سمت راست متن، کنار خط حاشیه
    lines = wrap(text, font, text_right - OUTER - PADDING)
    card_height = PADDING * 2 + LINE_HEIGHT * len(lines)
    height = card_height + OUTER * 2
    card = [OUTER, OUTER, WIDTH - OUTER, OUTER + card_height]
    rng = random.Random(noise_seed)

    image = wood(WIDTH, height, DESK, seed=31, horizontal=True).convert("RGBA")
    image.alpha_composite(drop_shadow(image.size, [card[0] + 2, card[1] + 9, card[2] + 4, card[3] + 11], 16, 9, 150))

    # برگه با گوشه‌های گرد
    paper = vertical_gradient(WIDTH, height, PAPER_TOP, PAPER_BOTTOM).convert("RGBA")
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(card, radius=16, fill=255)
    image.paste(paper, (0, 0), mask)

    marks = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(marks)
    # خط‌های دفتر و خط قرمز حاشیه
    for index in range(len(lines) + 1):
        y = OUTER + PADDING + index * LINE_HEIGHT - 12
        if card[1] + 14 < y < card[3] - 10:
            draw.line([(card[0] + 8, y), (card[2] - 8, y)], fill=RULE + (120,), width=2)
    margin_x = WIDTH - OUTER - PADDING
    draw.line([(margin_x, card[1] + 6), (margin_x, card[3] - 6)], fill=MARGIN_LINE + (170,), width=2)
    # بافت کاغذ و خط‌خطی‌های کم‌رنگ (ضد OCR)
    for _ in range(260):
        x, y = rng.randint(card[0] + 6, card[2] - 6), rng.randint(card[1] + 6, card[3] - 6)
        draw.point((x, y), fill=(90, 70, 40, rng.randint(18, 60)))
    for _ in range(5):
        y1, y2 = rng.randint(card[1] + 10, card[3] - 10), rng.randint(card[1] + 10, card[3] - 10)
        draw.line([(card[0] + 10, y1), (card[2] - 10, y2)], fill=(70, 80, 110, rng.randint(40, 70)), width=2)
    for _ in range(3):
        cx, cy, r = rng.randint(card[0] + 60, card[2] - 60), rng.randint(card[1], card[3]), rng.randint(40, 110)
        draw.arc([cx - r, cy - r, cx + r, cy + r], rng.randint(0, 180), rng.randint(200, 360), fill=(70, 80, 110, 46), width=2)
    marks.putalpha(Image.composite(marks.getchannel("A"), Image.new("L", image.size, 0), mask))
    image.alpha_composite(marks)

    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        shaped = shape(line)
        width = font.getlength(shaped)
        # راست‌چین، روی خط دفتر
        draw.text((text_right - width, OUTER + PADDING + index * LINE_HEIGHT), shaped, font=font, fill=INK)
    # لبه‌ی روشن بالای برگه
    draw.rounded_rectangle(card, radius=16, outline=(255, 255, 255, 120), width=1)

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
