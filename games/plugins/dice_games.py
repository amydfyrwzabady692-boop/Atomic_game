from html import escape

from core import texts
from core.textutils import fa_num
from games.engine.base import SUCCESS, BaseGame, Button, IncomingCallback
from games.engine.registry import register_game

# variant → (ایموجی تلگرام، تابع تبدیل مقدار دایس به امتیاز)
DICE_KINDS = {
    "dice": ("🎲", lambda v: v),
    "darts": ("🎯", lambda v: v),
    "bowling": ("🎳", lambda v: v),
    "basket": ("🏀", lambda v: 1 if v >= 4 else 0),  # ۴ و ۵ یعنی توپ داخل سبد
    "football": ("⚽", lambda v: 1 if v >= 3 else 0),  # ۳ تا ۵ یعنی گل
}
# بیشترین مقدار دایس هر ایموجی در تلگرام
DICE_MAX = {"🎲": 6, "🎯": 6, "🎳": 6, "🏀": 5, "⚽": 5}


@register_game
class DiceGame(BaseGame):
    """بازی‌های ایموجی تلگرام. فقط خود ربات با ``sendDice`` پرتاب می‌کند؛ دایسی که کاربر
    بفرستد یا فوروارد کند هیچ اثری ندارد چون این بازی اصلاً پیام‌ها را نمی‌خواند."""

    key = "dice_games"
    title_fa = "بازی‌های شانسی"
    emoji = "🎲"
    description_fa = "نوبتی دکمه‌ی «پرتاب» را بزن تا ربات به نام تو پرتاب کند. جمع امتیاز چند پرتاب ملاک است."
    min_players = 2
    max_players = 8
    players_ceiling = 12
    rounds = 3  # تعداد پرتاب هر بازیکن
    rules_fa = [
        "به‌نوبت دکمه‌ی «پرتاب» را بزن؛ ربات به نام تو پرتاب می‌کند.",
        "هر نفر {rounds} پرتاب دارد و جمع امتیازها حساب می‌شود.",
        "اگر تا {turn_seconds} ثانیه نزنی، ربات خودش پرتاب می‌کند.",
    ]
    turn_seconds = 20
    settle_seconds = 4  # صبر برای تمام شدن انیمیشن دایس
    variant_title_fa = "نوع بازی"
    variants = dict(texts.DICE_VARIANTS)

    async def start(self) -> None:
        self.variant = self.ctx.options.get("variant") or "dice"
        self.dice_emoji, self.to_points = DICE_KINDS.get(self.variant, DICE_KINDS["dice"])
        self.order = list(self.players)
        self.ctx.rng.shuffle(self.order)
        self.turn = 0  # شماره‌ی پرتاب کلی
        self.total_turns = len(self.order) * self.total_rounds
        self.waiting = False
        self.message_id = 0
        await self.next_round()

    @property
    def title(self) -> str:
        return self.variants.get(self.variant, self.title_fa)

    @property
    def current(self):
        return self.order[self.turn % len(self.order)]

    def _board(self) -> str:
        return "\n".join(
            texts.DICE_BOARD_LINE.format(name=escape(p.name), score=fa_num(self.scores[p.user_id]))
            for p in self.order
        )

    async def next_round(self) -> None:
        """نوبت بعدی را اعلام می‌کند (روی همان پیام کنترل، تا گروه شلوغ نشود)."""
        if self.turn >= self.total_turns:
            await self.ctx.edit(
                self.message_id,
                texts.DICE_DONE.format(emoji=self.dice_emoji, title=self.title, board=self._board()),
                None,
                urgent=True,
            )
            await self.ctx.end_game()
            return
        self.round_no = self.turn // len(self.order) + 1
        self.waiting = True
        text = texts.DICE_TURN.format(
            emoji=self.dice_emoji,
            title=self.title,
            board=self._board(),
            name=self.current.mention,
            n=fa_num(self.round_no),
            total=fa_num(self.total_rounds),
            seconds=fa_num(self.turn_seconds),
        )
        buttons = [[Button(texts.DICE_THROW_BTN.format(emoji=self.dice_emoji), f"t:{self.turn}", SUCCESS)]]
        if self.message_id:
            await self.ctx.edit(self.message_id, text, buttons, urgent=True)
        else:
            self.message_id = await self.ctx.send(text, buttons)
        self.ctx.set_timer("turn", self.turn_seconds, self._throw)

    async def on_callback(self, cb: IncomingCallback) -> None:
        if cb.player is None:
            await cb.reply(texts.NOT_A_PLAYER, alert=True)
            return
        if not self.waiting or cb.data != f"t:{self.turn}" or cb.player.user_id != self.current.user_id:
            await cb.reply(texts.NOT_YOUR_TURN)
            return
        await cb.reply()
        await self._throw()

    async def _throw(self) -> None:
        """ربات به نام بازیکنِ نوبت پرتاب می‌کند (با کلیک او یا خودکار بعد از پایان مهلت)."""
        if not self.waiting:
            return
        self.waiting = False
        self.ctx.cancel_timer("turn")
        value = await self.ctx.send_dice(self.dice_emoji)
        if not value:
            # تلگرام دایس را نفرستاد (مثلاً محدودیت نرخ): بازیکن نباید صفر بگیرد، پس ربات خودش قرعه می‌کشد
            value = self.ctx.rng.randint(1, DICE_MAX.get(self.dice_emoji, 6))
        self.add_score(self.current.user_id, self.to_points(value))
        self.turn += 1
        self.ctx.set_timer("settle", self.settle_seconds, self.next_round)
