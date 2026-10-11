from html import escape

from core import texts
from core.textutils import fa_num
from games.engine.base import DANGER, PRIMARY, BaseGame, Button, IncomingCallback
from games.engine.registry import register_game

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
MARKS = {"X": "❌", "O": "⭕️"}
MARK_STYLES = {"X": DANGER, "O": PRIMARY}


def winner_of(board: list[str]) -> str | None:
    for a, b, c in LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None


@register_game
class TicTacToeGame(BaseGame):
    key = "tictactoe"
    title_fa = "دوز"
    emoji = "⭕️"
    description_fa = "دوز دونفره با تایمر هر حرکت. اگر وقتت تمام شود می‌بازی."
    min_players = 2
    max_players = 2
    players_ceiling = 2
    move_seconds = 30
    rules_fa = [
        "به‌نوبت یک خانه را بزن؛ سه علامت در یک ردیف، ستون یا قطر یعنی برد.",
        "برای هر حرکت {move_seconds} ثانیه وقت داری؛ تمام شدن وقت یعنی باخت.",
        "اگر صفحه پر شود و کسی نبرد، بازی مساوی است.",
    ]

    async def start(self) -> None:
        order = list(self.players)
        self.ctx.rng.shuffle(order)
        self.x, self.o = order
        self.board = [""] * 9
        self.turn = "X"
        self.message_id = await self.ctx.send(self._text(self._turn_status()), self._buttons())
        self.ctx.set_timer("move", self.move_seconds, self._timeout)

    async def next_round(self) -> None:
        return None

    def _player(self, mark: str):
        return self.x if mark == "X" else self.o

    def _turn_status(self) -> str:
        return texts.XO_TURN.format(
            name=self._player(self.turn).mention, mark=MARKS[self.turn], seconds=fa_num(self.move_seconds)
        )

    def _text(self, status: str) -> str:
        return texts.XO_BOARD.format(x=escape(self.x.name), o=escape(self.o.name), status=status)

    def _buttons(self, active: bool = True):
        rows = []
        for r in range(3):
            row = []
            for c in range(3):
                i = r * 3 + c
                mark = self.board[i]
                row.append(Button(MARKS.get(mark, "▫️"), f"m:{i}" if active else "noop", MARK_STYLES.get(mark, "")))
            rows.append(row)
        return rows

    async def _end(self, status: str, winner=None) -> None:
        self.finished = True
        self.ctx.cancel_timer("move")
        if winner is not None:
            self.add_score(winner.user_id, 1)
        await self.ctx.edit(self.message_id, self._text(status), self._buttons(active=False), urgent=True)
        await self.ctx.end_game()

    async def on_callback(self, cb: IncomingCallback) -> None:
        if self.finished or not cb.data.startswith("m:"):
            return
        if cb.player is None:
            await cb.reply(texts.NOT_A_PLAYER, alert=True)
            return
        if cb.player.user_id != self._player(self.turn).user_id:
            await cb.reply(texts.NOT_YOUR_TURN)
            return
        cell = cb.data[2:]
        if not cell.isdigit() or not 0 <= int(cell) <= 8:
            return
        index = int(cell)
        if self.board[index]:
            await cb.reply(texts.XO_TAKEN)
            return
        self.board[index] = self.turn
        won = winner_of(self.board)
        if won:
            await self._end(texts.XO_WIN.format(name=self._player(won).mention), self._player(won))
            return
        if all(self.board):
            await self._end(texts.XO_DRAW)  # مساوی: جایزه نصف می‌شود
            return
        self.turn = "O" if self.turn == "X" else "X"
        await self.ctx.edit(self.message_id, self._text(self._turn_status()), self._buttons(), urgent=True)
        self.ctx.set_timer("move", self.move_seconds, self._timeout)

    async def _timeout(self) -> None:
        if self.finished:
            return
        loser = self._player(self.turn)
        winner = self._player("O" if self.turn == "X" else "X")
        await self._end(texts.XO_TIMEOUT.format(loser=escape(loser.name), winner=winner.mention), winner)
