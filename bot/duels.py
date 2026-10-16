"""اجرای دوئل‌های «حریف تصادفی» در ربات: پیام‌های پیوی دو طرف و پایان بازی.

دوئل ممکن است از ربات یا از مینی‌اپ شروع/تغییر کند؛ برای همین ربات هر چند ثانیه دیتابیس را نگاه
می‌کند (``DuelRunner.tick``): جستجوهای منقضی، دوئل‌هایی که نسخه‌شان عوض شده (پیام دو طرف به‌روز
می‌شود) و بازی‌های تمام‌شده (جایزه و اعلام نتیجه).
"""

import logging
from html import escape

from django.utils import timezone
from telegram import InlineKeyboardMarkup, WebAppInfo

from core import texts
from core.texts import fa_num
from games import duels
from games.catalog import get_info
from games.models import Duel, MatchPlayer

from . import render, ui
from .db import db
from .tg import tg_call

logger = logging.getLogger(__name__)

POLL_SECONDS = 2


# ------------------------------------------------------------------ متن و دکمه‌ها
def game_label(game_type: str) -> str:
    info = get_info(game_type)
    return f"{info.emoji} {info.title_fa}" if info else game_type


def stake_label(stake: int | None) -> str:
    if stake is None:
        return texts.DUEL_STAKE_ANY
    if stake == 0:
        return texts.DUEL_STAKE_FREE
    return f"{fa_num(stake)} {texts.COIN}"


def games_keyboard() -> InlineKeyboardMarkup:
    buttons = [ui.button(f"{g.emoji} {g.title_fa}", f"du:g:{g.key}", style=ui.PRIMARY) for g in duels.available_games()]
    return InlineKeyboardMarkup(ui.rows(buttons, 2))


def stakes_keyboard(game_type: str) -> InlineKeyboardMarkup:
    buttons = [ui.button(stake_label(s), f"du:s:{game_type}:{s}", style=ui.SUCCESS if s == 0 else ui.PRIMARY) for s in duels.STAKE_CHOICES]
    rows = ui.rows(buttons, 3)
    rows.append([ui.button(texts.DUEL_STAKE_ANY, f"du:s:{game_type}:any", style=ui.SUCCESS)])
    rows.append([ui.button(texts.BACK_BTN, "du:h")])
    return InlineKeyboardMarkup(rows)


def searching_view(ticket) -> tuple[str, InlineKeyboardMarkup]:
    text = texts.DUEL_SEARCHING.format(
        game=game_label(ticket.game_type), stake=stake_label(ticket.stake), minutes=fa_num(duels.SEARCH_SECONDS // 60)
    )
    return text, InlineKeyboardMarkup([[ui.button(texts.DUEL_CANCEL_SEARCH_BTN, "du:x", style=ui.DANGER)]])


def _offer_label(value: int | None) -> str:
    return texts.DUEL_NO_OFFER if value is None else stake_label(value)


def duel_view(duel: Duel, side: str, prizes: dict | None = None) -> tuple[str, InlineKeyboardMarkup | None]:
    """پیام دوئل برای یک طرف (``a`` یا ``b``) بر اساس وضعیت فعلی."""
    me = duel.player_a if side == "a" else duel.player_b
    them = duel.player_b if side == "a" else duel.player_a
    name = escape(render.short_name(them.display_name))
    game = game_label(duel.game_type)
    if duel.status == Duel.Status.NEGOTIATING:
        mine = duel.offer_a if side == "a" else duel.offer_b
        theirs = duel.offer_b if side == "a" else duel.offer_a
        seconds = max(0, int((duel.expires_at - timezone.now()).total_seconds()))
        text = texts.DUEL_FOUND.format(
            game=game, name=name, level=fa_num(them.level), mine=_offer_label(mine), theirs=_offer_label(theirs),
            seconds=fa_num(seconds),
        )  # fmt: skip
        rows = []
        if theirs is not None and theirs != mine:
            rows.append([ui.button(texts.DUEL_ACCEPT_BTN.format(amount=stake_label(theirs)), f"du:a:{duel.pk}", style=ui.SUCCESS)])
        offers = [
            ui.button(("• " if s == mine else "") + stake_label(s), f"du:o:{duel.pk}:{s}", style=ui.PRIMARY)
            for s in duels.STAKE_CHOICES
        ]
        rows += ui.rows(offers, 3)
        rows.append([ui.button(texts.DUEL_LEAVE_BTN, f"du:c:{duel.pk}", style=ui.DANGER)])
        return text, InlineKeyboardMarkup(rows)
    if duel.status == Duel.Status.PLAYING:
        stake = duel.stake or 0
        line = texts.DUEL_STAKE_LINE.format(stake=fa_num(stake), prize=fa_num(stake * 2)) if stake else texts.DUEL_FREE_LINE
        text = texts.DUEL_STARTED.format(game=game, name=name, stake_line=line)
        keyboard = None
        if render.arcade_ready() and duel.match is not None:
            web_app = WebAppInfo(url=render.game_page_url(duel.match.token))
            keyboard = InlineKeyboardMarkup([[ui.button(texts.DUEL_OPEN_BTN, web_app=web_app, style=ui.SUCCESS)]])
        return text, keyboard
    again = InlineKeyboardMarkup([[ui.button(texts.DUEL_AGAIN_BTN, "du:h", style=ui.PRIMARY)]])
    if duel.status == Duel.Status.FINISHED:
        mine, theirs = (prizes or {}).get(me.pk, (0, 0)), (prizes or {}).get(them.pk, (0, 0))
        prize = texts.DUEL_PRIZE.format(amount=fa_num(mine[0])) if mine[0] else ""
        if mine[1] == theirs[1]:
            text = texts.DUEL_DRAW.format(game=game, name=name, prize=prize)
        elif mine[1] < theirs[1]:
            text = texts.DUEL_WON.format(game=game, name=name, prize=prize)
        else:
            text = texts.DUEL_LOST.format(game=game, name=name)
        return text, again
    reason = duel.cancel_reason
    if reason.startswith("left_"):
        reason = "me" if reason == f"left_{side}" else "them"
    return texts.DUEL_CANCELLED.format(reason=texts.DUEL_CANCEL_REASONS.get(reason, "")), again


def error_text(exc: duels.DuelError) -> str:
    return texts.DUEL_ERRORS.get(exc.code, texts.ERROR_GENERIC)


@db
def load_duel(duel_id: int) -> tuple[Duel, dict]:
    """دوئل با بازیکن‌ها و (اگر تمام شده) جایزه و رتبه‌ی هر نفر: ``{user_id: (prize, rank)}``."""
    duel = Duel.objects.select_related("player_a", "player_b", "match").get(pk=duel_id)
    prizes = {}
    if duel.match_id:
        prizes = {
            uid: (prize, rank or 0)
            for uid, prize, rank in MatchPlayer.objects.filter(match_id=duel.match_id).values_list("user_id", "prize", "rank")
        }
    return duel, prizes


# ------------------------------------------------------------------ اجرای دوره‌ای
class DuelRunner:
    def __init__(self, application):
        self.application = application
        self.bot = application.bot

    def start(self) -> None:
        self.application.job_queue.run_repeating(self._job, interval=POLL_SECONDS, first=POLL_SECONDS, name="duels")

    async def _job(self, _context) -> None:
        try:
            await self.tick()
        except Exception:
            logger.exception("duel tick failed")

    async def tick(self) -> None:
        for ticket in await db(duels.expire)():
            await self._show(ticket.user.tg_id, ticket.message_id, texts.DUEL_SEARCH_EXPIRED, None)
        for duel_id in await db(_playing_ids)():
            try:
                await db(duels.finish_if_over)(duel_id)
            except Exception:
                logger.exception("duel finish failed", extra={"duel": duel_id})
        for duel_id in await db(_changed_ids)():
            await self.notify(duel_id)

    async def notify(self, duel_id: int) -> None:
        """پیام هر دو طرف را با وضعیت فعلی دوئل به‌روز می‌کند (یا برای شروع/پایان پیام تازه می‌فرستد)."""
        duel, prizes = await load_duel(duel_id)
        fresh = duel.status != Duel.Status.NEGOTIATING  # شروع، پایان و لغو اعلان تازه دارند
        for side in ("a", "b"):
            user = duel.player_a if side == "a" else duel.player_b
            text, keyboard = duel_view(duel, side, prizes)
            message_id = getattr(duel, f"message_{side}")
            if fresh or message_id is None:
                if message_id is not None and duel.status != Duel.Status.NEGOTIATING:
                    # دکمه‌های پیام توافق قبلی غیرفعال می‌شود تا کسی روی پیام کهنه کلیک نکند
                    await tg_call(self.bot.edit_message_reply_markup, chat_id=user.tg_id, message_id=message_id)
                sent = await tg_call(
                    self.bot.send_message, user.tg_id, text, parse_mode="HTML", reply_markup=keyboard
                )
                new_id = sent.message_id if sent else None
                if duel.status in (Duel.Status.NEGOTIATING, Duel.Status.PLAYING) and new_id:
                    await db(duels.set_duel_message)(duel.pk, side, new_id)
            else:
                await self._show(user.tg_id, message_id, text, keyboard)
        await db(_mark_notified)(duel.pk, duel.version)

    async def _show(self, chat_id: int, message_id: int | None, text: str, keyboard) -> None:
        if message_id is None:
            await tg_call(self.bot.send_message, chat_id, text, parse_mode="HTML", reply_markup=keyboard)
            return
        await tg_call(
            self.bot.edit_message_text,
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )


def _playing_ids() -> list[int]:
    return list(Duel.objects.filter(status=Duel.Status.PLAYING).values_list("pk", flat=True))


def _changed_ids() -> list[int]:
    from django.db.models import F

    return list(Duel.objects.exclude(notified_version=F("version")).order_by("pk").values_list("pk", flat=True)[:50])


def _mark_notified(duel_id: int, version: int) -> None:
    Duel.objects.filter(pk=duel_id, version=version).update(notified_version=version)
