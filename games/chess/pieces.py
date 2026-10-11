"""مهره‌های شطرنج به سبک استانتون، کاملاً رویه‌ای (بدون فونت یا فایل تصویر).

هر مهره یک نیم‌رخ برداری است که با بزرگ‌نمایی چندبرابر کشیده، با نور از بالا-چپ حجم‌دار و بعد کوچک
می‌شود. سایه‌روشن از «برجسته‌سازی» نسخه‌ی محوِ خود نیم‌رخ به دست می‌آید؛ پس به numpy یا محاسبه‌ی
پیکسل‌به‌پیکسل نیازی نیست و ساخت هر ۱۲ مهره کسری از ثانیه طول می‌کشد (و فقط یک بار انجام می‌شود).

دستگاه مختصات طراحی ۱۰۰×۱۰۰ است: محور وسط x=۵۰ و کف مهره y=۹۰.
"""

from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

SUPERSAMPLE = 4
CX = 50.0
FLOOR = 90.0

# (سایه، رنگ میانی، روشن، خط دور)
IVORY = ((120, 86, 52), (238, 222, 190), (255, 253, 244), (58, 38, 22))
EBONY = ((4, 3, 4), (54, 43, 41), (164, 146, 136), (0, 0, 0))


def chaikin(points, rounds: int = 2, closed: bool = False):
    """گوشه‌های چندخطی را گرد می‌کند (هر دور هر پاره‌خط را در ¼ و ¾ می‌بُرد)."""
    for _ in range(rounds):
        out = []
        count = len(points)
        last = count if closed else count - 1
        if not closed:
            out.append(points[0])
        for i in range(last):
            (x0, y0), (x1, y1) = points[i], points[(i + 1) % count]
            out.append((x0 * 0.75 + x1 * 0.25, y0 * 0.75 + y1 * 0.25))
            out.append((x0 * 0.25 + x1 * 0.75, y0 * 0.25 + y1 * 0.75))
        if not closed:
            out.append(points[-1])
        points = out
    return points


def lathe(profile, rounds: int = 2):
    """نیم‌رخ یک جسم تراش‌خورده: ``profile`` فهرست (y، نصف پهنا) از بالا به پایین است."""
    smooth = chaikin([(half, y) for y, half in profile], rounds)
    left = [(CX - half, y) for half, y in smooth]
    right = [(CX + half, y) for half, y in reversed(smooth)]
    return left + right


def base(width: float, top: float):
    """پایه‌ی مشترک مهره‌ها که از ``top`` با پهنای ساقه شروع می‌شود و تا کف پهن می‌شود."""
    return lathe(
        [
            (top, width * 0.58),
            (top + 2.2, width * 0.8),
            (top + 4.2, width * 0.84),
            (top + 5.4, width * 0.93),
            (top + 8.6, width * 0.97),
            (top + 10.0, width * 1.04),
            (FLOOR - 1.2, width * 1.04),
            (FLOOR, width * 1.0),
        ],
        rounds=1,
    )


class Shape:
    """ماسک مهره در اندازه‌ی بزرگ؛ همه‌ی مختصات در دستگاه ۱۰۰×۱۰۰ داده می‌شوند."""

    def __init__(self, size: int):
        self.size = size
        self.k = size / 100.0
        self.mask = Image.new("L", (size, size), 0)
        self.draw = ImageDraw.Draw(self.mask)
        self.details: list = []  # خط‌های تیره‌ی روی مهره: (نقاط، پهنا)
        self.sparkles: list = []  # نقطه‌های براق: (x، y، شعاع)
        self.grooves: list = []  # شیارهای دور بدنه: (y، نصف پهنا، ضخامت)

    def _pts(self, points):
        return [(x * self.k, y * self.k) for x, y in points]

    def poly(self, points, fill: int = 255):
        self.draw.polygon(self._pts(points), fill=fill)

    def circle(self, x: float, y: float, r: float, fill: int = 255):
        k = self.k
        self.draw.ellipse([(x - r) * k, (y - r) * k, (x + r) * k, (y + r) * k], fill=fill)

    def ellipse(self, x: float, y: float, rx: float, ry: float, fill: int = 255):
        k = self.k
        self.draw.ellipse([(x - rx) * k, (y - ry) * k, (x + rx) * k, (y + ry) * k], fill=fill)

    def rect(self, x0: float, y0: float, x1: float, y1: float, fill: int = 255, radius: float = 0):
        k = self.k
        box = [x0 * k, y0 * k, x1 * k, y1 * k]
        if radius:
            self.draw.rounded_rectangle(box, radius=radius * k, fill=fill)
        else:
            self.draw.rectangle(box, fill=fill)

    def line(self, points, width: float = 1.0):
        self.details.append((points, width))

    def sparkle(self, x: float, y: float, r: float):
        self.sparkles.append((x, y, r))

    def groove(self, y: float, half: float, width: float = 0.9):
        """شیار دور بدنه؛ چون از روبه‌رو دیده می‌شود کمی قوس رو به پایین دارد."""
        self.grooves.append((y, half, width))

    def collar(self, y: float, width: float, thickness: float = 2.6):
        """طوق برجسته‌ی دور گردن مهره."""
        self.ellipse(CX, y, width, thickness)


# ---------------------------------------------------------------------- نیم‌رخ هر مهره
def pawn(s: Shape):
    s.poly(base(22.5, 78.5))
    s.poly(lathe([(60, 6.2), (65, 7.8), (71, 11.2), (76, 15.4), (79, 17.6)]))
    s.collar(60.2, 12.2, 2.9)
    s.circle(CX, 48.6, 12.2)


def rook(s: Shape):
    s.poly(base(25.5, 77.5))
    s.poly(lathe([(47, 16.2), (50.5, 14.0), (62, 14.4), (72, 15.8), (78, 18.6)], rounds=1))
    s.collar(48.6, 17.8, 2.7)
    # برجک دندانه‌دار
    s.rect(30.5, 33.0, 69.5, 47.5, radius=1.4)
    s.rect(38.6, 32.0, 44.4, 38.6, fill=0)
    s.rect(55.6, 32.0, 61.4, 38.6, fill=0)
    s.groove(42.6, 18.6)
    s.groove(60.0, 14.0)


def bishop(s: Shape):
    s.poly(base(25.5, 77.5))
    s.poly(lathe([(56, 6.6), (62, 7.4), (69, 10.4), (74.5, 14.6), (78.5, 17.6)]))
    s.collar(56.4, 13.0, 2.8)
    s.collar(52.4, 9.2, 2.2)
    # کلاه اسقف (قطره‌ای) و گوی نوک آن
    s.poly(lathe([(27.5, 1.4), (32.0, 6.4), (37.5, 10.6), (43.0, 12.4), (47.5, 11.4), (51.5, 8.0), (53.5, 6.2)]))
    s.circle(CX, 25.2, 3.7)
    s.line([(54.8, 31.4), (46.0, 42.0)], 1.8)


def queen(s: Shape):
    s.poly(base(27.0, 77.0))
    s.poly(lathe([(50, 7.0), (57, 7.6), (66, 10.4), (72.5, 15.0), (78, 18.8)]))
    s.collar(50.4, 13.8, 2.9)
    s.collar(46.4, 10.2, 2.2)
    # سر و تاج پنج‌شاخه با گوی روی هر شاخه
    s.poly(lathe([(33.5, 14.2), (37.5, 15.0), (41.5, 12.6), (45.0, 9.8), (47.2, 8.6)]))
    s.poly([
        (35.6, 36.6), (32.0, 22.6), (39.6, 29.4), (41.6, 18.8), (46.4, 28.2), (50.0, 17.4),
        (53.6, 28.2), (58.4, 18.8), (60.4, 29.4), (68.0, 22.6), (64.4, 36.6),
    ])
    for x, y in [(32.0, 22.0), (41.6, 18.2), (50.0, 16.6), (58.4, 18.2), (68.0, 22.0)]:
        s.circle(x, y, 2.7)
        s.sparkle(x - 0.8, y - 0.8, 0.8)
    s.groove(34.4, 13.6)


def king(s: Shape):
    s.poly(base(27.5, 77.0))
    s.poly(lathe([(48, 7.4), (56, 8.0), (65, 10.8), (72, 15.4), (78, 19.2)]))
    s.collar(48.6, 14.4, 3.0)
    s.collar(44.4, 10.6, 2.2)
    # تاج پهن و صلیب
    s.poly(lathe([(22.0, 10.4), (24.0, 14.0), (28.5, 15.2), (34.5, 13.6), (40.0, 11.0), (45.0, 9.0)]))
    s.ellipse(CX, 22.6, 11.4, 2.6)
    s.rect(47.6, 6.4, 52.4, 22.4, radius=1.0)
    s.rect(42.8, 10.4, 57.2, 15.0, radius=1.0)
    s.groove(31.4, 14.4)


def _horse(points, widen: float = 1.24, shift: float = -1.6):
    """سر اسب کمی پهن‌تر و جلوتر تا با پایه‌ی پهن هماهنگ شود."""
    return [(CX + (x - CX) * widen + shift, y) for x, y in points]


def knight(s: Shape):
    s.poly(base(26.5, 77.5))
    head = [
        (37.0, 79.0), (38.4, 69.0), (42.4, 60.0), (45.6, 53.0), (42.6, 50.6), (37.0, 53.6), (31.6, 55.0),
        (27.6, 52.4), (26.8, 47.6), (29.4, 42.0), (33.6, 36.4), (37.6, 30.6), (40.6, 26.6),
        (41.6, 20.0), (45.6, 25.0), (48.6, 19.4), (52.4, 26.0), (58.0, 30.4), (63.4, 37.6),
        (66.6, 47.0), (67.8, 58.0), (67.0, 69.0), (65.6, 79.0),
    ]
    s.poly(chaikin(_horse(head), rounds=2, closed=True))
    # گوش‌ها تیز بمانند
    s.poly(_horse([(40.4, 28.0), (41.6, 18.6), (45.4, 26.4)]))
    s.poly(_horse([(46.0, 26.6), (48.8, 17.8), (52.2, 27.4)]))
    (ex, ey), (nx, ny) = _horse([(37.4, 40.2), (29.8, 48.8)])
    s.circle(ex, ey, 1.7, fill=0)  # چشم
    s.circle(nx, ny, 1.0, fill=0)  # سوراخ بینی
    s.line(_horse([(28.2, 52.4), (33.4, 51.0)]), 0.9)  # دهان
    s.line(_horse([(40.0, 46.4), (44.0, 50.2), (45.2, 54.4)]), 1.0)  # خط فک
    # یال
    for step in range(5):
        t = step * 4.6
        s.line(_horse([(54.6 + t * 0.52, 31.0 + t * 1.5), (59.6 + t * 0.4, 34.6 + t * 1.86)]), 1.0)


BUILDERS = {"P": pawn, "R": rook, "N": knight, "B": bishop, "Q": queen, "K": king}


# ---------------------------------------------------------------------- نور و متریال
def _emboss(height: Image.Image, distance: int, gain: float) -> Image.Image:
    """نور از بالا-چپ: جایی که سطح به سمت نور شیب دارد روشن‌تر از ۱۲۸ می‌شود."""
    ahead = ImageChops.offset(height, -distance, -distance)  # ارتفاع سطح در سمت پایین-راست
    behind = ImageChops.offset(height, distance, distance)
    return ImageChops.subtract(ahead, behind, scale=1.0 / gain, offset=128)


def _render(letter: str, white: bool, size: int) -> Image.Image:
    big = size * SUPERSAMPLE
    shape = Shape(big)
    BUILDERS[letter](shape)
    mask = shape.mask
    shadow, mid, light, outline = IVORY if white else EBONY

    # حجم کلی از نسخه‌ی خیلی محو، لبه‌ها و طوق‌ها از نسخه‌ی کم‌محو
    form = _emboss(mask.filter(ImageFilter.GaussianBlur(big * 0.07)), max(2, big // 40), 1.5)
    edges = _emboss(mask.filter(ImageFilter.GaussianBlur(big * 0.014)), max(1, big // 170), 0.55)
    shade = ImageChops.add(form, edges, scale=1.0, offset=-128)
    # کف مهره کمی تیره‌تر است (نور محیط کمتر)
    falloff = Image.linear_gradient("L").resize((big, big)).point(lambda v: 255 - int(max(0, v - 120) * 0.32))
    shade = ImageChops.multiply(shade, falloff)

    body = ImageOps.colorize(shade, black=shadow, white=light, mid=mid, blackpoint=38, whitepoint=222, midpoint=128)
    body = body.convert("RGBA")

    # برق نور روی برجسته‌ترین بخش‌ها
    gloss = form.point(lambda v: 0 if v < 178 else min(255, (v - 178) * 5))
    gloss = ImageChops.multiply(gloss, mask).filter(ImageFilter.GaussianBlur(big * 0.008))
    glossy = Image.new("RGBA", (big, big), (255, 255, 255, 0))
    glossy.putalpha(gloss.point(lambda v: int(v * (0.5 if white else 0.34))))
    body = Image.alpha_composite(body, glossy)

    draw = ImageDraw.Draw(body)
    k = shape.k
    line_color = outline + (150 if white else 215,)
    for points, width in shape.details:
        draw.line([(x * k, y * k) for x, y in points], fill=line_color, width=max(1, round(width * k)), joint="curve")
    for y, half, width in shape.grooves:
        box = [(CX - half) * k, (y - 2.2) * k, (CX + half) * k, (y + 2.2) * k]
        draw.arc(box, start=8, end=172, fill=line_color, width=max(1, round(width * k)))
    for x, y, r in shape.sparkles:
        draw.ellipse([(x - r) * k, (y - r) * k, (x + r) * k, (y + r) * k], fill=(255, 255, 255, 235))

    # خط دور تیره: ماسک کمی بزرگ‌شده زیر خود مهره
    grow = max(3, round(big * 0.011)) | 1
    rim = mask.filter(ImageFilter.MaxFilter(grow))
    sprite = Image.new("RGBA", (big, big), outline + (0,))
    sprite.putalpha(rim.point(lambda v: int(v * 0.86)))
    body.putalpha(mask)
    sprite = Image.alpha_composite(sprite, body)
    return sprite.resize((size, size), Image.LANCZOS)


@lru_cache(maxsize=32)
def piece_sprite(piece: str, size: int) -> Image.Image:
    """تصویر شفاف یک مهره (حرف بزرگ = سفید) در مربعی به ضلع ``size``."""
    return _render(piece.upper(), piece.isupper(), size)


@lru_cache(maxsize=8)
def shadow_sprite(size: int) -> Image.Image:
    """سایه‌ی نرم مهره روی صفحه."""
    big = size * 2
    layer = Image.new("L", (big, big), 0)
    ImageDraw.Draw(layer).ellipse([big * 0.16, big * 0.72, big * 0.96, big * 0.97], fill=160)
    layer = layer.filter(ImageFilter.GaussianBlur(big * 0.035)).resize((size, size), Image.LANCZOS)
    sprite = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sprite.putalpha(layer)
    return sprite
