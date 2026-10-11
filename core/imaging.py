"""ابزارهای مشترک تصویرسازی با Pillow برای تصویرهایی که ربات می‌فرستد (صفحه‌ی شطرنج، برگه‌ی تایپ)."""

import random

from PIL import Image, ImageDraw, ImageFilter


def wood(width: int, height: int, color: tuple[int, int, int], seed: int, horizontal: bool = False) -> Image.Image:
    """ورق چوب با رگه‌های بلند و لکه‌های تُن؛ قطعی (با هر بار اجرا یک شکل)."""
    rng = random.Random(seed)
    sheet = Image.new("RGB", (width, height), color)
    grain = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(grain)
    across, along = (height, width) if horizontal else (width, height)
    # نوارهای پهن تُن
    for _ in range(max(6, across // 26)):
        position, thickness = rng.uniform(0, across), rng.uniform(8, 34)
        tone = (255, 240, 210, rng.randint(8, 22)) if rng.random() < 0.5 else (60, 30, 10, rng.randint(8, 24))
        box = [0, position, along, position + thickness] if horizontal else [position, 0, position + thickness, along]
        draw.rectangle(box, fill=tone)
    grain = grain.filter(ImageFilter.GaussianBlur(5))
    draw = ImageDraw.Draw(grain)
    # رگه‌های باریک کمی موج‌دار
    for _ in range(across * 2 // 3):
        position = rng.uniform(0, across)
        dark = rng.random() < 0.72
        tone = (52, 26, 8, rng.randint(14, 46)) if dark else (255, 236, 200, rng.randint(10, 30))
        points, drift = [], rng.uniform(-3, 3)
        for step in range(9):
            t = step / 8
            wobble = position + drift * t + rng.uniform(-0.9, 0.9)
            points.append((t * along, wobble) if horizontal else (wobble, t * along))
        draw.line(points, fill=tone, width=1)
    sheet.paste(grain, (0, 0), grain)
    return sheet.filter(ImageFilter.GaussianBlur(0.5))


def drop_shadow(size: tuple[int, int], box: list[int], radius: int, blur: float, alpha: int) -> Image.Image:
    """لایه‌ی شفافِ سایه‌ی نرم یک مستطیل گوشه‌گرد."""
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=alpha)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.putalpha(mask.filter(ImageFilter.GaussianBlur(blur)))
    return layer


def vertical_gradient(width: int, height: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    ramp = Image.linear_gradient("L").resize((width, height))
    return Image.composite(Image.new("RGB", (width, height), bottom), Image.new("RGB", (width, height), top), ramp)
