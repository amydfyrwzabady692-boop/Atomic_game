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
PADDING = 48
BACKGROUND = (24, 28, 44)
FOREGROUND = (245, 247, 255)
ACCENT = (86, 204, 242)


def _candidates() -> list[str]:
    # بسته‌ی fonts-vazirmatn در توزیع‌های مختلف نام فایل متفاوتی دارد
    found = sorted(str(p) for p in Path("/usr/share/fonts").rglob("Vazirmatn*Regular*.ttf")) if os.name != "nt" else []
    return [FONT_CANDIDATES[0], FONT_CANDIDATES[1], *found, *FONT_CANDIDATES[2:]]


@lru_cache(maxsize=4)
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
    """تصویر PNG جمله را برمی‌گرداند."""
    import random

    font = load_font(46)
    lines = wrap(text, font, WIDTH - 2 * PADDING)
    line_height = 78
    height = PADDING * 2 + line_height * len(lines)
    image = Image.new("RGB", (WIDTH, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    # چند خط کم‌رنگ برای سخت‌تر شدن OCR خودکار
    rng = random.Random(noise_seed)
    for _ in range(6):
        y1, y2 = rng.randint(0, height), rng.randint(0, height)
        draw.line([(0, y1), (WIDTH, y2)], fill=(44, 52, 78), width=2)
    draw.rounded_rectangle([8, 8, WIDTH - 8, height - 8], radius=24, outline=ACCENT, width=3)
    for index, line in enumerate(lines):
        shaped = shape(line)
        width = font.getlength(shaped)
        # راست‌چین
        draw.text((WIDTH - PADDING - width, PADDING + index * line_height), shaped, font=font, fill=FOREGROUND)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
