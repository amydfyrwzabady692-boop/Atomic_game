from html import escape

from core import texts
from core.textutils import fa_num
from games.engine.base import DANGER, BaseGame, Button, IncomingCallback
from games.engine.registry import register_game

COLUMNS, ROWS, NEED = 7, 6, 4
DISCS = {"R": "🔴", "Y": "🟡"}
WIN_DISCS = {"R": "🟥", "Y": "🟨"}
EMPTY = "⚪️"
NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]
DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]


def winning_cells(board: list[str], last: int) -> list[int]:
    """خانه‌های خط برنده‌ای که از خانه‌ی ``last`` می‌گذرد (یا لیست خالی). خانه = ردیف×۷ + ستون، ردیف ۰ پایین است."""
    mark = board[last]
    row, column = divmod(last, COLUMNS)
    for d_row, d_column in DIRECTIONS:
        cells = [last]
        for sign in (1, -1):
            r, c = row + d_row * sign, column + d_column * sign
            while 0 <= r < ROWS and 0 <= c < COLUMNS and board[r * COLUMNS + c] == mark:
                cells.append(r * COLUMNS + c)
                r, c = r + d_row * sign, c + d_column * sign
        if len(cells) >= NEED:
            return cells
    return []


@register_game
class ConnectFourGame(BaseGame):
    """دوز چهارتایی استاندارد: صفحه‌ی ۷×۶، مهره به پایین‌ترین خانه‌ی خالی ستون می‌افتد و چهار مهره‌ی
    هم‌رنگ در یک خط (افقی، عمودی یا مورب) برنده است."""

    key = "connect4"
    title_fa = "دوز چهارتایی"
    emoji = "🔴"
    description_fa = "دوز چهارتایی دونفره روی صفحه‌ی ۷×۶؛ چهار مهره‌ی هم‌رنگ در یک خط یعنی برد."
    min_players = 2
    max_players = 2
    players_ceiling = 2
    move_seconds = 30
    rules_fa = [
        "به‌نوبت یک ستون را بزن؛ مهره به پایین‌ترین خانه‌ی خالی آن می‌افتد.",
        "چهار مهره‌ی هم‌رنگ در یک خط افقی، عمودی یا مورب یعنی برد.",
        "هر حرکت {move_seconds} ثانیه وقت دارد؛ صفحه‌ی پر یعنی مساوی.",
    ]

    async def start(self) -> None:
        order = list(self.players)
        self.ctx.rng.shuffle(order)
        self.red, self.yellow = order
        self.board = [""] * (COLUMNS * ROWS)
        self.turn = "R"
        self.winning: list[int] = []
        self.message_id = await self.ctx.send(self._text(self._turn_status()), self._buttons())
        self.ctx.set_timer("move", self.move_seconds, self._timeout)

    async def next_round(self) -> None:
        return None

    def _player(self, mark: str):
        return self.red if mark == "R" else self.yellow

    def _turn_status(self) -> str:
        status = texts.XO_TURN.format(
            name=self._player(self.turn).mention, mark=DISCS[self.turn], seconds=fa_num(self.move_seconds)
        )
        if not any(self.board):
            status += texts.C4_HINT
        return status

    def _grid(self) -> str:
        lines = []
        for row in range(ROWS - 1, -1, -1):
            cells = []
            for column in range(COLUMNS):
                index = row * COLUMNS + column
                mark = self.board[index]
                cells.append((WIN_DISCS if index in self.winning else DISCS).get(mark, EMPTY))
            lines.append("".join(cells))
        return "\n".join(lines) + "\n" + "".join(NUMBERS)

    def _text(self, status: str) -> str:
        return texts.C4_BOARD.format(
            red=escape(self.red.name), yellow=escape(self.yellow.name), grid=self._grid(), status=status
        )

    def _buttons(self):
        style = DANGER if self.turn == "R" else ""
        return [[Button(NUMBERS[column], f"c:{column}", style) for column in range(COLUMNS)]]

    async def _end(self, status: str, winner=None) -> None:
        self.finished = True
        self.ctx.cancel_timer("move")
        if winner is not None:
            self.add_score(winner.user_id, 1)
        await self.ctx.edit(self.message_id, self._text(status), None, urgent=True)
        await self.ctx.end_game()

    async def on_callback(self, cb: IncomingCallback) -> None:
        if self.finished or not cb.data.startswith("c:"):
            return
        if cb.player is None:
            await cb.reply(texts.NOT_A_PLAYER, alert=True)
            return
        if cb.player.user_id != self._player(self.turn).user_id:
            await cb.reply(texts.NOT_YOUR_TURN)
            return
        value = cb.data[2:]
        if not value.isdigit() or not 0 <= int(value) < COLUMNS:
            return
        column = int(value)
        row = next((r for r in range(ROWS) if not self.board[r * COLUMNS + column]), None)
        if row is None:
            await cb.reply(texts.C4_FULL)
            return
        index = row * COLUMNS + column
        self.board[index] = self.turn
        self.winning = winning_cells(self.board, index)
        if self.winning:
            winner = self._player(self.turn)
            await self._end(texts.XO_WIN.format(name=winner.mention), winner)
            return
        if all(self.board):
            await self._end(texts.XO_DRAW)
            return
        self.turn = "Y" if self.turn == "R" else "R"
        await self.ctx.edit(self.message_id, self._text(self._turn_status()), self._buttons(), urgent=True)
        self.ctx.set_timer("move", self.move_seconds, self._timeout)

    async def _timeout(self) -> None:
        if self.finished:
            return
        loser = self._player(self.turn)
        winner = self._player("Y" if self.turn == "R" else "R")
        await self._end(texts.XO_TIMEOUT.format(loser=escape(loser.name), winner=winner.mention), winner)
