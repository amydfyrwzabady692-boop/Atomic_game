"""کارت تصویری نتیجه‌ی مسابقه: سکوی سه‌نفره‌ی برندگان با مدال، نام، امتیاز و جایزه.

کارت همراه همان متن نتیجه (به‌عنوان کپشن) فرستاده می‌شود؛ اگر ساخت یا ارسال تصویر به هر دلیلی نشد،
ربات فقط متن را می‌فرستد.
"""

import io
import random
import re
import unicodedata
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from core.imaging import vertical_gradient
from core.textutils import fa_num
from games.content.typing_image import load_font, shape

WIDTH, HEIGHT = 900, 600
FLOOR = 556
CAPTION_LIMIT = 1000  # سقف تلگرام ۱۰۲۴ نویسه‌ی قابل‌دیدن است
NAME_CHARS = 18
ZWNJ = "‌"

GOLD = (255, 200, 87)
SILVER = (203, 211, 226)
BRONZE = (219, 144, 92)
MUTED = (186, 195, 230)
# رنگ و ارتفاع سکو برای هر رتبه
RANK_STYLE = {1: (GOLD, 176), 2: (SILVER, 128), 3: (BRONZE, 96)}
# وسط ستون‌ها به ترتیب جایگاه، بسته به تعداد نفرات روی سکو (نفر اول وسط؛ در دوئل سمت راست)
SLOTS = {1: [450], 2: [559, 341], 3: [450, 232, 668]}
BLOCK_W = 204
TEXT_W = BLOCK_W - 4
TAG = re.compile(r"<[^>]+>")


def visible_length(html: str) -> int:
    """طول متن بعد از حذف تگ‌های HTML، به واحد UTF-16 (همان چیزی که تلگرام برای سقف کپشن می‌شمارد)."""
    return len(TAG.sub("", html).encode("utf-16-le")) // 2


@lru_cache(maxsize=4096)
def _ink(ch: str) -> bytes:
    image = Image.new("L", (56, 60), 0)
    ImageDraw.Draw(image).text((10, 6), ch, font=load_font(34), fill=255)
    return image.tobytes()


def _drawable(ch: str) -> bool:
    """آیا فونت برای این نویسه شکلی دارد؟ (با شکلِ «نویسه‌ی ناموجود» فونت مقایسه می‌شود)"""
    if ch == " " or ch == ZWNJ:
        return True
    if ord(ch) > 0xFFFF or unicodedata.category(ch)[0] not in "LMNP":
        return False
    return _ink(ch) != _ink("￿")


def clean_name(name: str) -> str:
    """ایموجی و نویسه‌هایی که فونت ندارد حذف می‌شوند تا مربع خالی روی کارت نیفتد."""
    kept = "".join(ch for ch in name.replace(" ", " ") if _drawable(ch))
    kept = " ".join(kept.split()).strip(ZWNJ + " ") or "بازیکن"
    return kept if len(kept) <= NAME_CHARS else kept[: NAME_CHARS - 1].rstrip() + "…"


def _shade(color, factor: float):
    return tuple(max(0, min(255, round(c * factor))) for c in color)


def _fit(text: str, size: int, max_width: int, smallest: int = 18):
    """بزرگ‌ترین فونتی (تا ``size``) که متن با آن در ``max_width`` جا شود."""
    shaped = shape(text)
    while size > smallest and load_font(size).getlength(shaped) > max_width:
        size -= 2
    return load_font(size)


def _soft(image: Image.Image, box, blur: float, paint) -> None:
    """یک لایه‌ی محو را فقط به اندازه‌ی ``box`` می‌سازد و روی تصویر می‌نشاند (محو کردن کل تصویر کند است)."""
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    paint(ImageDraw.Draw(layer), -x0, -y0)
    image.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)), (x0, y0))


def _text(draw, xy, text: str, font, fill, bold: bool = False):
    draw.text(xy, shape(text), font=font, fill=fill, anchor="mm", stroke_width=1 if bold else 0, stroke_fill=fill)


def _background(rng: random.Random) -> Image.Image:
    image = vertical_gradient(WIDTH, HEIGHT, (34, 26, 84), (8, 10, 28)).convert("RGBA")
    # هاله‌ی طلایی پشت سکو و دو نور رنگی کناری (در یک‌چهارم اندازه محو و بعد بزرگ می‌شود)
    glow = Image.new("RGBA", (WIDTH // 4, HEIGHT // 4), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    draw.ellipse([52, 38, 172, 155], fill=GOLD + (70,))
    draw.ellipse([-40, -30, 75, 65], fill=(110, 231, 255, 46))
    draw.ellipse([155, -35, 265, 60], fill=(167, 139, 250, 54))
    glow = glow.filter(ImageFilter.GaussianBlur(17)).resize(image.size, Image.BICUBIC)
    image = Image.alpha_composite(image, glow)
    # پرتوهای نور از پشت سکو
    rays = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(rays)
    for index in range(-5, 6):
        x = WIDTH / 2 + index * 150
        draw.polygon([(WIDTH / 2 - 14, FLOOR), (WIDTH / 2 + 14, FLOOR), (x + 46, 0), (x - 46, 0)], fill=(255, 236, 170, 15))
    image = Image.alpha_composite(image, rays.filter(ImageFilter.BoxBlur(4)))
    # کاغذرنگی
    confetti = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(confetti)
    palette = [GOLD, (110, 231, 255), (255, 92, 122), (94, 230, 168), (167, 139, 250)]
    for _ in range(64):
        x, y = rng.randint(0, WIDTH), rng.randint(150, 520)
        if 130 < x < 770 and y > 170:  # روی نام‌ها و سکو نمی‌افتد
            y = rng.randint(4, 40)
        w, h, tilt = rng.randint(5, 11), rng.randint(9, 17), rng.uniform(-0.8, 0.8)
        color = palette[rng.randrange(len(palette))] + (rng.randint(110, 215),)
        draw.polygon([(x, y), (x + w, y + w * tilt), (x + w - h * tilt, y + w * tilt + h), (x - h * tilt, y + h)], fill=color)
    return Image.alpha_composite(image, confetti)


def _podium_block(image: Image.Image, color, cx: int, height: int, rank: int) -> int:
    """سکوی یک رتبه را می‌کشد و y بالای آن را برمی‌گرداند."""
    top, left, right, depth = FLOOR - height, cx - BLOCK_W // 2, cx + BLOCK_W // 2, 16
    # بازتاب سکو روی کف صحنه
    _soft(
        image,
        (left - 12, FLOOR - 4, right + 12, HEIGHT),
        5,
        lambda d, ox, oy: d.rectangle([left + ox, FLOOR + 6 + oy, right + ox, HEIGHT + 20 + oy], fill=color + (46,)),
    )
    draw = ImageDraw.Draw(image)
    # وجه بالا
    draw.polygon([(left, top), (left + depth, top - depth), (right + depth, top - depth), (right, top)], fill=_shade(color, 1.12))
    # وجه کناری
    draw.polygon([(right, top), (right + depth, top - depth), (right + depth, FLOOR - depth), (right, FLOOR)], fill=_shade(color, 0.5))
    # وجه جلو با سایه‌روشن عمودی
    for step in range(height):
        t = step / max(1, height - 1)
        draw.line([(left, top + step), (right, top + step)], fill=_shade(color, 0.96 - 0.42 * t))
    draw.line([(left, top), (right, top)], fill=_shade(color, 1.25), width=2)
    _text(draw, (cx, top + height / 2 + 2), fa_num(rank), load_font(min(84, height - 24)), _shade(color, 0.4), bold=True)
    return top


def _medal(image: Image.Image, color, cx: int, cy: int) -> None:
    _soft(
        image,
        (cx - 50, cy - 44, cx + 54, cy + 60),
        6,
        lambda d, ox, oy: d.ellipse([cx - 28 + ox, cy - 20 + oy, cx + 32 + ox, cy + 38 + oy], fill=(0, 0, 0, 130)),
    )
    draw = ImageDraw.Draw(image)
    # روبان
    draw.polygon([(cx - 24, cy - 56), (cx - 7, cy - 56), (cx + 7, cy - 12), (cx - 10, cy - 12)], fill=(229, 56, 59))
    draw.polygon([(cx + 24, cy - 56), (cx + 7, cy - 56), (cx - 7, cy - 12), (cx + 10, cy - 12)], fill=(47, 111, 214))
    # قرص مدال: لبه، رویه، برق بالا-چپ و ستاره
    draw.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill=_shade(color, 0.6))
    draw.ellipse([cx - 26, cy - 26, cx + 26, cy + 26], fill=color)
    draw.pieslice([cx - 26, cy - 26, cx + 26, cy + 26], 190, 280, fill=_shade(color, 1.2))
    draw.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill=_shade(color, 0.94))
    draw.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], outline=_shade(color, 0.68), width=2)
    star = []
    for index in range(10):
        radius = 13 if index % 2 == 0 else 5.6
        vector = complex(0, -radius) * complex(0.809016994, 0.587785252) ** index  # چرخش ۳۶ درجه
        star.append((cx + vector.real, cy + vector.imag))
    draw.polygon(star, fill=_shade(color, 0.56))


def render_result_card(title: str, players: list[tuple[int, str, int, int]], pot: int, seed: int = 0) -> bytes:
    """``players``: فهرست (رتبه، نام، امتیاز، جایزه). فقط سه جایگاه اول روی سکو می‌آیند."""
    image = _background(random.Random(seed))
    draw = ImageDraw.Draw(image)
    _text(draw, (WIDTH / 2, 62), f"پایان {title}", _fit(f"پایان {title}", 52, WIDTH - 120, 30), (255, 255, 255), bold=True)
    footer = f"جایزه‌ی کل: {fa_num(pot)} سکه" if pot else "مسابقه‌ی دوستانه"
    _text(draw, (WIDTH / 2, 120), footer, load_font(28), GOLD if pot else MUTED)

    # کف صحنه
    draw.rectangle([0, FLOOR, WIDTH, HEIGHT], fill=(13, 14, 36))
    draw.line([(0, FLOOR), (WIDTH, FLOOR)], fill=(70, 74, 120), width=2)

    # رتبه‌ی مشترک هم جایگاه خودش را می‌گیرد (دو نفرِ اول، دو سکوی طلایی هم‌قد)
    placed = [row for row in sorted(players, key=lambda row: row[0]) if row[0] in RANK_STYLE][:3]
    columns = sorted(zip(SLOTS.get(len(placed), []), placed, strict=True))  # از چپ به راست کشیده می‌شوند
    for cx, (rank, name, score, prize) in columns:
        color, height = RANK_STYLE[rank]
        top = _podium_block(image, color, cx, height, rank)
        _medal(image, color, cx, top - 48)
        draw = ImageDraw.Draw(image)
        lines = [(f"{fa_num(score)} امتیاز", 24, MUTED, False)]
        if prize:
            lines.append((f"+{fa_num(prize)} سکه", 24, GOLD, True))
        y = top - 126
        for text, size, fill, bold in reversed(lines):
            _text(draw, (cx, y), text, _fit(text, size, TEXT_W, 16), fill, bold=bold)
            y -= 32
        shown = clean_name(name)
        _text(draw, (cx, y - 6), shown, _fit(shown, 34, TEXT_W), (255, 255, 255), bold=True)

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=88, optimize=True)
    return buffer.getvalue()


def result_card(result, info) -> bytes | None:
    """کارت نتیجه برای خروجی ``finish_match``؛ اگر ساختنی نبود ``None``."""
    try:
        rows = [(r.rank, r.user.display_name, r.score, r.prize) for r in result.players if r.rank <= 3]
        if not rows:
            return None
        return render_result_card(info.title_fa, rows, result.match.pot, seed=result.match.pk)
    except Exception:  # فونت پیدا نشد یا هر خطای تصویرسازی: نتیجه‌ی متنی کافی است
        return None
