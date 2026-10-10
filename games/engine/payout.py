"""رتبه‌بندی و تقسیم pot. توابع خالص و بدون دیتابیس تا راحت تست شوند."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Standing:
    user_id: int
    score: int
    # لحظه‌ی رسیدن به این امتیاز (کوچک‌تر = زودتر). None یعنی نامشخص.
    reached_at: float | None = None


def rank_standings(standings: list[Standing]) -> list[list[Standing]]:
    """بازیکن‌ها را به گروه‌های هم‌رتبه (به ترتیب رتبه) تبدیل می‌کند.

    امتیاز بیشتر بالاتر است. در امتیاز برابر، کسی که زودتر به آن رسیده برنده است.
    اگر زمان هم برابر (یا نامشخص) بود، در یک گروه مساوی قرار می‌گیرند.
    """
    inf = float("inf")

    def key(s: Standing):
        return (-s.score, s.reached_at if s.reached_at is not None else inf)

    groups: list[list[Standing]] = []
    last_key = None
    for s in sorted(standings, key=key):
        k = key(s)
        if groups and k == last_key:
            groups[-1].append(s)
        else:
            groups.append([s])
            last_key = k
    return groups


def compute_payouts(pot: int, split: list[int], groups: list[list[int]]) -> dict[int, int]:
    """pot را بین بازیکن‌ها تقسیم می‌کند. ``groups`` لیست گروه‌های هم‌رتبه به ترتیب رتبه است.

    - اگر تعداد بازیکن کمتر از تعداد سهم‌ها باشد، سهم‌های اضافه به نسبت بین رتبه‌های
      موجود پخش می‌شود (مثلاً ۶۰-۳۰-۱۰ با دو بازیکن می‌شود ۶۰:۳۰ از کل pot).
    - بازیکن‌های مساوی، مجموع سهم جایگاه‌هایی که اشغال کرده‌اند را مساوی تقسیم می‌کنند.
    - همه‌ی تقسیم‌ها رو به پایین گرد می‌شوند و باقیمانده به نفر اول می‌رسد؛
      بنابراین جمع پرداختی همیشه دقیقاً برابر pot است.
    """
    players = [uid for group in groups for uid in group]
    payouts = dict.fromkeys(players, 0)
    if not players or pot <= 0:
        return payouts
    weights = [w for w in split[: len(players)] if w > 0] or [1]
    total_weight = sum(weights)
    position_amounts = [pot * w // total_weight for w in weights]
    position_amounts += [0] * (len(players) - len(position_amounts))

    position = 0
    for group in groups:
        group_total = sum(position_amounts[position : position + len(group)])
        each = group_total // len(group)
        for uid in group:
            payouts[uid] = each
        position += len(group)

    payouts[players[0]] += pot - sum(payouts.values())
    return payouts
