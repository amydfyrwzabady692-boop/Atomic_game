from core import texts
from core.textutils import fa_num, fold_alef, normalize_fa
from games.engine.base import BaseGame, IncomingMessage
from games.engine.registry import register_game

FALLBACK_LETTERS = "بمسکردنتپاشگخ"


@register_game
class WordChainGame(BaseGame):
    key = "word_chain"
    title_fa = "زنجیره‌ی کلمات"
    emoji = "🔗"
    description_fa = "نوبتی کلمه‌ای بگو که با حرف آخر کلمه‌ی قبلی شروع شود. هر کس جا بماند حذف می‌شود."
    min_players = 2
    max_players = 10
    players_ceiling = 20
    start_seconds = 20
    style_fa = "نوبتی با حذف: مهلت هر نوبت از {start_seconds} ثانیه شروع و کم‌کم تا {min_seconds} ثانیه کوتاه می‌شود."
    rules_fa = [
        "به‌نوبت کلمه‌ای بگو که با حرف آخر کلمه‌ی قبلی شروع شود.",
        "کلمه‌ی تکراری یا خارج از فهرست کلمات قبول نیست.",
        "اگر در مهلت جواب ندهی حذف می‌شوی؛ آخرین نفر برنده است.",
    ]
    min_seconds = 8
    max_turns = 80

    async def start(self) -> None:
        self.order = list(self.players)
        self.ctx.rng.shuffle(self.order)
        self.alive = list(self.order)
        self.eliminated: list[int] = []
        self.used: set[str] = set()
        self.turn_index = 0
        self.turns = 0
        self.turn_seconds = self.start_seconds
        self.warned: set[str] = set()
        first = (await self.ctx.content.random_words(1, 3, 6))[0]
        self.used.add(first)
        await self.ctx.send(texts.CHAIN_START.format(order=" ← ".join(p.name for p in self.order)))
        self.letter, note = await self._next_letter(first)
        await self._announce(texts.CHAIN_FIRST_WORD.format(word=first) + note)

    async def next_round(self) -> None:  # این بازی راند ندارد
        return None

    @property
    def current(self):
        return self.alive[self.turn_index % len(self.alive)]

    async def _next_letter(self, word: str) -> tuple[str, str]:
        """حرف آخر کلمه؛ اگر کلمه‌ی استفاده‌نشده‌ای با آن نمانده باشد، حرف تازه‌ای انتخاب می‌شود."""
        letter = word[-1]
        if await self.ctx.content.has_word_starting_with(letter, self.used):
            return letter, ""
        candidates = list(FALLBACK_LETTERS)
        self.ctx.rng.shuffle(candidates)
        for candidate in candidates:
            if candidate != letter and await self.ctx.content.has_word_starting_with(candidate, self.used):
                return candidate, texts.CHAIN_NEW_LETTER.format(old=letter)
        return letter, ""

    async def _announce(self, prefix: str = "") -> None:
        self.warned = set()
        await self.ctx.send(
            texts.CHAIN_TURN.format(
                prev=prefix, name=self.current.mention, letter=self.letter, seconds=fa_num(self.turn_seconds)
            )
        )
        self.ctx.set_timer("turn", self.turn_seconds, self._timeout)

    async def _warn(self, kind: str, text: str) -> None:
        # در هر نوبت از هر نوع هشدار فقط یک بار، تا گروه شلوغ نشود
        if kind not in self.warned:
            self.warned.add(kind)
            await self.ctx.flash(text)

    async def on_message(self, msg: IncomingMessage) -> None:
        if self.finished or msg.player.user_id != self.current.user_id:
            return
        word = normalize_fa(msg.text, keep_spaces=False)
        if len(word) < 2 or len(word) > 20 or " " in msg.text.strip():
            return
        name = msg.player.name
        if not fold_alef(word).startswith(fold_alef(self.letter)):
            await self._warn("letter", texts.CHAIN_WRONG_LETTER.format(name=name, letter=self.letter))
            return
        if word in self.used:
            await self._warn("used", texts.CHAIN_USED.format(name=name, word=word))
            return
        if not await self.ctx.content.is_valid_word(word):
            await self._warn("invalid", texts.CHAIN_INVALID.format(name=name, word=word))
            return

        self.used.add(word)
        self.turns += 1
        prefix = texts.CHAIN_ACCEPTED.format(name=name, word=word)
        if self.turns >= self.max_turns:
            await self._finish_with_survivors(prefix + texts.CHAIN_LIMIT)
            return
        self.letter, note = await self._next_letter(word)
        self.turn_index = (self.turn_index + 1) % len(self.alive)
        self.turn_seconds = max(self.min_seconds, self.turn_seconds - 1)
        await self._announce(prefix + note)

    async def _timeout(self) -> None:
        if self.finished:
            return
        loser = self.current
        self.alive.remove(loser)
        self.eliminated.append(loser.user_id)
        prefix = texts.CHAIN_ELIMINATED.format(name=loser.name)
        if len(self.alive) <= 1:
            await self._finish_with_survivors(prefix + texts.CHAIN_WINNER.format(name=self.alive[0].mention))
            return
        self.turn_index %= len(self.alive)
        await self._announce(prefix)

    async def _finish_with_survivors(self, text: str) -> None:
        self.ctx.cancel_timer("turn")
        # ترتیب حذف رتبه‌ها را می‌سازد: اولین حذف‌شده کمترین امتیاز، بازمانده(ها) بیشترین
        self.scores = {uid: index + 1 for index, uid in enumerate(self.eliminated)}
        self.reached_at = {}
        for player in self.alive:
            self.scores[player.user_id] = len(self.players)
        self.finished = True
        await self.ctx.send(text)
        await self.ctx.end_game()
