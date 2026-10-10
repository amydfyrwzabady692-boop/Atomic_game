"""mulberry32 — دقیقاً معادل پیاده‌سازی ``static/arcade/common/rng.js``."""

MASK = 0xFFFFFFFF


def imul(a: int, b: int) -> int:
    return (a * b) & MASK


class Mulberry32:
    __slots__ = ("a",)

    def __init__(self, seed: int):
        self.a = seed & MASK

    def next_u32(self) -> int:
        self.a = (self.a + 0x6D2B79F5) & MASK
        a = self.a
        t = imul(a ^ (a >> 15), 1 | a)
        t = ((t + imul(t ^ (t >> 7), 61 | t)) & MASK) ^ t
        return (t ^ (t >> 14)) & MASK

    def int(self, n: int) -> int:
        """عدد صحیح در بازه‌ی [0, n)"""
        return self.next_u32() % n

    def range(self, lo: int, hi: int) -> int:
        """عدد صحیح در بازه‌ی بسته‌ی [lo, hi]"""
        return lo + self.next_u32() % (hi - lo + 1)

    def chance(self, percent: int) -> bool:
        return self.next_u32() % 100 < percent


def idiv(a: int, b: int) -> int:
    """تقسیم صحیح رو به پایین (مثل Math.floor(a / b) در JS)."""
    return a // b
