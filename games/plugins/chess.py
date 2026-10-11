from html import escape

from core import texts
from core.textutils import fa_num
from games.chess.engine import Move, Position, square_name
from games.chess.render import render_board
from games.engine.base import BaseGame, IncomingCallback
from games.engine.registry import register_game

BLANK = "⠀"  # کاراکتر نامرئی برای دکمه‌های خالی


@register_game
class ChessGame(BaseGame):
    """شطرنج دونفره در گروه. صفحه به‌صورت تصویر نمایش داده می‌شود و یک کیبورد ۸×۸ هم‌تراز
    با تصویر برای انتخاب مهره و مقصد زیر آن است. ارتقای پیاده خودکار به وزیر است."""

    key = "chess"
    title_fa = "شطرنج"
    emoji = "♟"
    description_fa = "شطرنج دونفره با صفحه‌ی تصویری و تایمر هر حرکت؛ مات کن تا ببری."
    min_players = 2
    max_players = 2
    players_ceiling = 2
    move_seconds = 90
    max_plies = 300

    async def start(self) -> None:
        order = list(self.players)
        self.ctx.rng.shuffle(order)
        self.white, self.black = order
        self.position = Position.initial()
        self.selected: int | None = None
        self.last_move: Move | None = None
        self.history: dict[tuple, int] = {self.position.key(): 1}
        self.draw_offer: int | None = None
        self.plies = 0
        self.result_line = ""
        self.message_id = await self.ctx.send_photo(self._image(), self._caption(), self._buttons())
        self.ctx.set_timer("move", self.move_seconds, self._timeout)

    async def next_round(self) -> None:
        return None

    # ------------------------------------------------------------------ نمایش
    def _player(self, color: str):
        return self.white if color == "w" else self.black

    @property
    def current(self):
        return self._player(self.position.turn)

    def _targets(self) -> tuple[int, ...]:
        if self.selected is None:
            return ()
        return tuple(sorted({m.dst for m in self.position.moves_from(self.selected)}))

    def _image(self) -> bytes:
        return render_board(self.position, self.last_move, self.selected, self._targets())

    def _caption(self) -> str:
        if self.finished:
            status = self.result_line
        else:
            color = texts.CHESS_WHITE if self.position.turn == "w" else texts.CHESS_BLACK
            status = texts.CHESS_TURN.format(
                name=escape(self.current.name), color=color, seconds=fa_num(self.move_seconds)
            )
            if self.position.in_check():
                status += texts.CHESS_CHECK
        last = ""
        if self.last_move is not None:
            last = texts.CHESS_LAST.format(move=f"{square_name(self.last_move.src)} → {square_name(self.last_move.dst)}")
        if not self.finished:
            if self.draw_offer is not None:
                last += texts.CHESS_DRAW_OFFER.format(name=escape(self.by_id[self.draw_offer].name))
            elif self.plies == 0:
                last += texts.CHESS_HINT
        return texts.CHESS_CAPTION.format(
            white=escape(self.white.name), black=escape(self.black.name), status=status, last=last
        )

    def _buttons(self):
        if self.finished:
            return None
        targets = set(self._targets())
        rows = []
        for rank in range(7, -1, -1):
            row = []
            for file in range(8):
                index = rank * 8 + file
                if index == self.selected:
                    label = "◉"
                elif index in targets:
                    label = "✕" if self.position.board[index] != "." else "•"
                else:
                    label = BLANK
                row.append((label, f"q:{index}"))
            rows.append(row)
        rows.append([(texts.CHESS_RESIGN_BTN, "resign"), (texts.CHESS_DRAW_BTN, "draw")])
        return rows

    async def _refresh(self) -> None:
        await self.ctx.edit_photo(self.message_id, self._image(), self._caption(), self._buttons())

    # ------------------------------------------------------------------ ورودی
    async def on_callback(self, cb: IncomingCallback) -> None:
        if self.finished:
            await cb.reply()
            return
        if cb.player is None:
            await cb.reply(texts.NOT_A_PLAYER, alert=True)
            return
        uid = cb.player.user_id
        if cb.data == "resign":
            winner = self.black if uid == self.white.user_id else self.white
            await cb.reply()
            await self._end(texts.CHESS_END_RESIGN.format(loser=escape(cb.player.name), winner=winner.mention), winner)
            return
        if cb.data == "draw":
            if self.draw_offer is not None and self.draw_offer != uid:
                await cb.reply()
                await self._end(texts.CHESS_END_DRAW.format(reason=texts.CHESS_DRAW_REASONS["agreed"]))
                return
            self.draw_offer = uid
            await cb.reply(texts.CHESS_DRAW_SENT)
            await self._refresh()
            return
        if not cb.data.startswith("q:") or not cb.data[2:].isdigit():
            await cb.reply()
            return
        if uid != self.current.user_id:
            await cb.reply(texts.NOT_YOUR_TURN)
            return
        square = int(cb.data[2:])
        if not 0 <= square < 64:
            return
        if self.selected is not None and square in self._targets():
            await cb.reply()
            await self._move(square)
            return
        piece = self.position.board[square]
        own = piece != "." and (piece.isupper() == (self.position.turn == "w"))
        if not own:
            self.selected = None
            await cb.reply(texts.CHESS_PICK_OWN)
            await self._refresh()
            return
        if not self.position.moves_from(square):
            await cb.reply(texts.CHESS_NO_MOVES)
            return
        self.selected = None if square == self.selected else square
        await cb.reply()
        await self._refresh()

    async def _move(self, destination: int) -> None:
        candidates = [m for m in self.position.moves_from(self.selected) if m.dst == destination]
        # ارتقای خودکار به وزیر
        move = next((m for m in candidates if m.promo.upper() in ("", "Q")), candidates[0])
        mover = self.current
        self.position = self.position.push(move)
        self.last_move = move
        self.selected = None
        self.plies += 1
        if self.draw_offer is not None and self.draw_offer != mover.user_id:
            self.draw_offer = None  # حرکت به‌جای قبول، یعنی رد پیشنهاد
        key = self.position.key()
        self.history[key] = self.history.get(key, 0) + 1

        outcome = self.position.outcome()
        if outcome == "checkmate":
            await self._end(texts.CHESS_END_MATE.format(name=mover.mention), mover)
            return
        reason = outcome
        if reason is None and self.history[key] >= 3:
            reason = "repetition"
        if reason is None and self.plies >= self.max_plies:
            reason = "limit"
        if reason is not None:
            await self._end(texts.CHESS_END_DRAW.format(reason=texts.CHESS_DRAW_REASONS[reason]))
            return
        await self._refresh()
        self.ctx.set_timer("move", self.move_seconds, self._timeout)

    async def _timeout(self) -> None:
        if self.finished:
            return
        loser = self.current
        winner = self._player("b" if self.position.turn == "w" else "w")
        await self._end(texts.CHESS_END_TIMEOUT.format(loser=escape(loser.name), winner=winner.mention), winner)

    async def _end(self, line: str, winner=None) -> None:
        self.finished = True
        self.selected = None
        self.result_line = line
        self.ctx.cancel_timer("move")
        if winner is not None:
            self.add_score(winner.user_id, 1)
        await self._refresh()
        await self.ctx.end_game()
