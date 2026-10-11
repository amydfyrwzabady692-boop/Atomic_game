"""ساخت متن پیام‌ها و کیبوردهای لابی، نتیجه و مسابقه‌ی آرکید."""

from html import escape

from django.conf import settings
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core import texts
from core.texts import fa_num
from games.catalog import GameInfo

# پیام تلگرام حداکثر ۴۰۹۶ نویسه است؛ با ظرفیت‌های بزرگ، فهرست‌ها کوتاه می‌شوند
LOBBY_NAMES_SHOWN = 30
BOARD_ROWS_SHOWN = 20
RESULT_ROWS_SHOWN = 25
RESULT_EXTRAS_SHOWN = 8
NAME_CHARS = 24


def short_name(name: str) -> str:
    return name if len(name) <= NAME_CHARS else name[: NAME_CHARS - 1] + "…"


def short_mention(user) -> str:
    return f'<a href="tg://user?id={user.tg_id}">{escape(short_name(user.display_name))}</a>'


def split_label(split: list[int]) -> str:
    key = "-".join(str(x) for x in split)
    return texts.SPLIT_LABELS.get(key, key)


def fee_label(fee: int) -> str:
    return texts.FEE_FREE if fee == 0 else texts.FEE_BTN.format(amount=fa_num(fee))


def variant_suffix(info: GameInfo, options: dict) -> str:
    label = info.variants.get(options.get("variant", ""))
    return f" — {label}" if label else ""


def bot_username(context=None) -> str:
    if context is not None and context.bot_data.get("username"):
        return context.bot_data["username"]
    return settings.BOT_USERNAME


def start_link(username: str, payload: str = "join") -> str:
    return f"https://t.me/{username}?start={payload}"


def miniapp_link(username: str, token: str) -> str:
    return f"https://t.me/{username}/{settings.MINIAPP_SHORT_NAME}?startapp={token}"


def lobby_text(match, info: GameInfo, names: list[str], remaining: int) -> str:
    if names:
        players = "\n".join(
            texts.LOBBY_PLAYER.format(n=fa_num(i), name=escape(short_name(n)))
            for i, n in enumerate(names[:LOBBY_NAMES_SHOWN], start=1)
        )
        if len(names) > LOBBY_NAMES_SHOWN:
            players += "\n" + texts.MORE_PLAYERS.format(n=fa_num(len(names) - LOBBY_NAMES_SHOWN))
    else:
        players = texts.LOBBY_NO_PLAYERS
    total = 60
    if match.created_at and match.join_deadline:
        total = max(1, int((match.join_deadline - match.created_at).total_seconds()))
    return texts.LOBBY.format(
        emoji=info.emoji,
        title=info.title_fa,
        variant=variant_suffix(info, match.options),
        description=info.description_fa,
        fee=fee_label(match.entry_fee),
        pot=fa_num(match.pot),
        split=split_label(match.prize_split),
        count=fa_num(len(names)),
        max=fa_num(match.max_players),
        players=players,
        remaining=fa_num(max(remaining, 0)),
        min=fa_num(match.min_players),
        bar=texts.progress_bar(max(remaining, 0) / total),
    )


def lobby_keyboard(match_id: int, username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(texts.JOIN_BTN, callback_data=f"j:{match_id}"),
                InlineKeyboardButton(texts.CANCEL_BTN, callback_data=f"x:{match_id}"),
            ],
            [InlineKeyboardButton(texts.START_BOT_BTN, url=start_link(username))],
        ]
    )


def cancelled_text(reason: str, refunded: bool) -> str:
    text = texts.MATCH_CANCELLED.format(reason=texts.CANCEL_REASONS.get(reason, ""))
    if refunded:
        text += "\n" + texts.REFUND_NOTE
    return text


def result_text(result, info: GameInfo) -> str:
    lines = [texts.RESULT_HEADER.format(title=info.title_fa)]
    ranked = sorted(result.players, key=lambda p: p.rank)
    for r in ranked[:RESULT_ROWS_SHOWN]:
        prize = texts.RESULT_PRIZE.format(prize=fa_num(r.prize)) if r.prize else ""
        lines.append(
            texts.RESULT_LINE.format(
                medal=texts.MEDALS.get(r.rank, texts.MEDAL_OTHER),
                name=short_mention(r.user),
                score=fa_num(r.score),
                prize=prize,
                xp=fa_num(r.xp),
            )
        )
    if len(ranked) > RESULT_ROWS_SHOWN:
        lines.append(texts.MORE_PLAYERS.format(n=fa_num(len(ranked) - RESULT_ROWS_SHOWN)) + "\n")
    lines.append(
        texts.RESULT_FOOTER.format(pot=fa_num(result.match.pot)) if result.match.pot else texts.RESULT_FREE
    )
    extras = []
    for r in result.players:
        if r.leveled_up:
            extras.append(texts.LEVEL_UP.format(name=escape(r.user.display_name), level=fa_num(r.user.level)))
        for a in r.achievements:
            extras.append(
                f"{escape(r.user.display_name)} — "
                + texts.ACHIEVEMENT_UNLOCKED.format(emoji=a.emoji, title=a.title, reward=fa_num(a.reward_coins))
            )
    if extras:
        lines.append("\n\n" + "\n".join(extras[:RESULT_EXTRAS_SHOWN]))
    return "".join(lines)


def arcade_text(match, info: GameInfo, standings, remaining: int, attempts: int, flash: str = "") -> str:
    rows = []
    for i, s in enumerate(standings[:BOARD_ROWS_SHOWN], start=1):
        medal = texts.MEDALS.get(i, texts.MEDAL_OTHER)
        score = fa_num(s.score) if s.attempts else "—"
        rows.append(
            texts.ARCADE_ROW.format(
                medal=medal,
                name=escape(short_name(s.name)),
                score=score,
                used=fa_num(s.attempts),
                total=fa_num(attempts),
            )
        )
    if len(standings) > BOARD_ROWS_SHOWN:
        rows.append(texts.MORE_PLAYERS.format(n=fa_num(len(standings) - BOARD_ROWS_SHOWN)))
    minutes, seconds = divmod(max(remaining, 0), 60)
    window = int(match.options.get("window_minutes") or 5) * 60
    return texts.ARCADE_RUNNING.format(
        bar=texts.progress_bar(max(remaining, 0) / window, 8),
        emoji=info.emoji,
        title=info.title_fa,
        variant=variant_suffix(info, match.options),
        pot=fa_num(match.pot),
        attempts=fa_num(attempts),
        board="\n".join(rows),
        minutes=fa_num(minutes),
        seconds=texts.fa_digits(f"{seconds:02d}"),
        flash=f"\n\n{flash}" if flash else "",
    )


def arcade_keyboard(username: str, token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(texts.ARCADE_PLAY_BTN, url=miniapp_link(username, token))]])
