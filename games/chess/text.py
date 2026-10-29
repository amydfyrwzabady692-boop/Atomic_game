"""متن کپشن صفحه‌ی شطرنج در گروه؛ مشترک بین شطرنج مینی‌اپ و شطرنج داخل گفت‌وگو."""

from core import texts
from core.textutils import fa_clock, fa_digits

FIGURINES = str.maketrans({"K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘"})
LTR = "‎"  # نشانه‌ی چپ‌به‌راست: نماد حرکت وسط متن فارسی به‌هم نمی‌ریزد


def notation(san: str, ply: int) -> str:
    """حرکت به نماد جبری با شکل مهره و شماره‌ی حرکت: «۱۲. ♘f3» برای سفید و «۱۲… ♘f6» برای سیاه."""
    number = fa_digits(ply // 2 + 1)
    return f"{LTR}{number}{'.' if ply % 2 == 0 else '…'} {san.translate(FIGURINES)}"


def caption(white: str, black: str, control: str | None, clocks: dict | None, status: str, last: str) -> str:
    """``white`` و ``black`` نام‌های escape‌شده‌اند و ``clocks`` ثانیه‌ی باقی‌مانده‌ی هر طرف (یا ``None``)."""
    label = texts.CHESS_CONTROLS.get(control or "")

    def clock(side: str) -> str:
        return texts.CHESS_CAPTION_CLOCK.format(time=fa_clock(clocks[side])) if clocks else ""

    return texts.CHESS_CAPTION.format(
        control=texts.CHESS_CAPTION_CONTROL.format(label=label) if label else "",
        white=white,
        black=black,
        white_clock=clock("w"),
        black_clock=clock("b"),
        status=status,
        last=last,
    )
