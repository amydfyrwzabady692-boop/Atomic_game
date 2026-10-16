"""حریف کامپیوتری شطرنج برای تمرین در مینی‌اپ: جست‌وجوی آلفا-بتا با ارزش مهره‌ها و جدول موقعیت.

سه سطح دارد؛ سطح آسان گاهی حرکت ضعیف‌تر انتخاب می‌کند تا برای تازه‌کارها قابل‌بردن باشد.
"""

import random

from .engine import Move, Position

VALUES = {"P": 100, "N": 320, "B": 330, "R": 500, "Q": 900, "K": 0}
MATE = 100_000
# سطح ← (عمق جست‌وجو، احتمال انتخاب یکی از چند حرکت خوب به‌جای بهترین)
LEVELS = {"easy": (1, 0.45), "medium": (2, 0.1), "hard": (3, 0.0)}

# جدول موقعیت از دید سفید (ردیف ۰ = ردیف ۱ صفحه)؛ برای سیاه قرینه می‌شود
_PAWN = [
    0, 0, 0, 0, 0, 0, 0, 0,
    5, 10, 10, -20, -20, 10, 10, 5,
    5, -5, -10, 0, 0, -10, -5, 5,
    0, 0, 0, 20, 20, 0, 0, 0,
    5, 5, 10, 25, 25, 10, 5, 5,
    10, 10, 20, 30, 30, 20, 10, 10,
    50, 50, 50, 50, 50, 50, 50, 50,
    0, 0, 0, 0, 0, 0, 0, 0,
]  # fmt: skip
_KNIGHT = [
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20, 0, 5, 5, 0, -20, -40,
    -30, 5, 10, 15, 15, 10, 5, -30,
    -30, 0, 15, 20, 20, 15, 0, -30,
    -30, 5, 15, 20, 20, 15, 5, -30,
    -30, 0, 10, 15, 15, 10, 0, -30,
    -40, -20, 0, 0, 0, 0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
]  # fmt: skip
_CENTER = [
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10, 5, 0, 0, 0, 0, 5, -10,
    -10, 10, 10, 10, 10, 10, 10, -10,
    -10, 0, 10, 10, 10, 10, 0, -10,
    -10, 5, 5, 10, 10, 5, 5, -10,
    -10, 0, 5, 10, 10, 5, 0, -10,
    -10, 0, 0, 0, 0, 0, 0, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
]  # fmt: skip
_KING = [
    20, 30, 10, 0, 0, 10, 30, 20,
    20, 20, 0, 0, 0, 0, 20, 20,
    -10, -20, -20, -20, -20, -20, -20, -10,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
]  # fmt: skip
TABLES = {"P": _PAWN, "N": _KNIGHT, "B": _CENTER, "Q": _CENTER, "R": [0] * 64, "K": _KING}


def evaluate(position: Position) -> int:
    """امتیاز وضعیت از دید بازیکنی که نوبتش است."""
    score = 0
    for index, piece in enumerate(position.board):
        if piece == ".":
            continue
        kind = piece.upper()
        if piece.isupper():
            score += VALUES[kind] + TABLES[kind][index]
        else:
            mirrored = (7 - index // 8) * 8 + index % 8
            score -= VALUES[kind] + TABLES[kind][mirrored]
    return score if position.turn == "w" else -score


def _ordered(position: Position) -> list[Move]:
    """زدن مهره‌های باارزش و ارتقا اول بررسی می‌شوند تا آلفا-بتا زودتر هرس کند."""

    def weight(move: Move) -> int:
        target = position.board[move.dst]
        gain = VALUES[target.upper()] * 10 - VALUES[position.board[move.src].upper()] if target != "." else 0
        return gain + (800 if move.promo else 0)

    return sorted(position.legal_moves(), key=weight, reverse=True)


def _search(position: Position, depth: int, alpha: int, beta: int) -> int:
    if depth == 0:  # برگ‌ها: فقط ارزیابی، بدون ساختن حرکت‌ها (پرهزینه‌ترین بخش)
        return evaluate(position)
    moves = _ordered(position)
    if not moves:
        return -MATE - depth if position.in_check() else 0
    best = -MATE * 2
    for move in moves:
        score = -_search(position.push(move, validate=False), depth - 1, -beta, -alpha)
        if score > best:
            best = score
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def choose_move(position: Position, level: str = "medium", rng: random.Random | None = None) -> Move | None:
    """حرکت کامپیوتر برای بازیکنی که نوبتش است (یا ``None`` اگر حرکتی نمانده)."""
    rng = rng or random.Random()
    depth, sloppiness = LEVELS.get(level, LEVELS["medium"])
    scored = []
    for move in _ordered(position):
        score = -_search(position.push(move, validate=False), depth - 1, -MATE * 2, MATE * 2)
        scored.append((score, move))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    if sloppiness and len(scored) > 1 and rng.random() < sloppiness:
        return rng.choice(scored[: min(4, len(scored))])[1]
    best = scored[0][0]
    return rng.choice([move for score, move in scored if score == best])
