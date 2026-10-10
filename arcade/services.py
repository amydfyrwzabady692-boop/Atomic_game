"""منطق سمت سرور بازی‌های آرکید: صدور session، تأیید امتیاز با شبیه‌سازی و جدول مسابقه."""

import secrets
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max, Min, Q
from django.utils import timezone

from core.models import TelegramUser
from games.catalog import ARCADE_PREFIX
from games.models import Match, MatchPlayer, MatchStatus

from .models import ArcadeRecord, ArcadeSession
from .sim import get_simulator


class ArcadeError(Exception):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass
class Standing:
    user_id: int
    name: str
    score: int
    reached_at: float | None
    attempts: int


def attempts_allowed(match: Match) -> int:
    return int(match.options.get("attempts") or settings.ARCADE_DEFAULT_ATTEMPTS)


def match_for_token(token: str) -> Match:
    match = Match.objects.filter(token=token).select_related("group").first()
    if match is None or not match.game_type.startswith(ARCADE_PREFIX):
        raise ArcadeError("match_not_found", 404)
    return match


def attempts_used(match: Match, user: TelegramUser) -> int:
    return ArcadeSession.objects.filter(match=match, user=user).count()


def start_session(user: TelegramUser, game_key: str | None, match_token: str | None) -> tuple[ArcadeSession, dict]:
    """یک تلاش جدید صادر می‌کند. برای مسابقه عضویت، مهلت و تعداد تلاش بررسی می‌شود."""
    if user.is_banned:
        raise ArcadeError("banned", 403)
    match = None
    options: dict = {}
    if match_token:
        with transaction.atomic():
            match = Match.objects.select_for_update().filter(token=match_token).first()
            if match is None or not match.game_type.startswith(ARCADE_PREFIX):
                raise ArcadeError("match_not_found", 404)
            if match.status != MatchStatus.RUNNING or not match.play_deadline:
                raise ArcadeError("match_not_running", 409)
            if timezone.now() >= match.play_deadline:
                raise ArcadeError("match_over", 409)
            if not MatchPlayer.objects.filter(match=match, user=user).exists():
                raise ArcadeError("not_a_player", 403)
            if attempts_used(match, user) >= attempts_allowed(match):
                raise ArcadeError("no_attempts_left", 409)
            game_key = match.game_type[len(ARCADE_PREFIX) :]
            options = match.options
            session = ArcadeSession.objects.create(user=user, match=match, game_key=game_key, seed=match.seed)
    else:
        if get_simulator(game_key or "") is None:
            raise ArcadeError("unknown_game", 404)
        seed = secrets.randbelow(2**31 - 1) + 1
        session = ArcadeSession.objects.create(user=user, game_key=game_key, seed=seed)
    sim = get_simulator(session.game_key)
    if sim is None:
        raise ArcadeError("unknown_game", 404)
    return session, sim.config(session.seed, options)


def _suspicious_gaps(inputs: list, min_gap: int) -> int:
    if not min_gap:
        return 0
    return sum(1 for a, b in zip(inputs, inputs[1:], strict=False) if b[0] - a[0] < min_gap)


def submit_session(
    user: TelegramUser, session_id: str, inputs, duration_ms, claimed_score=None
) -> ArcadeSession:
    """لاگ ورودی را دوباره در سرور شبیه‌سازی می‌کند و امتیاز تأییدشده را ثبت می‌کند.

    هر session فقط یک بار مصرف می‌شود. امتیاز هرگز از کلاینت پذیرفته نمی‌شود.
    """
    try:
        with transaction.atomic():
            session = (
                ArcadeSession.objects.select_for_update(of=("self",))
                .select_related("match")
                .get(pk=session_id, user=user)
            )
            if session.status != ArcadeSession.Status.OPEN:
                raise ArcadeError("session_already_used", 409)
            now = timezone.now()
            session.submitted_at = now
            session.claimed_score = claimed_score if isinstance(claimed_score, int) else None
            sim = get_simulator(session.game_key)
            elapsed_ms = int((now - session.started_at).total_seconds() * 1000)
            options = session.match.options if session.match else {}

            reason = sim.validate_inputs(inputs, duration_ms)
            if reason is None and duration_ms > elapsed_ms + settings.ARCADE_SESSION_GRACE_MS:
                reason = "faster_than_real_time"  # بازی نمی‌تواند طولانی‌تر از زمان واقعی سپری‌شده باشد
            if reason is None and session.match and session.match.play_deadline:
                if session.started_at >= session.match.play_deadline:
                    reason = "after_deadline"
            if reason is None:
                fast = _suspicious_gaps(inputs, sim.MIN_INPUT_GAP_MS)
                if fast > max(3, len(inputs) // 10):
                    reason = "inhuman_input"
                elif fast:
                    session.flagged = True

            if reason is not None:
                session.status = ArcadeSession.Status.REJECTED
                session.reject_reason = reason
                session.flagged = True
                session.input_log = _compact_log(inputs)
                session.save()
                return session

            result = sim.simulate(session.seed, inputs, duration_ms, options)
            session.input_log = inputs
            session.verified_score = result.score
            session.level_reached = result.level
            session.duration_ms = result.duration_ms
            session.status = ArcadeSession.Status.VERIFIED
            if session.claimed_score is not None and session.claimed_score != result.score:
                session.flagged = True
                session.reject_reason = "claim_mismatch"
            # بازی آهسته‌شده (slow motion): زمان واقعی خیلی بیشتر از زمان بازی است
            if elapsed_ms > result.duration_ms * 3 // 2 + 30_000:
                session.flagged = True
                session.reject_reason = session.reject_reason or "slower_than_real_time"
            session.save()

            record, _ = ArcadeRecord.objects.select_for_update().get_or_create(
                user=user, game_key=session.game_key
            )
            if result.score > record.best_score:
                record.best_score = result.score
                record.level_reached = result.level
                record.save()
            return session
    except (ArcadeSession.DoesNotExist, ValueError, ValidationError) as exc:
        raise ArcadeError("session_not_found", 404) from exc


def _compact_log(inputs):
    """لاگ ردشده را برای بررسی ادمین نگه می‌داریم ولی اگر خیلی بزرگ/خراب بود کوتاهش می‌کنیم."""
    if isinstance(inputs, list):
        return inputs[:2000]
    return None


def match_standings(match: Match) -> list[Standing]:
    """بهترین امتیاز تأییدشده‌ی هر بازیکن، مرتب‌شده. تساوی با زمان ثبت زودتر شکسته می‌شود."""
    entries = list(match.players.select_related("user"))
    stats = {
        row["user_id"]: row
        for row in ArcadeSession.objects.filter(match=match)
        .values("user_id")
        .annotate(
            attempts=Count("id"),
            best=Max("verified_score", filter=Q(status=ArcadeSession.Status.VERIFIED)),
        )
    }
    standings = []
    for entry in entries:
        row = stats.get(entry.user_id, {})
        best = row.get("best") or 0
        reached = None
        if best:
            first = ArcadeSession.objects.filter(
                match=match, user_id=entry.user_id, status=ArcadeSession.Status.VERIFIED, verified_score=best
            ).aggregate(t=Min("submitted_at"))["t"]
            reached = first.timestamp() if first else None
        standings.append(
            Standing(entry.user_id, entry.user.display_name, int(best), reached, int(row.get("attempts", 0)))
        )
    standings.sort(key=lambda s: (-s.score, s.reached_at if s.reached_at is not None else float("inf")))
    return standings


def all_attempts_done(match: Match) -> bool:
    """همه‌ی بازیکن‌ها همه‌ی تلاش‌هایشان را فرستاده‌اند؟ (برای پایان زودهنگام مسابقه)"""
    allowed = attempts_allowed(match)
    player_ids = list(match.players.values_list("user_id", flat=True))
    done = (
        ArcadeSession.objects.filter(match=match)
        .exclude(status=ArcadeSession.Status.OPEN)
        .values("user_id")
        .annotate(n=Count("id"))
    )
    counts = {row["user_id"]: row["n"] for row in done}
    return bool(player_ids) and all(counts.get(uid, 0) >= allowed for uid in player_ids)
