"""چرخه‌ی مسابقه در دیتابیس: ساخت، عضویت، لغو/برگشت ورودی، شروع و پرداخت.

همه‌ی توابع sync و اتمیک‌اند؛ لایه‌ی ربات آن‌ها را با ``sync_to_async`` صدا می‌زند.
ترتیب قفل‌ها همیشه «مسابقه ← کاربر» است تا بن‌بست پیش نیاید.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import TelegramGroup, TelegramUser
from leaderboard.progress import award, check_progress_achievements, level_for_xp
from wallet.economy import ReferralResult, try_reward_referral
from wallet.models import TxType
from wallet.services import InsufficientFunds, apply_transaction

from ..models import ACTIVE_STATUSES, Match, MatchPlayer, MatchStatus
from .payout import Standing, compute_payouts, rank_standings


class MatchError(Exception):
    """خطای قابل‌نمایش به کاربر؛ ``code`` کلید متن در ``core.texts`` است."""

    def __init__(self, code: str, **context):
        super().__init__(code)
        self.code = code
        self.context = context


@dataclass
class PlayerResult:
    user: TelegramUser
    score: int
    rank: int
    prize: int
    xp: int
    leveled_up: bool = False
    achievements: list = field(default_factory=list)
    won: bool = False


@dataclass
class MatchResult:
    match: Match
    players: list[PlayerResult]
    # (نتیجه‌ی دعوت، دعوت‌شده) برای پیام به دعوت‌کننده
    referral_rewards: list[tuple[ReferralResult, TelegramUser]] = field(default_factory=list)


def create_match(
    group: TelegramGroup,
    creator: TelegramUser,
    game_type: str,
    *,
    entry_fee: int,
    prize_split: list[int],
    join_seconds: int,
    min_players: int,
    max_players: int,
    options: dict | None = None,
) -> Match:
    if not group.fee_allowed(entry_fee):
        raise MatchError("fee_not_allowed")
    try:
        with transaction.atomic():
            return Match.objects.create(
                group=group,
                creator=creator,
                game_type=game_type,
                entry_fee=entry_fee,
                prize_split=list(prize_split),
                join_deadline=timezone.now() + timedelta(seconds=join_seconds),
                min_players=min_players,
                max_players=max_players,
                options=options or {},
            )
    except IntegrityError as exc:
        raise MatchError("active_match_exists") from exc


def get_active_match(group_id: int) -> Match | None:
    return Match.objects.filter(group_id=group_id, status__in=ACTIVE_STATUSES).first()


def join_match(match_id: int, user: TelegramUser) -> Match:
    """کاربر را عضو لابی می‌کند و ورودی را کسر می‌کند. تکرار کلیک بی‌اثر است."""
    with transaction.atomic():
        match = Match.objects.select_for_update().get(pk=match_id)
        if match.status != MatchStatus.LOBBY or timezone.now() >= match.join_deadline:
            raise MatchError("lobby_closed")
        if user.is_banned:
            raise MatchError("banned")
        if not user.started_bot:
            raise MatchError("need_start")
        if MatchPlayer.objects.filter(match=match, user=user).exists():
            raise MatchError("already_joined")
        if match.players.count() >= match.max_players:
            raise MatchError("lobby_full")
        try:
            if match.entry_fee:
                apply_transaction(user, -match.entry_fee, TxType.ENTRY_FEE, f"entry:{match.pk}:{user.pk}", match)
        except InsufficientFunds as exc:
            raise MatchError("not_enough_coins", balance=exc.balance, needed=exc.needed) from exc
        MatchPlayer.objects.create(match=match, user=user, paid_fee=match.entry_fee)
        match.pot += match.entry_fee
        match.save(update_fields=["pot"])
    return match


def cancel_match(match_id: int, reason: str = "") -> tuple[Match, list[MatchPlayer]]:
    """مسابقه را لغو می‌کند و ورودی همه را کامل برمی‌گرداند. چندبار صدا زدن بی‌خطر است."""
    with transaction.atomic():
        match = Match.objects.select_for_update().get(pk=match_id)
        if match.status not in ACTIVE_STATUSES:
            return match, []
        refunded = []
        for entry in match.players.select_related("user").order_by("user_id"):
            if entry.paid_fee and not entry.refunded:
                apply_transaction(
                    entry.user, entry.paid_fee, TxType.REFUND, f"refund:{match.pk}:{entry.user_id}", match
                )
                entry.refunded = True
                entry.save(update_fields=["refunded"])
            refunded.append(entry)
        match.status = MatchStatus.CANCELLED
        match.cancel_reason = reason[:64]
        match.pot = 0
        match.finished_at = timezone.now()
        match.save(update_fields=["status", "cancel_reason", "pot", "finished_at"])
    return match, refunded


def start_match(match_id: int, play_seconds: int | None = None) -> Match:
    """لابی را می‌بندد. اگر بازیکن کافی نباشد ``MatchError('not_enough_players')`` می‌دهد
    (فراخواننده باید ``cancel_match`` را صدا بزند)."""
    with transaction.atomic():
        match = Match.objects.select_for_update().get(pk=match_id)
        if match.status != MatchStatus.LOBBY:
            raise MatchError("lobby_closed")
        if match.players.count() < match.min_players:
            raise MatchError("not_enough_players")
        now = timezone.now()
        match.status = MatchStatus.RUNNING
        match.started_at = now
        update = ["status", "started_at"]
        if play_seconds:
            match.play_deadline = now + timedelta(seconds=play_seconds)
            update.append("play_deadline")
        match.save(update_fields=update)
    return match


def finish_match(match_id: int, standings: list[Standing]) -> MatchResult | None:
    """رتبه‌بندی، تقسیم pot، XP و دستاوردها. فقط یک بار اثر می‌کند."""
    with transaction.atomic():
        match = Match.objects.select_for_update().get(pk=match_id)
        if match.status != MatchStatus.RUNNING:
            return None
        entries = {e.user_id: e for e in match.players.select_related("user")}
        # همه‌ی کاربرانی که این تراکنش قفل می‌کند (بازیکن‌ها و دعوت‌کننده‌ی آن‌هایی که جایزه‌ی دعوتشان
        # مانده) یک‌جا و به ترتیب شناسه قفل می‌شوند؛ دو مسابقه‌ی هم‌زمان با بازیکن مشترک به بن‌بست نمی‌خورند.
        referrers = {
            e.user.referred_by_id for e in entries.values() if e.user.referred_by_id and not e.user.referral_rewarded
        }
        list(
            TelegramUser.objects.select_for_update()
            .filter(pk__in=set(entries) | referrers)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        given ={s.user_id: s for s in standings if s.user_id in entries}
        full = [given.get(uid) or Standing(uid, 0, None) for uid in entries]
        groups = rank_standings(full)
        # جایزه فقط به کسانی می‌رسد که امتیاز گرفته‌اند؛ امتیاز صفر یعنی باخت و سهمی ندارد.
        # اگر هیچ‌کس امتیاز نگرفت (یا بازی دونفره مساوی شد)، pot مساوی بین همه تقسیم می‌شود.
        paid_groups = [g for g in groups if g[0].score > 0] or groups
        shares = compute_payouts(match.pot, match.prize_split, [[s.user_id for s in g] for g in paid_groups])
        payouts = {uid: shares.get(uid, 0) for uid in entries}
        # بازی رایگان (ورودی صفر) فقط برای سرگرمی است: سکه، XP، برد، آمار و دستاورد ندارد
        free = match.entry_fee == 0

        results: list[PlayerResult] = []
        rank = 1
        for group in groups:
            for s in group:
                entry = entries[s.user_id]
                prize = payouts[s.user_id]
                # تساوی صفر-صفر (مثلاً وقتی هیچ‌کس بازی نکرده) «برد» حساب نمی‌شود؛
                # وگرنه می‌شد با مسابقه‌های خالی، آمار برد و جایزه‌ی دستاوردها را جمع کرد.
                scored = s.score > 0
                xp = 0 if free else settings.XP_PARTICIPATION + (settings.XP_BY_RANK.get(rank, 0) if scored else 0)
                if prize:
                    apply_transaction(entry.user, prize, TxType.PRIZE, f"prize:{match.pk}:{s.user_id}", match)
                entry.score, entry.score_at, entry.rank, entry.prize, entry.xp_gained = (
                    s.score,
                    s.reached_at,
                    rank,
                    prize,
                    xp,
                )
                entry.save(update_fields=["score", "score_at", "rank", "prize", "xp_gained"])

                user = TelegramUser.objects.select_for_update().get(pk=s.user_id)
                old_level = user.level
                won = rank == 1 and scored and not free
                if not free:
                    user.games_played += 1
                    if won:
                        user.wins += 1
                    user.xp += xp
                    user.level = level_for_xp(user.xp)
                    user.save(update_fields=["games_played", "wins", "xp", "level"])
                results.append(PlayerResult(user, s.score, rank, prize, xp, user.level > old_level, won=won))
            rank += len(group)

        match.status = MatchStatus.FINISHED
        match.finished_at = timezone.now()
        match.save(update_fields=["status", "finished_at"])

        referral_rewards = []
        for r in [] if free else results:
            r.achievements = check_progress_achievements(r.user)
            if r.won:
                extra = _special_win_achievement(match)
                if extra and (a := award(r.user, extra)):
                    r.achievements.append(a)
            referral = try_reward_referral(r.user)
            if referral:
                referral_rewards.append((referral, r.user))
        for r in results:
            r.user.refresh_from_db()
    return MatchResult(match, results, referral_rewards)


def _special_win_achievement(match: Match) -> str | None:
    if match.game_type == "quiz" and match.options.get("variant") == "freefire":
        return "quiz_freefire"
    if match.game_type.startswith("arcade_"):
        return "arcade_first"
    return None


def set_lobby_message(match_id: int, message_id: int) -> None:
    Match.objects.filter(pk=match_id).update(lobby_message_id=message_id)


def save_state(match_id: int, state: dict) -> None:
    Match.objects.filter(pk=match_id).update(state=state)
