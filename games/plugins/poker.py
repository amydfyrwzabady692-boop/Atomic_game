"""پوکر تگزاس هولدم داخل گروه (وقتی مینی‌اپ راه‌اندازی نشده؛ با مینی‌اپ همین بازی روی میز گرافیکی است).

منطق کامل بازی در ``games.poker.live`` است؛ این پلاگین فقط پیام میز و دکمه‌ها را نگه می‌دارد. کارت‌های
هر بازیکن با دکمه‌ی «کارت‌های من» در پنجره‌ی هشداری نشان داده می‌شود که فقط خود او می‌بیند.
"""

from core import texts
from core.textutils import fa_num
from games.chess.live import LiveError
from games.engine.base import DANGER, PRIMARY, SUCCESS, BaseGame, Button, IncomingCallback
from games.engine.payout import Standing
from games.engine.registry import register_game
from games.poker import live as engine
from games.poker.cards import best_hand, hand_name, label


@register_game
class PokerGame(BaseGame):
    key = "poker"
    title_fa = "پوکر"
    emoji = "🃏"
    description_fa = "تگزاس هولدم: هر نفر با ژتون برابر شروع می‌کند؛ ژتون بیشتر در پایان یعنی رتبه‌ی بهتر."
    min_players = 2
    max_players = 6
    players_floor = 2
    players_ceiling = engine.MAX_PLAYERS
    move_seconds = engine.MOVE_SECONDS
    hands = engine.HAND_LIMIT
    start_chips = engine.START_CHIPS
    rules_fa = [
        "هر نفر {start_chips} ژتون؛ حداکثر {hands} دست، بلایندها کم‌کم بالا می‌روند.",
        "فولد، چک، کال، رِیز یا آل‌این؛ هر نوبت {move_seconds} ثانیه.",
        "در پایان، ژتون بیشتر رتبه‌ی بهتر و سهم بیشتری از جایزه است.",
    ]
    play_style = "turns"
    style_fa = "نوبتی: هر حرکت {move_seconds} ثانیه، حداکثر {hands} دست."

    async def start(self) -> None:
        order = list(self.players)
        self.ctx.rng.shuffle(order)
        self.state = engine.new_state([p.user_id for p in order], self.ctx.now(), seed=str(self.ctx.rng.random()))
        self.message_id = await self.ctx.send(self._text(), self._buttons())
        self._arm()

    async def next_round(self) -> None:
        return None

    # ------------------------------------------------------------ نمایش
    def _text(self) -> str:
        from bot.render import poker_text

        return poker_text(self.state, {p.user_id: p.name for p in self.players})

    def _buttons(self):
        state = self.state
        rows = [[Button(texts.POKER_MY_CARDS_BTN, "c", PRIMARY)]]
        if state["over"] or state["phase"] != "betting" or state["to_act"] is None:
            return rows
        legal = engine.legal_actions(state, state["to_act"])
        row = [Button(texts.POKER_FOLD_BTN, "a:fold", DANGER)]
        if legal["check"]:
            row.append(Button(texts.POKER_CHECK_BTN, "a:check", SUCCESS))
        if legal["call"]:
            row.append(Button(texts.POKER_CALL_BTN.format(amount=fa_num(legal["call"])), "a:call", SUCCESS))
        rows.append(row)
        raises = []
        if legal["raise_min"]:
            raises.append(legal["raise_min"])
            double = state["current_bet"] * 2 + state["bb"] * 2
            if legal["raise_min"] < double < legal["raise_max"]:
                raises.append(double)
        row = [Button(texts.POKER_RAISE_BTN.format(amount=fa_num(a)), f"a:raise:{a}", PRIMARY) for a in raises]
        if legal["allin"]:
            row.append(Button(texts.POKER_ALLIN_BTN.format(amount=fa_num(legal["allin"])), "a:allin", DANGER))
        if row:
            rows.append(row)
        return rows

    async def _refresh(self) -> None:
        if self.state["over"]:
            await self._end()
            return
        await self.ctx.edit(self.message_id, self._text(), self._buttons(), urgent=True)
        self._arm()

    # ------------------------------------------------------------ زمان‌بندی
    def _arm(self) -> None:
        deadline = self.state["deadline"]
        if deadline is not None:
            self.ctx.set_timer("poker", max(0.5, deadline - self.ctx.now() + 0.2), self._tick)

    async def _tick(self) -> None:
        if self.finished:
            return
        if engine.check_timeout(self.state, self.ctx.now()):
            await self._refresh()
        else:
            self._arm()

    async def _end(self) -> None:
        if self.finished:
            return
        self.finished = True
        self.ctx.cancel_timer("poker")
        await self.ctx.edit(self.message_id, self._text(), [], urgent=True)
        await self.ctx.end_game()

    # ------------------------------------------------------------ کلیک‌ها
    async def on_callback(self, cb: IncomingCallback) -> None:
        if self.finished:
            return
        if cb.player is None:
            await cb.reply(texts.NOT_A_PLAYER, alert=True)
            return
        seat = engine.seat_of(self.state, cb.player.user_id)
        if cb.data == "c":
            await cb.reply(self._my_cards(seat), alert=True)
            return
        if not cb.data.startswith("a:"):
            return
        parts = cb.data.split(":")
        kind = parts[1]
        amount = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        try:
            engine.act(self.state, cb.player.user_id, kind, amount, self.ctx.now())
        except LiveError as exc:
            await cb.reply(texts.POKER_ERRORS.get(exc.code, texts.ERROR_GENERIC))
            if exc.code == "timeout":
                await self._refresh()
            return
        await self._refresh()

    def _my_cards(self, seat: int | None) -> str:
        state = self.state
        if seat is None or not state["hole"][seat]:
            return texts.POKER_NO_CARDS
        cards = state["hole"][seat]
        best = ""
        if len(cards) + len(state["board"]) >= 5:
            best = "دست تو: " + hand_name(best_hand(cards + state["board"])[0])
        board = " ".join(label(c) for c in state["board"]) or "—"
        return texts.POKER_MY_CARDS.format(cards=" ".join(label(c) for c in cards), board=board, best=best)

    async def finish(self) -> list[Standing]:
        self.finished = True
        now = self.ctx.now()
        return [Standing(uid, score, now if score > 0 else None) for uid, score in engine.standings(self.state)]
