"""ساخت متن پیام‌ها و کیبوردهای لابی، نتیجه و مسابقه‌ی آرکید."""

from html import escape

from django.conf import settings
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core import texts
from core.texts import fa_num
from games.catalog import GameInfo


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
    players = "\n".join(f"• {escape(n)}" for n in names) if names else texts.LOBBY_NO_PLAYERS
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
    for r in sorted(result.players, key=lambda p: p.rank):
        prize = texts.RESULT_PRIZE.format(prize=fa_num(r.prize)) if r.prize else ""
        lines.append(
            texts.RESULT_LINE.format(
                medal=texts.MEDALS.get(r.rank, texts.MEDAL_OTHER),
                name=r.user.mention_html,
                score=fa_num(r.score),
                prize=prize,
                xp=fa_num(r.xp),
            )
        )
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
        lines.append("\n\n" + "\n".join(extras))
    return "".join(lines)


def arcade_text(match, info: GameInfo, standings, remaining: int, attempts: int, flash: str = "") -> str:
    rows = []
    for i, s in enumerate(standings, start=1):
        medal = texts.MEDALS.get(i, texts.MEDAL_OTHER)
        score = fa_num(s.score) if s.attempts else "—"
        rows.append(
            texts.ARCADE_ROW.format(
                medal=medal, name=escape(s.name), score=score, used=fa_num(s.attempts), total=fa_num(attempts)
            )
        )
    minutes, seconds = divmod(max(remaining, 0), 60)
    return texts.ARCADE_RUNNING.format(
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
