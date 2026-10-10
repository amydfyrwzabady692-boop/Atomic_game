"""ابزارهای متن فارسی: نرمال‌سازی ورودی و قالب‌بندی اعداد."""

import re

_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"

_CHAR_MAP = {
    "ي": "ی",
    "ى": "ی",
    "ئ": "ی",
    "ك": "ک",
    "ة": "ه",
    "ۀ": "ه",
    "أ": "ا",
    "إ": "ا",
    "ٱ": "ا",
    "ؤ": "و",
    "‌": " ",  # نیم‌فاصله
    "‍": "",  # ZWJ
    "‎": "",
    "‏": "",
    " ": " ",
    "ـ": "",  # کشیده
}
_CHAR_MAP.update({d: str(i) for i, d in enumerate(_FA_DIGITS)})
_CHAR_MAP.update({d: str(i) for i, d in enumerate(_AR_DIGITS)})
_TRANS = str.maketrans(_CHAR_MAP)

# اعراب و علامت‌های ترکیبی عربی
_DIACRITICS = re.compile(r"[ً-ٰٟۖ-ۭ]")
_SPACES = re.compile(r"\s+")


def normalize_fa(text: str, *, keep_spaces: bool = True) -> str:
    """ورودی فارسی را برای مقایسه یکدست می‌کند.

    ي→ی، ك→ک، حذف اعراب و کشیده، نیم‌فاصله→فاصله، ارقام فارسی/عربی→انگلیسی،
    حذف فاصله‌های اضافه. با ``keep_spaces=False`` همه‌ی فاصله‌ها حذف می‌شوند.
    """
    if not text:
        return ""
    text = _DIACRITICS.sub("", text).translate(_TRANS)
    text = _SPACES.sub(" ", text).strip().lower()
    if not keep_spaces:
        text = text.replace(" ", "")
    return text


def answers_match(given: str, expected: str) -> bool:
    """مقایسه‌ی جواب بدون حساسیت به فاصله/نیم‌فاصله."""
    return normalize_fa(given, keep_spaces=False) == normalize_fa(expected, keep_spaces=False)


def fa_digits(value) -> str:
    return str(value).translate(str.maketrans("0123456789", _FA_DIGITS))


def fa_num(value: int) -> str:
    """عدد با جداکننده‌ی هزارگان و ارقام فارسی: 12500 → ۱۲٬۵۰۰"""
    return fa_digits(f"{int(value):,}").replace(",", "٬")


def parse_int(text: str) -> int | None:
    text = normalize_fa(text, keep_spaces=False).replace(",", "").replace("٬", "")
    if re.fullmatch(r"-?\d{1,12}", text):
        return int(text)
    return None
