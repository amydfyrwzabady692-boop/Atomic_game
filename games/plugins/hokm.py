"""حکم چهارنفره (دو تیم دونفره) — فقط روی میز گرافیکی مینی‌اپ.

منطق کامل بازی در ``games.hokm.live`` است و ربات آن را مثل شطرنج و پوکر زنده اجرا می‌کند (``bot.runner``: صفحه‌ی
بازی در مینی‌اپ و یک پیام وضعیت در گروه). این کلاس فقط مشخصات بازی را برای منو، لابی و راهنما نگه می‌دارد. بازی
دقیقاً ۴ نفر لازم دارد؛ اگر لابی با کمتر از ۴ نفر بسته شود، مسابقه لغو و ورودی همه برگردانده می‌شود.
"""

from core import texts
from games.engine.base import BaseGame
from games.engine.payout import Standing
from games.engine.registry import register_game
from games.hokm import live as engine


@register_game
class HokmGame(BaseGame):
    key = "hokm"
    title_fa = "حکم"
    emoji = "♠️"
    description_fa = (
        "حکم چهارنفره‌ی ایرانی در دو تیم دونفره (یارها روبه‌روی هم) روی میز کارت مینی‌اپ: اولین آس حاکم را معلوم "
        "می‌کند، حاکم از روی ۵ کارت اول خال حکم را می‌گوید، باید از خال زمین بازی کرد و تیمی که زودتر ۷ دست ببرد "
        "دور را می‌برد (کُت ۲ و حاکم‌کُت ۳ امتیاز). تیم برنده کل جایزه را نصف‌نصف می‌برد."
    )
    min_players = 4
    max_players = 4
    players_floor = 4
    players_ceiling = 4
    move_seconds = engine.MOVE_SECONDS
    miniapp_only = True
    variant_title_fa = "طول بازی"
    variants = {"7": "۷ امتیازی (کامل)", "5": "۵ امتیازی", "3": "۳ امتیازی (سریع)"}
    rules_fa = [
        "۴ نفر، دو تیم؛ یارت روبه‌روست. حاکم از ۵ کارت اول حکم را می‌گوید.",
        "از خال زمین بده؛ نداری، حکم بزن یا هر کارتی. هر نوبت {move_seconds} ثانیه.",
        "۷ دست زودتر یعنی برد دور؛ کُت ۲ و حاکم‌کُت ۳ امتیاز.",
    ]
    play_style = "turns"
    style_fa = "نوبتی: دقیقاً ۴ نفر در دو تیم، هر کارت {move_seconds} ثانیه، روی میز مینی‌اپ."

    async def start(self) -> None:
        # ربات حکم را همیشه روی مینی‌اپ اجرا می‌کند؛ اگر مینی‌اپ نباشد مسابقه پیش از شروع لغو می‌شود
        await self.ctx.send(texts.HOKM_NEEDS_MINIAPP)
        await self.ctx.end_game()

    async def next_round(self) -> None:
        return None

    async def finish(self) -> list[Standing]:
        self.finished = True
        return [Standing(p.user_id, 0, None) for p in self.players]
