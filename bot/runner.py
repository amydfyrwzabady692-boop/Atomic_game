"""مدیریت چرخه‌ی زنده‌ی مسابقه‌ها در پروسه‌ی ربات: لابی ← اجرا ← پرداخت.

وضعیت پایدار (بازیکن‌ها، pot، وضعیت مسابقه) همیشه در دیتابیس است؛ این‌جا فقط
وضعیت زنده‌ی بازی و تایمرها نگه داشته می‌شود. بعد از ری‌استارت ``recover`` مسابقه‌های
نیمه‌کاره را از DB می‌خواند: لابی‌ها و مسابقه‌های آرکید ادامه پیدا می‌کنند و بازی‌های
متنیِ در حال اجرا لغو می‌شوند و ورودی‌ها برمی‌گردد.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from html import escape

from django.utils import timezone
from telegram import InlineKeyboardMarkup, InputMediaPhoto

from arcade import board as live_board
from arcade import services as arcade_services
from core import texts
from core.models import TelegramUser
from core.redis import get_redis
from core.texts import fa_num
from games import config as game_config
from games.catalog import GameInfo, get_info
from games.chess import live as chess_live
from games.chess.engine import Move, square_name
from games.chess.render import render_board
from games.content.provider import DbContentProvider, NoContent
from games.engine import services
from games.engine.base import BaseGame, IncomingCallback, IncomingMessage, Player
from games.engine.payout import Standing
from games.engine.registry import get_game
from games.engine.services import MatchError
from games.models import ACTIVE_STATUSES, Match, MatchPlayer, MatchStatus

from . import cards, render, ui
from .db import db
from .tg import EditQueue, tg_call

logger = logging.getLogger(__name__)

LOBBY_REFRESH_SECONDS = 10
LIVE_POLL_SECONDS = 2
LIVE_EDIT_MIN_GAP = 3  # فاصله‌ی ویرایش عکس صفحه در گروه (حد نرخ تلگرام)
ARCADE_POLL_SECONDS = 5
ARCADE_FLASH_MIN_GAP = 20
WATCHDOG_SECONDS = 15


@dataclass
class ActiveMatch:
    match_id: int
    chat_id: int
    info: GameInfo
    creator_tg_id: int
    phase: str = "lobby"  # lobby | running | done
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    lobby_message_id: int | None = None
    game: BaseGame | None = None
    ctx: TelegramGameContext | None = None
    players_by_tg: dict[int, Player] = field(default_factory=dict)
    jobs: dict[str, object] = field(default_factory=dict)
    ending: bool = False
    # آرکید
    token: str = ""
    board_message_id: int | None = None
    last_board: str = ""
    leader: tuple[int, int] | None = None
    last_flash_at: float = 0.0
    flash: str = ""
    # بازی دونفره‌ی گرافیکی (شطرنج در مینی‌اپ)
    live_version: int = 0
    live_edit_at: float = 0.0


class TelegramGameContext:
    """پیاده‌سازی ``GameContext`` روی تلگرام."""

    def __init__(self, manager: MatchManager, active: ActiveMatch, players: list[Player], options: dict, seed: int):
        self.manager = manager
        self.active = active
        self.players = players
        self.options = options
        self.rng = random.Random(seed)
        self.content = DbContentProvider()
        self.event_time: float | None = None
        self._seq = 0

    @property
    def bot(self):
        return self.manager.bot

    def now(self) -> float:
        if self.event_time is not None:
            return self.event_time
        return time.time()

    def _markup(self, buttons):
        if not buttons:
            return None
        prefix = f"g:{self.active.match_id}:"
        return InlineKeyboardMarkup(
            [
                [ui.button(cell[0], prefix + cell[1], style=getattr(cell, "style", "")) for cell in row]
                for row in buttons
            ]
        )

    async def send(self, text, buttons=None) -> int:
        message = await tg_call(
            self.bot.send_message,
            self.active.chat_id,
            text,
            parse_mode="HTML",
            reply_markup=self._markup(buttons),
            disable_web_page_preview=True,
        )
        return message.message_id if message else 0

    async def edit(self, message_id, text, buttons=None, urgent: bool = False) -> None:
        if message_id:
            self.manager.edits.edit(self.active.chat_id, message_id, text, self._markup(buttons), urgent=urgent)

    async def send_photo(self, image: bytes, caption: str = "", buttons=None) -> int:
        message = await tg_call(
            self.bot.send_photo,
            self.active.chat_id,
            image,
            caption=caption or None,
            parse_mode="HTML",
            reply_markup=self._markup(buttons),
        )
        return message.message_id if message else 0

    async def edit_photo(self, message_id: int, image: bytes, caption: str = "", buttons=None) -> None:
        if not message_id:
            return
        await tg_call(
            self.bot.edit_message_media,
            chat_id=self.active.chat_id,
            message_id=message_id,
            media=InputMediaPhoto(image, caption=caption or None, parse_mode="HTML"),
            reply_markup=self._markup(buttons),
        )

    async def send_dice(self, emoji: str) -> int:
        message = await tg_call(self.bot.send_dice, self.active.chat_id, emoji=emoji)
        return message.dice.value if message and message.dice else 0

    async def flash(self, text: str, seconds: int = 6) -> None:
        message = await tg_call(self.bot.send_message, self.active.chat_id, text, parse_mode="HTML")
        if message:
            self.manager.delete_later(self.active.chat_id, message.message_id, seconds)

    def set_timer(self, name, seconds, callback) -> None:
        self.manager.set_game_timer(self.active, name, seconds, callback)

    def cancel_timer(self, name) -> None:
        self.manager.cancel_job(self.active, f"game:{name}")

    async def end_game(self) -> None:
        self.active.ending = True


class MatchManager:
    def __init__(self, application):
        self.application = application
        self.bot = application.bot
        self.jobs = application.job_queue
        self.edits = EditQueue(self.bot)
        self.active: dict[int, ActiveMatch] = {}  # chat_id → مسابقه‌ی فعال

    @property
    def username(self) -> str:
        return self.application.bot_data.get("username") or render.bot_username()

    async def shutdown(self) -> None:
        """قبل از بسته شدن حلقه‌ی رویداد، ویرایش‌های در صف را لغو می‌کند."""
        await self.edits.close()

    # ================================================================ ابزار زمان‌بندی
    def _schedule(self, active: ActiveMatch, name: str, seconds: float, coro_fn, repeat: bool = False):
        self.cancel_job(active, name)

        async def run(_context):
            if not repeat:
                active.jobs.pop(name, None)
            try:
                await coro_fn()
            except Exception:
                logger.exception("scheduled job failed", extra={"match_id": active.match_id, "job": name})

        job_name = f"m{active.match_id}:{name}"
        if repeat:
            job = self.jobs.run_repeating(run, interval=seconds, first=seconds, name=job_name)
        else:
            job = self.jobs.run_once(run, when=max(seconds, 0.05), name=job_name)
        active.jobs[name] = job

    def cancel_job(self, active: ActiveMatch, name: str) -> None:
        job = active.jobs.pop(name, None)
        if job is not None:
            job.schedule_removal()

    def _cancel_all_jobs(self, active: ActiveMatch) -> None:
        for name in list(active.jobs):
            self.cancel_job(active, name)

    def delete_later(self, chat_id: int, message_id: int, seconds: float) -> None:
        async def run(_context):
            await tg_call(self.bot.delete_message, chat_id, message_id)

        self.jobs.run_once(run, when=seconds)

    def set_game_timer(self, active: ActiveMatch, name: str, seconds: float, callback) -> None:
        async def fire():
            await self._dispatch(active, callback)

        self._schedule(active, f"game:{name}", seconds, fire)

    # ================================================================ لابی
    async def create_lobby(
        self,
        group,
        creator: TelegramUser,
        info: GameInfo,
        *,
        fee: int,
        split: list[int],
        join_seconds: int,
        options: dict,
        menu_message_id: int | None = None,
    ) -> ActiveMatch:
        """مسابقه را می‌سازد و پیام لابی را نمایش می‌دهد. قفل Redis جلوی ساخت همزمان را می‌گیرد."""
        redis = get_redis()
        lock_key = f"lock:create:{group.chat_id}"
        if not await redis.set(lock_key, "1", nx=True, ex=15):
            raise MatchError("active_match_exists")
        try:
            if group.chat_id in self.active:
                raise MatchError("active_match_exists")
            # تعداد شرکت‌کننده و فعال بودن بازی همین لحظه از تنظیمات پنل ادمین خوانده می‌شود
            await db(game_config.reload)()
            info = get_info(info.key) or info
            if not info.enabled:
                raise MatchError("game_disabled")
            match = await db(services.create_match)(
                group,
                creator,
                info.key,
                entry_fee=fee,
                prize_split=split,
                join_seconds=join_seconds,
                min_players=info.min_players,
                max_players=info.max_players,
                options=options,
            )
            active = ActiveMatch(match.pk, group.chat_id, info, creator.tg_id, token=match.token)
            self.active[group.chat_id] = active
        finally:
            await redis.delete(lock_key)

        text = render.lobby_text(match, info, [], join_seconds)
        keyboard = render.lobby_keyboard(match.pk, self.username, info.key)
        message_id = None
        if menu_message_id:
            edited = await tg_call(
                self.bot.edit_message_text,
                chat_id=group.chat_id,
                message_id=menu_message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            message_id = menu_message_id if edited else None
        if message_id is None:
            message = await tg_call(
                self.bot.send_message, group.chat_id, text, parse_mode="HTML", reply_markup=keyboard
            )
            message_id = message.message_id if message else None
        active.lobby_message_id = message_id
        if message_id:
            await db(services.set_lobby_message)(match.pk, message_id)
        self._arm_lobby(active, join_seconds)
        logger.info("lobby created", extra={"match_id": match.pk, "chat_id": group.chat_id, "game": info.key})
        return active

    def _arm_lobby(self, active: ActiveMatch, remaining: float) -> None:
        self._schedule(active, "lobby_close", remaining, lambda: self.close_lobby(active))
        self._schedule(active, "lobby_refresh", LOBBY_REFRESH_SECONDS, lambda: self.refresh_lobby(active), repeat=True)
        self._arm_watchdog(active)

    def _arm_watchdog(self, active: ActiveMatch) -> None:
        self._schedule(active, "watchdog", WATCHDOG_SECONDS, lambda: self.watchdog(active), repeat=True)

    async def watchdog(self, active: ActiveMatch) -> None:
        """اگر مسابقه بیرون از ربات لغو شده باشد (اکشن پنل ادمین)، اجرای زنده را هم متوقف می‌کند."""
        if active.phase == "done":
            return
        match = await db(Match.objects.get)(pk=active.match_id)
        if match.status == MatchStatus.CANCELLED:
            await self.cancel(active, match.cancel_reason or "admin")

    @staticmethod
    @db
    def _lobby_snapshot(match_id: int):
        match = Match.objects.get(pk=match_id)
        names = [e.user.display_name for e in match.players.select_related("user")]
        remaining = int((match.join_deadline - timezone.now()).total_seconds())
        return match, names, remaining

    async def refresh_lobby(self, active: ActiveMatch, urgent: bool = False) -> None:
        if active.phase != "lobby" or not active.lobby_message_id:
            return
        match, names, remaining = await self._lobby_snapshot(active.match_id)
        if match.status != MatchStatus.LOBBY:
            return
        self.edits.edit(
            active.chat_id,
            active.lobby_message_id,
            render.lobby_text(match, active.info, names, remaining),
            render.lobby_keyboard(active.match_id, self.username, active.info.key),
            urgent=urgent,
        )

    async def join(self, active: ActiveMatch, user: TelegramUser) -> str:
        """کاربر را عضو می‌کند. متن کوتاهی برای ``answerCallbackQuery`` برمی‌گرداند یا ``MatchError`` می‌دهد."""
        if active.phase != "lobby":
            raise MatchError("lobby_closed")
        match = await db(services.join_match)(active.match_id, user)
        await self.refresh_lobby(active)
        count = await db(lambda: MatchPlayer.objects.filter(match_id=active.match_id).count())()
        if count >= match.max_players:
            # ظرفیت پر شد: منتظر پایان زمان نمی‌مانیم
            self._schedule(active, "lobby_close", 0.5, lambda: self.close_lobby(active))
        return texts.JOINED_OK

    async def close_lobby(self, active: ActiveMatch) -> None:
        async with active.lock:
            if active.phase != "lobby":
                return
            self.cancel_job(active, "lobby_close")
            self.cancel_job(active, "lobby_refresh")
            info = active.info
            play_seconds = None
            if info.is_arcade:
                match_row = await db(Match.objects.get)(pk=active.match_id)
                play_seconds = int(match_row.options.get("window_minutes") or info.suggested_minutes) * 60
            try:
                match = await db(services.start_match)(active.match_id, play_seconds)
            except MatchError as exc:
                reason = "not_enough_players" if exc.code == "not_enough_players" else "error"
                await self._cancel_locked(active, reason)
                return
            entries = await db(lambda: list(match.players.select_related("user")))()
            # نام‌های خیلی بلند کوتاه می‌شوند تا هیچ پیام بازی از سقف طول تلگرام رد نشود
            players = [Player(e.user_id, e.user.tg_id, render.short_name(e.user.display_name)) for e in entries]
            active.players_by_tg = {p.tg_id: p for p in players}
            active.phase = "running"
            if active.lobby_message_id:
                await self.edits.flush_now(active.chat_id, active.lobby_message_id)
                await tg_call(
                    self.bot.edit_message_text,
                    chat_id=active.chat_id,
                    message_id=active.lobby_message_id,
                    text=texts.MATCH_STARTING.format(
                        title=info.title_fa + render.variant_suffix(info, match.options),
                        players=render.names_line([p.name for p in players]),
                        pot=fa_num(match.pot),
                    ),
                    parse_mode="HTML",
                )
            logger.info("match started", extra={"match_id": match.pk, "players": len(players), "pot": match.pot})
            if info.is_arcade:
                await self._start_arcade(active, match)
                return
            if info.key in live_board.LIVE_GAMES and render.arcade_ready():
                # صفحه‌ی گرافیکی در مینی‌اپ؛ بدون مینی‌اپ همان نسخه‌ی داخل گفت‌وگو اجرا می‌شود
                await self._start_live(active, match, players)
                return
            cls = get_game(info.key)
            active.ctx = TelegramGameContext(self, active, players, dict(match.options), match.seed)
            active.game = cls(active.ctx)
            await self._run_locked(active, active.game.start)

    # ================================================================ لغو
    async def cancel(self, active: ActiveMatch, reason: str) -> None:
        async with active.lock:
            await self._cancel_locked(active, reason)

    async def _cancel_locked(self, active: ActiveMatch, reason: str) -> None:
        if active.phase == "done":
            return
        was_lobby = active.phase == "lobby"
        active.phase = "done"
        self._cancel_all_jobs(active)
        self.active.pop(active.chat_id, None)
        match, refunded = await db(services.cancel_match)(active.match_id, reason)
        # اگر لغو قبلاً در دیتابیس انجام شده (پنل ادمین)، ورودی‌ها همان‌جا برگشته‌اند
        refund_note = any(e.paid_fee for e in refunded) or (reason == "admin" and match.entry_fee > 0)
        text = render.cancelled_text(reason, refund_note)
        if was_lobby and active.lobby_message_id:
            self.edits.forget(active.chat_id, active.lobby_message_id)
            edited = await tg_call(
                self.bot.edit_message_text,
                chat_id=active.chat_id,
                message_id=active.lobby_message_id,
                text=text,
                parse_mode="HTML",
            )
            if edited:
                logger.info("match cancelled", extra={"match_id": active.match_id, "reason": reason})
                return
        if active.board_message_id:
            self.edits.forget(active.chat_id, active.board_message_id)
            await tg_call(
                self.bot.edit_message_reply_markup, chat_id=active.chat_id, message_id=active.board_message_id
            )
        await tg_call(self.bot.send_message, active.chat_id, text, parse_mode="HTML")
        logger.info("match cancelled", extra={"match_id": active.match_id, "reason": reason})

    # ================================================================ اجرای بازی متنی
    async def _dispatch(self, active: ActiveMatch, coro_fn, *args) -> None:
        async with active.lock:
            await self._run_locked(active, coro_fn, *args)

    async def _run_locked(self, active: ActiveMatch, coro_fn, *args) -> None:
        if active.phase != "running":
            return
        try:
            await coro_fn(*args)
        except NoContent:
            logger.error("not enough content", extra={"match_id": active.match_id, "game": active.info.key})
            await self._cancel_locked(active, "no_content")
            return
        except Exception:
            logger.exception("game crashed", extra={"match_id": active.match_id, "game": active.info.key})
            await self._cancel_locked(active, "error")
            return
        if active.ending and active.phase == "running":
            await self._finalize_text_game(active)

    async def on_message(self, active: ActiveMatch, player: Player, text: str, message_id: int, date: float) -> None:
        if active.game is None:
            return
        ctx = active.ctx

        async def handle():
            # زمان رویداد = message.date به‌علاوه‌ی ترتیب رسیدن (برای شکستن تساوی در همان ثانیه)
            ctx._seq += 1
            ctx.event_time = date + (ctx._seq % 1_000_000) * 1e-6
            try:
                await active.game.on_message(IncomingMessage(player, text, message_id, date))
            finally:
                ctx.event_time = None

        await self._dispatch(active, handle)

    async def on_callback(self, active: ActiveMatch, tg_id: int, data: str, message_id: int, answer) -> None:
        if active.game is None:
            await answer("", False)
            return
        cb = IncomingCallback(active.players_by_tg.get(tg_id), data, message_id, answer)

        async def handle():
            await active.game.on_callback(cb)

        await self._dispatch(active, handle)
        if not cb.answered:
            await answer("", False)

    async def _finalize_text_game(self, active: ActiveMatch) -> None:
        active.phase = "done"
        self._cancel_all_jobs(active)
        self.active.pop(active.chat_id, None)
        standings = await active.game.finish()
        await self._payout(active, standings)

    async def _payout(self, active: ActiveMatch, standings: list[Standing]) -> None:
        result = await db(services.finish_match)(active.match_id, standings)
        if result is None:
            return
        await self._announce_result(active, result)
        for referrer, invitee in result.referral_rewards:
            from django.conf import settings

            await tg_call(
                self.bot.send_message,
                referrer.tg_id,
                texts.REFERRAL_REWARDED.format(
                    name=escape(invitee.display_name), amount=fa_num(settings.REFERRAL_REWARD)
                ),
                parse_mode="HTML",
            )
        logger.info(
            "match finished",
            extra={"match_id": active.match_id, "pot": result.match.pot, "players": len(result.players)},
        )

    async def _announce_result(self, active: ActiveMatch, result) -> None:
        """نتیجه را با کارت تصویری سکو می‌فرستد؛ اگر کارت ساخته یا فرستاده نشد، فقط متن."""
        text = render.result_text(result, active.info)
        card = await asyncio.to_thread(cards.result_card, result, active.info)
        if card and cards.visible_length(text) <= cards.CAPTION_LIMIT:
            if await tg_call(self.bot.send_photo, active.chat_id, card, caption=text, parse_mode="HTML"):
                return
        elif card:
            # متن نتیجه از سقف کپشن بلندتر است: کارت جدا و متن کامل زیر آن
            await tg_call(self.bot.send_photo, active.chat_id, card)
        await tg_call(
            self.bot.send_message,
            active.chat_id,
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    # ================================================================ آرکید
    async def _start_arcade(self, active: ActiveMatch, match: Match) -> None:
        remaining = int((match.play_deadline - timezone.now()).total_seconds())
        text, _ = await self._arcade_board(active)
        message = await tg_call(
            self.bot.send_message,
            active.chat_id,
            text,
            parse_mode="HTML",
            reply_markup=render.arcade_keyboard(self.username, match.token, active.info.key),
            disable_web_page_preview=True,
        )
        active.board_message_id = message.message_id if message else None
        active.last_board = text
        if active.board_message_id:
            await db(services.save_state)(match.pk, {"board_message_id": active.board_message_id})
        self._arm_arcade(active, remaining)

    def _arm_arcade(self, active: ActiveMatch, remaining: float) -> None:
        self._arm_watchdog(active)
        self._schedule(active, "arcade_end", remaining, lambda: self.finish_arcade(active))
        self._schedule(active, "arcade_poll", ARCADE_POLL_SECONDS, lambda: self.poll_arcade(active), repeat=True)

    @staticmethod
    @db
    def _arcade_snapshot(match_id: int):
        match = Match.objects.get(pk=match_id)
        standings = arcade_services.match_standings(match)
        return match, standings, arcade_services.all_attempts_done(match)

    async def _arcade_board(self, active: ActiveMatch):
        match, standings, all_done = await self._arcade_snapshot(active.match_id)
        remaining = int((match.play_deadline - timezone.now()).total_seconds()) if match.play_deadline else 0
        attempts = arcade_services.attempts_allowed(match)
        top = standings[0] if standings and standings[0].score > 0 else None
        if top is not None:
            leader = (top.user_id, top.score)
            if active.leader is not None and leader != active.leader:
                now = time.monotonic()
                if now - active.last_flash_at >= ARCADE_FLASH_MIN_GAP:
                    active.last_flash_at = now
                    active.flash = texts.ARCADE_RECORD.format(name=escape(top.name), score=fa_num(top.score))
            active.leader = leader
        text = render.arcade_text(match, active.info, standings, remaining, attempts, active.flash)
        return text, all_done

    async def poll_arcade(self, active: ActiveMatch) -> None:
        if active.phase != "running":
            return
        text, all_done = await self._arcade_board(active)
        if all_done:
            await self.finish_arcade(active)
            return
        if active.board_message_id and text != active.last_board:
            active.last_board = text
            self.edits.edit(
                active.chat_id,
                active.board_message_id,
                text,
                render.arcade_keyboard(self.username, active.token, active.info.key),
            )

    async def finish_arcade(self, active: ActiveMatch) -> None:
        async with active.lock:
            if active.phase != "running":
                return
            active.phase = "done"
            self._cancel_all_jobs(active)
            self.active.pop(active.chat_id, None)
            match, standings, _ = await self._arcade_snapshot(active.match_id)
            if active.board_message_id:
                self.edits.forget(active.chat_id, active.board_message_id)
                await tg_call(
                    self.bot.edit_message_reply_markup, chat_id=active.chat_id, message_id=active.board_message_id
                )
            await self._payout(active, [Standing(s.user_id, s.score, s.reached_at) for s in standings])

    # ================================================================ شطرنج زنده (مینی‌اپ)
    def _live_view(self, active: ActiveMatch, state: dict) -> tuple[bytes, str]:
        """عکس صفحه و متن وضعیت برای پیام گروه (تماشاچی‌ها همین را می‌بینند)."""
        by_id = {p.user_id: p for p in active.players_by_tg.values()}
        white, black = by_id[state["w"]], by_id[state["b"]]
        position = chess_live.position_of(state)
        over = state["over"]
        if over:
            winner = by_id.get(over["winner"])
            loser = black if winner is white else white
            if over["reason"] == "checkmate":
                status = texts.CHESS_END_MATE.format(name=winner.mention)
            elif over["reason"] == "resign":
                status = texts.CHESS_END_RESIGN.format(loser=escape(loser.name), winner=winner.mention)
            elif over["reason"] == "timeout":
                status = texts.CHESS_END_TIMEOUT.format(loser=escape(loser.name), winner=winner.mention)
            else:
                status = texts.CHESS_END_DRAW.format(reason=texts.CHESS_DRAW_REASONS.get(over["reason"], ""))
        else:
            current = white if position.turn == "w" else black
            status = texts.CHESS_TURN.format(
                name=escape(current.name),
                color=texts.CHESS_WHITE if position.turn == "w" else texts.CHESS_BLACK,
                seconds=fa_num(state["move_seconds"]),
            )
            if position.in_check():
                status += texts.CHESS_CHECK
        last, last_move = "", None
        if state["last"]:
            last_move = Move(state["last"][0], state["last"][1])
            last = texts.CHESS_LAST.format(move=f"{square_name(last_move.src)} → {square_name(last_move.dst)}")
        if not over:
            last += texts.CHESS_LIVE_HINT
        caption = texts.CHESS_CAPTION.format(
            white=escape(white.name), black=escape(black.name), status=status, last=last
        )
        return render_board(position, last_move), caption

    async def _start_live(self, active: ActiveMatch, match: Match, players: list[Player]) -> None:
        order = list(players)
        random.Random(match.seed).shuffle(order)
        state = chess_live.new_state(order[0].user_id, order[1].user_id, time.time())
        await db(live_board.start)(match.pk, state)
        active.live_version = state["version"]
        image, caption = await asyncio.to_thread(self._live_view, active, state)
        message = await tg_call(
            self.bot.send_photo,
            active.chat_id,
            image,
            caption=caption,
            parse_mode="HTML",
            reply_markup=render.live_keyboard(self.username, match.token, active.info.key),
        )
        active.board_message_id = message.message_id if message else None
        if active.board_message_id:
            await db(live_board.remember)(match.pk, board_message_id=active.board_message_id)
        self._arm_live(active)

    def _arm_live(self, active: ActiveMatch) -> None:
        self._arm_watchdog(active)
        self._schedule(active, "live_poll", LIVE_POLL_SECONDS, lambda: self.poll_live(active), repeat=True)

    async def _edit_live(self, active: ActiveMatch, state: dict, final: bool = False) -> None:
        if not active.board_message_id:
            return
        image, caption = await asyncio.to_thread(self._live_view, active, state)
        active.live_edit_at = time.monotonic()
        await tg_call(
            self.bot.edit_message_media,
            chat_id=active.chat_id,
            message_id=active.board_message_id,
            media=InputMediaPhoto(image, caption=caption, parse_mode="HTML"),
            reply_markup=None if final else render.live_keyboard(self.username, active.token, active.info.key),
        )

    async def poll_live(self, active: ActiveMatch) -> None:
        """وضعیت بازی را از دیتابیس می‌خواند: پایان مهلت، به‌روزرسانی عکس گروه و اعلام نتیجه."""
        if active.phase != "running":
            return
        state = await db(live_board.tick)(active.match_id)
        if state is None:
            return
        if state["over"]:
            await self.finish_live(active, state)
            return
        if state["version"] != active.live_version and time.monotonic() - active.live_edit_at >= LIVE_EDIT_MIN_GAP:
            active.live_version = state["version"]
            await self._edit_live(active, state)

    async def finish_live(self, active: ActiveMatch, state: dict) -> None:
        async with active.lock:
            if active.phase != "running":
                return
            active.phase = "done"
            self._cancel_all_jobs(active)
            self.active.pop(active.chat_id, None)
            await self._edit_live(active, state, final=True)
            winner = state["over"]["winner"]
            now = time.time()
            standings = [
                Standing(uid, 1 if uid == winner else 0, now if uid == winner else None)
                for uid in (state["w"], state["b"])
            ]
            await self._payout(active, standings)

    # ================================================================ بازیابی بعد از ری‌استارت
    async def recover(self) -> None:
        matches = await db(
            lambda: list(Match.objects.filter(status__in=ACTIVE_STATUSES).select_related("group", "creator"))
        )()
        for match in matches:
            try:
                await self._recover_one(match)
            except Exception:
                logger.exception("recover failed", extra={"match_id": match.pk})
                await db(services.cancel_match)(match.pk, "restart")

    async def _recover_one(self, match: Match) -> None:
        info = get_info(match.game_type)
        chat_id = match.group.chat_id
        now = timezone.now()
        if info is None:
            await db(services.cancel_match)(match.pk, "restart")
            return
        active = ActiveMatch(
            match.pk, chat_id, info, match.creator.tg_id, lobby_message_id=match.lobby_message_id, token=match.token
        )
        if match.status == MatchStatus.LOBBY:
            self.active[chat_id] = active
            remaining = (match.join_deadline - now).total_seconds()
            if remaining <= 0:
                await self.close_lobby(active)
            else:
                self._arm_lobby(active, remaining)
            logger.info("lobby recovered", extra={"match_id": match.pk})
            return
        if info.is_arcade and match.play_deadline:
            entries = await db(lambda: list(match.players.select_related("user")))()
            active.players_by_tg = {
                e.user.tg_id: Player(e.user_id, e.user.tg_id, render.short_name(e.user.display_name)) for e in entries
            }
            active.phase = "running"
            active.board_message_id = (match.state or {}).get("board_message_id")
            self.active[chat_id] = active
            remaining = (match.play_deadline - now).total_seconds()
            if remaining <= 0:
                await self.finish_arcade(active)
            else:
                self._arm_arcade(active, remaining)
            logger.info("arcade match recovered", extra={"match_id": match.pk})
            return
        if info.key in live_board.LIVE_GAMES and (match.state or {}).get("board"):
            # وضعیت شطرنج زنده در دیتابیس است؛ بازی از همان‌جا ادامه پیدا می‌کند
            entries = await db(lambda: list(match.players.select_related("user")))()
            active.players_by_tg = {
                e.user.tg_id: Player(e.user_id, e.user.tg_id, render.short_name(e.user.display_name)) for e in entries
            }
            active.phase = "running"
            active.board_message_id = match.state.get("board_message_id")
            self.active[chat_id] = active
            self._arm_live(active)
            logger.info("live match recovered", extra={"match_id": match.pk})
            return
        # بازی متنیِ در حال اجرا قابل ادامه نیست: لغو و برگشت کامل ورودی‌ها
        active.phase = "running"
        active.lobby_message_id = None
        await self.cancel(active, "restart")
