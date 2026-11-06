"""انفجار (Crash) — ۲ تا ۱۰ نفر، فقط روی صفحه‌ی مینی‌اپ. منطق بازی در ``games.crash.live`` است و ربات آن را مثل حکم و
پوکر زنده اجرا می‌کند؛ این کلاس فقط مشخصات بازی را برای منو، لابی و راهنما نگه می‌دارد. درصد کمی از pot سهم سرویس است
(``CRASH_HOUSE_PERCENT``) و بقیه طبق رتبه بین بازیکن‌ها تقسیم می‌شود."""

from core import texts
from games.engine.base import BaseGame
from games.engine.payout import Standing
from games.engine.registry import register_game


@register_game
class CrashGame(BaseGame):
    key = "crash"
    title_fa = "انفجار"
    emoji = "💥"
    description_fa = (
        "ضریب از ۱٫۰۰× بالا می‌رود و هر لحظه ممکن است منفجر شود. قبل از انفجار «برداشت» بزن تا ضریب همان لحظه امتیازت "
        "شود؛ دیر کنی، آن دور صفر می‌گیری. جمع ضریب‌های همه‌ی دورها رتبه را معلوم می‌کند و جایزه طبق تقسیم لابی (پس از کسر "
        "سهم کم سرویس) به بالاترین‌ها می‌رسد."
    )
    min_players = 2
    max_players = 10
    players_floor = 2
    players_ceiling = 10
    miniapp_only = True
    variant_title_fa = "تعداد دور"
    variants = {"3": "۳ دور", "1": "یک دور (سریع)", "5": "۵ دور"}
    rules_fa = [
        "ضریب از ۱٫۰۰× بالا می‌رود و ناگهان منفجر می‌شود.",
        "قبل از انفجار «برداشت» بزن؛ دیر کنی آن دور صفر.",
        "جمع ضریب همه‌ی دورها برنده را معلوم می‌کند.",
    ]
    play_style = "rounds"
    style_fa = "دوری: همه هم‌زمان، هر دور چند ثانیه، روی صفحه‌ی مینی‌اپ."

    async def start(self) -> None:
        await self.ctx.send(texts.CRASH_NEEDS_MINIAPP)
        await self.ctx.end_game()

    async def next_round(self) -> None:
        return None

    async def finish(self) -> list[Standing]:
        self.finished = True
        return [Standing(p.user_id, 0, None) for p in self.players]
