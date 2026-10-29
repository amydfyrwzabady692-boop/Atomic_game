"""قوانین کامل شطرنج (بدون موتور هوش مصنوعی): تولید حرکت‌های قانونی، کیش، قلعه،
آن‌پاسان، ارتقا و حالت‌های پایان بازی.

خانه‌ها با اندیس ۰ تا ۶۳ مشخص می‌شوند: ``index = rank * 8 + file``؛ rank صفر یعنی ردیف ۱
(سمت سفید) و file صفر یعنی ستون a. مهره‌ها حرف‌اند: بزرگ برای سفید (PNBRQK) و کوچک برای سیاه.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FILES = "abcdefgh"
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

KNIGHT_STEPS = [(1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)]
KING_STEPS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
ROOK_DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]
BISHOP_DIRS = [(1, 1), (1, -1), (-1, 1), (-1, -1)]

# قلعه: (حق، خانه‌ی شاه، مقصد شاه، خانه‌ی رخ، مقصد رخ، خانه‌هایی که باید خالی باشند، خانه‌هایی که نباید تهدید شوند)
CASTLES = {
    "K": (4, 6, 7, 5, (5, 6), (4, 5, 6)),
    "Q": (4, 2, 0, 3, (1, 2, 3), (4, 3, 2)),
    "k": (60, 62, 63, 61, (61, 62), (60, 61, 62)),
    "q": (60, 58, 56, 59, (57, 58, 59), (60, 59, 58)),
}


def square_name(index: int) -> str:
    return f"{FILES[index % 8]}{index // 8 + 1}"


def parse_square(name: str) -> int:
    return (int(name[1]) - 1) * 8 + FILES.index(name[0])


def color_of(piece: str) -> str | None:
    if piece == ".":
        return None
    return "w" if piece.isupper() else "b"


@dataclass(frozen=True)
class Move:
    src: int
    dst: int
    promo: str = ""  # حرف مهره‌ی ارتقا با رنگ حرکت‌دهنده (مثل Q یا q)

    def __str__(self) -> str:
        return square_name(self.src) + square_name(self.dst) + self.promo.lower()


@dataclass
class Position:
    board: list[str]
    turn: str = "w"
    castling: str = "KQkq"
    ep: int | None = None  # خانه‌ای که با آن‌پاسان می‌شود رویش زد
    halfmove: int = 0
    fullmove: int = 1
    _legal: list[Move] | None = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------ ساخت
    @classmethod
    def initial(cls) -> Position:
        return cls.from_fen(START_FEN)

    @classmethod
    def from_fen(cls, fen: str) -> Position:
        parts = fen.split()
        board = ["."] * 64
        for row, text in enumerate(parts[0].split("/")):
            rank = 7 - row
            file = 0
            for ch in text:
                if ch.isdigit():
                    file += int(ch)
                else:
                    board[rank * 8 + file] = ch
                    file += 1
        castling = "" if len(parts) < 3 or parts[2] == "-" else parts[2]
        ep = None if len(parts) < 4 or parts[3] == "-" else parse_square(parts[3])
        halfmove = int(parts[4]) if len(parts) > 4 else 0
        fullmove = int(parts[5]) if len(parts) > 5 else 1
        return cls(board, parts[1] if len(parts) > 1 else "w", castling, ep, halfmove, fullmove)

    def fen(self) -> str:
        """وضعیت به قالب FEN (برعکس ``from_fen``)."""
        rows = []
        for rank in range(7, -1, -1):
            text, empty = "", 0
            for piece in self.board[rank * 8 : rank * 8 + 8]:
                if piece == ".":
                    empty += 1
                    continue
                text += (str(empty) if empty else "") + piece
                empty = 0
            rows.append(text + (str(empty) if empty else ""))
        ep = square_name(self.ep) if self.ep is not None else "-"
        return f"{'/'.join(rows)} {self.turn} {self.castling or '-'} {ep} {self.halfmove} {self.fullmove}"

    def key(self) -> tuple:
        """کلید تکرار وضعیت (برای قانون تکرار سه‌باره)."""
        return ("".join(self.board), self.turn, self.castling, self.ep)

    # ------------------------------------------------------------------ تهدید
    def is_attacked(self, square: int, by: str) -> bool:
        """آیا خانه‌ی ``square`` زیر حمله‌ی رنگ ``by`` است؟"""
        board = self.board
        r, f = divmod(square, 8)
        pawn, knight, bishop, rook, queen, king = ("PNBRQK" if by == "w" else "pnbrqk")
        # پیاده: سفید از پایین حمله می‌کند
        pr = r - 1 if by == "w" else r + 1
        if 0 <= pr < 8:
            for pf in (f - 1, f + 1):
                if 0 <= pf < 8 and board[pr * 8 + pf] == pawn:
                    return True
        for dr, df in KNIGHT_STEPS:
            nr, nf = r + dr, f + df
            if 0 <= nr < 8 and 0 <= nf < 8 and board[nr * 8 + nf] == knight:
                return True
        for dr, df in KING_STEPS:
            nr, nf = r + dr, f + df
            if 0 <= nr < 8 and 0 <= nf < 8 and board[nr * 8 + nf] == king:
                return True
        for dirs, sliders in ((ROOK_DIRS, (rook, queen)), (BISHOP_DIRS, (bishop, queen))):
            for dr, df in dirs:
                nr, nf = r + dr, f + df
                while 0 <= nr < 8 and 0 <= nf < 8:
                    piece = board[nr * 8 + nf]
                    if piece != ".":
                        if piece in sliders:
                            return True
                        break
                    nr += dr
                    nf += df
        return False

    def king_square(self, color: str) -> int:
        return self.board.index("K" if color == "w" else "k")

    def in_check(self, color: str | None = None) -> bool:
        color = color or self.turn
        return self.is_attacked(self.king_square(color), "b" if color == "w" else "w")

    # ------------------------------------------------------------------ تولید حرکت
    def _pseudo_moves(self):
        board, turn = self.board, self.turn
        enemy = "b" if turn == "w" else "w"
        for src, piece in enumerate(board):
            if color_of(piece) != turn:
                continue
            r, f = divmod(src, 8)
            kind = piece.upper()
            if kind == "P":
                step = 1 if turn == "w" else -1
                start_rank, last_rank = (1, 7) if turn == "w" else (6, 0)
                promos = ["Q", "R", "B", "N"] if turn == "w" else ["q", "r", "b", "n"]
                nr = r + step
                if 0 <= nr < 8:
                    dst = nr * 8 + f
                    if board[dst] == ".":
                        if nr == last_rank:
                            for p in promos:
                                yield Move(src, dst, p)
                        else:
                            yield Move(src, dst)
                            if r == start_rank and board[(r + 2 * step) * 8 + f] == ".":
                                yield Move(src, (r + 2 * step) * 8 + f)
                    for nf in (f - 1, f + 1):
                        if not 0 <= nf < 8:
                            continue
                        dst = nr * 8 + nf
                        if color_of(board[dst]) == enemy:
                            if nr == last_rank:
                                for p in promos:
                                    yield Move(src, dst, p)
                            else:
                                yield Move(src, dst)
                        elif dst == self.ep:
                            yield Move(src, dst)
            elif kind in ("N", "K"):
                for dr, df in KNIGHT_STEPS if kind == "N" else KING_STEPS:
                    nr, nf = r + dr, f + df
                    if 0 <= nr < 8 and 0 <= nf < 8 and color_of(board[nr * 8 + nf]) != turn:
                        yield Move(src, nr * 8 + nf)
            else:
                dirs = ROOK_DIRS if kind == "R" else BISHOP_DIRS if kind == "B" else ROOK_DIRS + BISHOP_DIRS
                for dr, df in dirs:
                    nr, nf = r + dr, f + df
                    while 0 <= nr < 8 and 0 <= nf < 8:
                        target = board[nr * 8 + nf]
                        if color_of(target) == turn:
                            break
                        yield Move(src, nr * 8 + nf)
                        if target != ".":
                            break
                        nr += dr
                        nf += df
        # قلعه
        rights = "KQ" if turn == "w" else "kq"
        king = "K" if turn == "w" else "k"
        rook = "R" if turn == "w" else "r"
        for right in rights:
            if right not in self.castling:
                continue
            k_sq, k_dst, r_sq, _, empty, safe = CASTLES[right]
            if board[k_sq] != king or board[r_sq] != rook:
                continue
            if any(board[s] != "." for s in empty):
                continue
            if any(self.is_attacked(s, enemy) for s in safe):
                continue
            yield Move(k_sq, k_dst)

    def legal_moves(self) -> list[Move]:
        if self._legal is None:
            legal = []
            for move in self._pseudo_moves():
                after = self.push(move, validate=False)
                if not after.in_check(self.turn):
                    legal.append(move)
            self._legal = legal
        return self._legal

    def moves_from(self, square: int) -> list[Move]:
        return [m for m in self.legal_moves() if m.src == square]

    def san(self, move: Move) -> str:
        """نماد جبری استاندارد (SAN) یک حرکت قانونی، مثل Nf3، exd5، Nbd7، O-O، e8=Q+ یا Qh4#."""
        piece = self.board[move.src]
        kind = piece.upper()
        if kind == "K" and abs(move.dst - move.src) == 2:
            text = "O-O" if move.dst > move.src else "O-O-O"
        else:
            en_passant = kind == "P" and move.dst == self.ep and move.src % 8 != move.dst % 8
            capture = self.board[move.dst] != "." or en_passant
            if kind == "P":
                text = (FILES[move.src % 8] + "x" if capture else "") + square_name(move.dst)
                if move.promo:
                    text += "=" + move.promo.upper()
            else:
                text = kind
                # اگر مهره‌ی هم‌نوع دیگری هم به همین خانه می‌رود، ستون یا ردیف (یا هر دو) نوشته می‌شود
                rivals = [m.src for m in self.legal_moves() if m.dst == move.dst and m.src != move.src and self.board[m.src] == piece]
                if rivals:
                    if all(src % 8 != move.src % 8 for src in rivals):
                        text += FILES[move.src % 8]
                    elif all(src // 8 != move.src // 8 for src in rivals):
                        text += str(move.src // 8 + 1)
                    else:
                        text += square_name(move.src)
                text += ("x" if capture else "") + square_name(move.dst)
        after = self.push(move, validate=False)
        if after.in_check():
            text += "+" if after.legal_moves() else "#"
        return text

    def has_mating_material(self, color: str) -> bool:
        """آیا رنگ ``color`` با هیچ رشته حرکت قانونی‌ای می‌تواند مات کند؟ (قانون ۶.۹ فیده برای پایان وقت)

        شاه تنها هرگز نمی‌تواند مات کند. با هر مهره‌ی دیگری (حتی یک اسب یا فیل) مات کمکی در وضعیت‌هایی
        ممکن است که مهره‌های خود حریف راه فرار شاهش را بسته‌اند؛ آن حالت‌های بی‌مهره‌ی دو طرف (مثل شاه و
        فیل در برابر شاه تنها) پیش‌تر با «مهره‌ی ناکافی» مساوی شده‌اند."""
        return any(p != "." and color_of(p) == color and p.upper() != "K" for p in self.board)

    # ------------------------------------------------------------------ اجرای حرکت
    def push(self, move: Move, validate: bool = True) -> Position:
        """وضعیت جدید بعد از حرکت (وضعیت فعلی تغییر نمی‌کند)."""
        if validate and move not in self.legal_moves():
            raise ValueError(f"illegal move {move}")
        board = list(self.board)
        piece = board[move.src]
        captured = board[move.dst]
        kind = piece.upper()
        board[move.dst] = move.promo or piece
        board[move.src] = "."
        # آن‌پاسان: پیاده‌ی حریف از کنار برداشته می‌شود
        if kind == "P" and move.dst == self.ep and captured == "." and move.src % 8 != move.dst % 8:
            board[move.dst - 8 if self.turn == "w" else move.dst + 8] = "."
            captured = "p"
        # قلعه: رخ هم جابه‌جا می‌شود
        if kind == "K" and abs(move.dst - move.src) == 2:
            for k_sq, k_dst, r_sq, r_dst, _, _ in CASTLES.values():
                if move.src == k_sq and move.dst == k_dst:
                    board[r_dst] = board[r_sq]
                    board[r_sq] = "."
        castling = self.castling
        for sq, rights in ((4, "KQ"), (60, "kq"), (0, "Q"), (7, "K"), (56, "q"), (63, "k")):
            if move.src == sq or move.dst == sq:
                castling = "".join(c for c in castling if c not in rights)
        ep = None
        if kind == "P" and abs(move.dst - move.src) == 16:
            ep = (move.src + move.dst) // 2
        halfmove = 0 if kind == "P" or captured != "." else self.halfmove + 1
        return Position(
            board,
            "b" if self.turn == "w" else "w",
            castling,
            ep,
            halfmove,
            self.fullmove + (1 if self.turn == "b" else 0),
        )

    # ------------------------------------------------------------------ پایان بازی
    def insufficient_material(self) -> bool:
        pieces = [p for p in self.board if p != "." and p.upper() != "K"]
        if not pieces:
            return True
        if len(pieces) == 1 and pieces[0].upper() in ("N", "B"):
            return True
        if all(p.upper() == "B" for p in pieces):
            # فقط فیل‌های هم‌رنگ‌خانه
            colors = {(i // 8 + i % 8) % 2 for i, p in enumerate(self.board) if p.upper() == "B"}
            return len(colors) == 1
        return False

    def outcome(self) -> str | None:
        """``checkmate`` / ``stalemate`` / ``insufficient`` / ``fifty`` یا None."""
        if not self.legal_moves():
            return "checkmate" if self.in_check() else "stalemate"
        if self.insufficient_material():
            return "insufficient"
        if self.halfmove >= 100:
            return "fifty"
        return None


def perft(position: Position, depth: int) -> int:
    """شمارش گره‌ها؛ برای اطمینان از درستی تولید حرکت با اعداد مرجع."""
    if depth == 0:
        return 1
    moves = position.legal_moves()
    if depth == 1:
        return len(moves)
    return sum(perft(position.push(m, validate=False), depth - 1) for m in moves)
