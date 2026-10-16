"""ساخت متن پیام‌ها و کیبوردهای لابی، نتیجه و مسابقه‌ی آرکید."""

from html import escape

from django.conf import settings
from telegram import InlineKeyboardMarkup

from core import texts
from core.texts import fa_num
from games.catalog import GameInfo

from . import ui

# پیام تلگرام حداکثر ۴۰۹۶ نویسه است؛ با ظرفیت‌های بزرگ، فهرست‌ها کوتاه می‌شوند
LOBBY_NAMES_SHOWN = 30
BOARD_ROWS_SHOWN = 20
RESULT_ROWS_SHOWN = 25
RESULT_EXTRAS_SHOWN = 8
NAME_CHARS = 24
STARTING_NAMES_SHOWN = 30
ALERT_CHARS = 200  # سقف متن answerCallbackQuery


def short_name(name: str) -> str:
    return name if len(name) <= NAME_CHARS else name[: NAME_CHARS - 1] + "…"


def short_mention(user) -> str:
    return f'<a href="tg://user?id={user.tg_id}">{escape(short_name(user.display_name))}</a>'


def names_line(names: list[str], limit: int = STARTING_NAMES_SHOWN) -> str:
    """فهرست یک‌خطی نام‌ها؛ نام‌های بلند کوتاه و فهرست‌های طولانی بریده می‌شوند تا پیام از سقف تلگرام رد نشود."""
    line = "، ".join(escape(short_name(name)) for name in names[:limit])
    if len(names) > limit:
        line += " " + texts.MORE_PLAYERS.format(n=fa_num(len(names) - limit))
    return line


def players_label(info: GameInfo) -> str:
    if info.min_players == info.max_players:
        return texts.RULES_PLAYERS_FIXED.format(n=fa_num(info.min_players))
    return texts.RULES_PLAYERS_RANGE.format(min=fa_num(info.min_players), max=fa_num(info.max_players))


def rules_lines(info: GameInfo) -> list[str]:
    return [texts.RULES_LINE.format(line=line) for line in (info.rules or (info.description_fa,))]


def rules_text(info: GameInfo) -> str:
    """متن کامل قوانین یک بازی برای دستور /rules."""
    text = texts.RULES_GAME.format(
        emoji=info.emoji,
        title=info.title_fa,
        lines="\n".join(escape(line) for line in rules_lines(info)),
        players=players_label(info),
        style=info.style,
    )
    return text + (texts.RULES_ARCADE_NOTE if info.is_arcade else "")


def rules_alert(info: GameInfo) -> str:
    """قوانین کوتاه برای پنجره‌ی هشدار دکمه‌ی «قوانین بازی» (حداکثر ۲۰۰ نویسه)."""
    text = "\n".join(rules_lines(info))
    return text if len(text) <= ALERT_CHARS else text[: ALERT_CHARS - 1] + "…"


def split_label(split: list[int]) -> str:
    key = "-".join(str(x) for x in split)
    return texts.SPLIT_LABELS.get(key, key)


def referral_text(referral, invitee) -> str:
    """پیام به دعوت‌کننده بعد از اولین بازی سکه‌ای دوستش: جایزه یا پیشرفت تا جایزه‌ی بعدی.
    اگر جایزه‌ی دعوت در تنظیمات خاموش باشد متن خالی برمی‌گرداند (پیامی فرستاده نمی‌شود)."""
    name = escape(invitee.display_name)
    if referral.reward:
        return texts.REFERRAL_REWARDED.format(name=name, count=fa_num(referral.count), amount=fa_num(referral.reward))
    if referral.next_reward <= 0:
        return ""
    progress = referral.count % referral.every
    return texts.REFERRAL_PROGRESS.format(
        name=name,
        progress=fa_num(progress),
        every=fa_num(referral.every),
        left=fa_num(referral.every - progress),
        reward=fa_num(referral.next_reward),
    )


def fee_label(fee: int) -> str:
    return texts.FEE_FREE if fee == 0 else texts.FEE_BTN.format(amount=fa_num(fee))


def variant_suffix(info: GameInfo, options: dict) -> str:
    label = info.variants.get(options.get("variant", ""))
    return f" — {label}" if label else ""


def bot_username(context=None) -> str:
    if context is not None and context.bot_data.get("username"):
        return context.bot_data["username"]
    return settings.BOT_USERNAME


def arcade_ready() -> bool:
    """مینی‌اپ آرکید فقط با آدرس عمومی HTTPS کار می‌کند؛ تا تنظیم نشود بازی‌های آرکید پیشنهاد نمی‌شوند."""
    return settings.MINIAPP_BASE_URL.startswith("https://")


def start_link(username: str, payload: str = "join") -> str:
    return f"https://t.me/{username}?start={payload}"


def miniapp_link(username: str, token: str) -> str:
    """لینک مستقیم مینی‌اپ برای دکمه‌های داخل گروه (دکمه‌ی web_app در گروه مجاز نیست).

    با ``MINIAPP_SHORT_NAME`` لینک مینی‌اپی است که در BotFather با /newapp و همین نام کوتاه ساخته شده؛
    اگر خالی باشد لینک «مینی‌اپ اصلی» ربات (BotFather ← Bot Settings ← Configure Mini App) ساخته می‌شود.
    اگر هیچ‌کدام در BotFather تنظیم نشده باشد، تلگرام به‌جای صفحه‌ی بازی فقط چت ربات را باز می‌کند؛
    برای همین زیر هر دکمه یک راه پشتیبان (``open_in_bot_link``) هم هست.
    """
    short = (settings.MINIAPP_SHORT_NAME or "").strip()
    if short:
        return f"https://t.me/{username}/{short}?startapp={token}"
    return f"https://t.me/{username}?startapp={token}"


OPEN_PAYLOAD_PREFIX = "p_"


def open_in_bot_link(username: str, token: str) -> str:
    """راه پشتیبان: پیوی ربات باز می‌شود و ربات دکمه‌ی web_app همین بازی را می‌فرستد."""
    return start_link(username, OPEN_PAYLOAD_PREFIX + token)


def game_page_url(token: str) -> str:
    """آدرس مستقیم صفحه‌ی بازی برای دکمه‌ی web_app در پیوی (شطرنج/دوز یا آرکید)."""
    return f"{settings.MINIAPP_BASE_URL.rstrip('/')}/arcade/?tgWebAppStartParam={token}"


def lobby_text(match, info: GameInfo, names: list[str], remaining: int, prize_note: str = "") -> str:
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
    prize = texts.LOBBY_PRIZE_NOTE.format(note=escape(prize_note)) if prize_note else ""
    text = texts.LOBBY.format(
        emoji=info.emoji,
        title=info.title_fa,
        variant=variant_suffix(info, match.options),
        description=info.description_fa,
        style=info.style,
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
    if prize:
        marker = texts.DIVIDER
        text = text.replace(marker, prize.lstrip("\n") + "\n" + marker, 1)
    return text


def lobby_keyboard(match_id: int, username: str, game_key: str = "") -> InlineKeyboardMarkup:
    rows = [
        [
            ui.button(texts.JOIN_BTN, f"j:{match_id}", style=ui.SUCCESS),
            ui.button(texts.CANCEL_BTN, f"x:{match_id}", style=ui.DANGER),
        ]
    ]
    if game_key:
        rows.append([ui.button(texts.RULES_BTN, f"rl:{game_key}", style=ui.PRIMARY)])
    rows.append([ui.button(texts.START_BOT_BTN, url=start_link(username), style=ui.PRIMARY)])
    return InlineKeyboardMarkup(rows)


def cancelled_text(reason: str, refunded: bool) -> str:
    text = texts.MATCH_CANCELLED.format(reason=texts.CANCEL_REASONS.get(reason, ""))
    if refunded:
        text += "\n" + texts.REFUND_NOTE
    return text


def result_text(result, info: GameInfo, prize_note: str = "") -> str:
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
    if prize_note:
        lines.append(texts.RESULT_PRIZE_NOTE.format(note=escape(prize_note)))
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


def live_keyboard(username: str, token: str, game_key: str) -> InlineKeyboardMarkup:
    """دکمه‌ی باز کردن صفحه‌ی گرافیکی بازی دونفره (شطرنج) در مینی‌اپ."""
    return InlineKeyboardMarkup(
        [
            [
                ui.button(
                    texts.CHESS_PLAY_BTN if game_key == "chess" else texts.LIVE_PLAY_BTN,
                    url=miniapp_link(username, token),
                    style=ui.SUCCESS,
                )
            ],
            [ui.button(texts.OPEN_IN_BOT_BTN, url=open_in_bot_link(username, token), style=ui.PRIMARY)],
            [ui.button(texts.RULES_BTN, f"rl:{game_key}", style=ui.PRIMARY)],
        ]
    )


def arcade_keyboard(username: str, token: str, game_key: str = "") -> InlineKeyboardMarkup:
    rows = [
        [ui.button(texts.ARCADE_PLAY_BTN, url=miniapp_link(username, token), style=ui.SUCCESS)],
        [ui.button(texts.OPEN_IN_BOT_BTN, url=open_in_bot_link(username, token), style=ui.PRIMARY)],
    ]
    if game_key:
        rows.append([ui.button(texts.RULES_BTN, f"rl:{game_key}", style=ui.PRIMARY)])
    return InlineKeyboardMarkup(rows)
