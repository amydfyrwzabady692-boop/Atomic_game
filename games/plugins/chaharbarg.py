"""چهاربرگ (پاسور) — ۲ تا ۴ نفر، فقط روی میز کارت مینی‌اپ. منطق بازی در ``games.chaharbarg.live`` است و ربات آن را مثل
پوکر و حکم زنده اجرا می‌کند؛ این کلاس فقط مشخصات بازی را برای منو، لابی و راهنما نگه می‌دارد."""

from core import texts
from games.chaharbarg import live as engine
from games.engine.base import BaseGame
from games.engine.payout import Standing
from games.engine.registry import register_game


@register_game
class ChaharBargGame(BaseGame):
    key = "chaharbarg"
    title_fa = "چهاربرگ"
    emoji = "🀄"
    description_fa = (
        "چهاربرگ (پاسور) روی میز کارت مینی‌اپ، ۲ تا ۴ نفر. با هر کارت، کارت‌هایی از زمین را بردار که جمعشان با آن ۱۱ شود؛ "
        "سرباز همه‌ی زمین جز شاه و بی‌بی را جمع می‌کند و شاه شاه و بی‌بی بی‌بی را. سور ۵، بیشترین گشنیز ۷، ده خشت ۳، دو "
        "گشنیز ۲ و هر آس و سرباز ۱ امتیاز."
    )
    min_players = 2
    max_players = 4
    players_floor = 2
    players_ceiling = 4
    move_seconds = engine.MOVE_SECONDS
    miniapp_only = True
    variant_title_fa = "طول بازی"
    variants = {"0": "یک دست کامل", "31": "تا ۳۱ امتیاز", "62": "تا ۶۲ امتیاز (کامل)"}
    rules_fa = [
        "کارت بازی کن و از زمین بردار تا جمع ۱۱ شود؛ سرباز همه جز شاه و بی‌بی را می‌برد.",
        "زمین را خالی کنی سور است (۵). بیشترین گشنیز ۷، ده خشت ۳، دو گشنیز ۲.",
        "هر آس و سرباز ۱ امتیاز؛ هر نوبت {move_seconds} ثانیه.",
    ]
    play_style = "turns"
    style_fa = "نوبتی: ۲ تا ۴ نفر، هر کارت {move_seconds} ثانیه، روی میز مینی‌اپ."

    async def start(self) -> None:
        await self.ctx.send(texts.HOKM_NEEDS_MINIAPP.replace("حکم", "چهاربرگ"))
        await self.ctx.end_game()

    async def next_round(self) -> None:
        return None

    async def finish(self) -> list[Standing]:
        self.finished = True
        return [Standing(p.user_id, 0, None) for p in self.players]
