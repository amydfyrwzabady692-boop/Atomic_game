"""حریف تصادفی: صف جستجو، توافق دو طرف روی مقدار سکه و اجرای دوئل روی صفحه‌ی بازی مینی‌اپ.

جریان:
۱. ``search``: کاربر بازی و (اختیاری) مقدار سکه را انتخاب می‌کند. اگر کسی با همان بازی و مقدار سازگار
   منتظر باشد جفت می‌شوند؛ وگرنه درخواست در صف می‌ماند (حداکثر ``SEARCH_SECONDS``).
   سازگار یعنی: هر دو همان مقدار را خواسته‌اند، یا حداقل یکی «فرقی نمی‌کند» گفته است.
۲. ``offer``/``accept``: هر طرف مقدار پیشنهادی‌اش را می‌گوید یا پیشنهاد حریف را قبول می‌کند. وقتی دو
   پیشنهاد برابر شد (از جمله ۰ = بدون سکه) بازی شروع می‌شود؛ اگر هر دو از اول همان مقدار را خواسته
   باشند بلافاصله. اگر تا ``NEGOTIATE_SECONDS`` توافق نشد دوئل لغو می‌شود.
۳. ``_start``: یک ``Match`` بدون گروه ساخته می‌شود؛ ورودی هر دو از مسیر عادی ledger کم می‌شود و کل
   جایزه به برنده می‌رسد (در تساوی نصف‌نصف). بازی روی همان صفحه‌های شطرنج/دوز/پوکر مینی‌اپ است و
   ربات (``bot.duels``) مهلت‌ها، پایان بازی و پرداخت را دنبال می‌کند.

همه‌ی توابع sync و اتمیک‌اند؛ ربات آن‌ها را با ``db(...)`` صدا می‌زند و API مینی‌اپ مستقیم.
"""

import random
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from core.models import TelegramUser

from .catalog import catalog
from .engine import services
from .engine.payout import Standing
from .engine.services import MatchError
from .models import Duel, DuelTicket, Match, MatchStatus

DUEL_GAMES = ("chess", "tictactoe", "connect4", "poker")
STAKE_CHOICES = (0, 50, 100, 250, 500, 1000)
MAX_STAKE = 1_000_000
SEARCH_SECONDS = 300
NEGOTIATE_SECONDS = 120


class DuelError(Exception):
    """خطای قابل‌نمایش؛ ``code`` کلید متن است."""

    def __init__(self, code: str, **context):
        super().__init__(code)
        self.code = code
        self.context = context


def available_games() -> list:
    games = catalog()
    return [games[key] for key in DUEL_GAMES if key in games]


def _check_stake(stake) -> int | None:
    if stake is None:
        return None
    if isinstance(stake, bool) or not isinstance(stake, int) or not 0 <= stake <= MAX_STAKE:
        raise DuelError("bad_stake")
    return stake


def active_duel(user_id: int) -> Duel | None:
    return (
        Duel.objects.filter(Q(player_a_id=user_id) | Q(player_b_id=user_id))
        .filter(status__in=[Duel.Status.NEGOTIATING, Duel.Status.PLAYING])
        .select_related("player_a", "player_b", "match")
        .order_by("-pk")
        .first()
    )


def searching_ticket(user_id: int) -> DuelTicket | None:
    return DuelTicket.objects.filter(user_id=user_id, status=DuelTicket.Status.SEARCHING).first()


# ------------------------------------------------------------------ جستجو
def search(user: TelegramUser, game_type: str, stake: int | None, now=None) -> DuelTicket | Duel:
    """درخواست جستجو. اگر حریف سازگار منتظر بود ``Duel`` برمی‌گرداند، وگرنه ``DuelTicket``."""
    now = now or timezone.now()
    stake = _check_stake(stake)
    if game_type not in DUEL_GAMES or game_type not in catalog():
        raise DuelError("bad_game")
    user.refresh_from_db(fields=["coins", "is_banned", "started_bot"])
    if user.is_banned:
        raise DuelError("banned")
    if not user.started_bot:
        raise DuelError("need_start")
    if stake and user.coins < stake:
        raise DuelError("not_enough_coins", balance=user.coins, needed=stake)
    if active_duel(user.pk) is not None:
        raise DuelError("already_in_duel")
    with transaction.atomic():
        # جستجوی قبلی همین کاربر (اگر بود) با جستجوی تازه جایگزین می‌شود
        DuelTicket.objects.select_for_update().filter(user=user, status=DuelTicket.Status.SEARCHING).update(
            status=DuelTicket.Status.CANCELLED
        )
        waiting = list(
            DuelTicket.objects.select_for_update()
            .filter(status=DuelTicket.Status.SEARCHING, game_type=game_type, expires_at__gt=now)
            .exclude(user=user)
            .select_related("user")
            .order_by("created_at", "pk")
        )
        partner = _best_partner(waiting, stake)
        if partner is None:
            try:
                with transaction.atomic():
                    return DuelTicket.objects.create(
                        user=user, game_type=game_type, stake=stake, expires_at=now + timedelta(seconds=SEARCH_SECONDS)
                    )
            except IntegrityError as exc:  # کلیک دوباره‌ی هم‌زمان
                raise DuelError("already_searching") from exc
        duel = Duel.objects.create(
            game_type=game_type,
            player_a=partner.user,
            player_b=user,
            offer_a=partner.stake,
            offer_b=stake,
            message_a=partner.message_id,
            expires_at=now + timedelta(seconds=NEGOTIATE_SECONDS),
        )
        partner.status = DuelTicket.Status.MATCHED
        partner.duel = duel
        partner.save(update_fields=["status", "duel"])
    if duel.offer_a is not None and duel.offer_a == duel.offer_b:
        _start(duel.pk)
        duel.refresh_from_db()
    return duel


def _best_partner(waiting: list[DuelTicket], stake: int | None) -> DuelTicket | None:
    """قدیمی‌ترین منتظر با همان مقدار؛ وگرنه قدیمی‌ترین منتظری که یکی از دو طرف «فرقی نمی‌کند» گفته."""
    banned = {t.pk for t in waiting if t.user.is_banned}
    exact = [t for t in waiting if t.stake == stake and t.pk not in banned]
    if exact:
        return exact[0]
    flexible = [t for t in waiting if (t.stake is None or stake is None) and t.pk not in banned]
    return flexible[0] if flexible else None


def cancel_search(user: TelegramUser) -> DuelTicket | None:
    ticket = searching_ticket(user.pk)
    if ticket is not None:
        DuelTicket.objects.filter(pk=ticket.pk, status=DuelTicket.Status.SEARCHING).update(
            status=DuelTicket.Status.CANCELLED
        )
    return ticket


def set_ticket_message(ticket_id: int, message_id: int) -> None:
    DuelTicket.objects.filter(pk=ticket_id).update(message_id=message_id)


def set_duel_message(duel_id: int, side: str, message_id: int) -> None:
    Duel.objects.filter(pk=duel_id).update(**{f"message_{side}": message_id})


# ------------------------------------------------------------------ توافق روی سکه
def _locked(duel_id: int, user: TelegramUser) -> tuple[Duel, str]:
    duel = Duel.objects.select_for_update().get(pk=duel_id)
    side = duel.side_of(user.pk)
    if side is None:
        raise DuelError("not_your_duel")
    if duel.status != Duel.Status.NEGOTIATING:
        raise DuelError("duel_closed")
    return duel, side


def offer(user: TelegramUser, duel_id: int, amount: int, now=None) -> Duel:
    """پیشنهاد مقدار سکه. اگر با پیشنهاد حریف برابر شود بازی شروع می‌شود."""
    now = now or timezone.now()
    amount = _check_stake(amount)
    if amount is None:
        raise DuelError("bad_stake")
    if amount and TelegramUser.objects.filter(pk=user.pk).values_list("coins", flat=True).first() < amount:
        raise DuelError("not_enough_coins", balance=user.coins, needed=amount)
    with transaction.atomic():
        duel, side = _locked(duel_id, user)
        if now >= duel.expires_at:
            raise DuelError("duel_closed")
        setattr(duel, f"offer_{side}", amount)
        duel.version += 1
        duel.save(update_fields=[f"offer_{side}", "version"])
        agreed = duel.offer_a is not None and duel.offer_a == duel.offer_b
    if agreed:
        _start(duel.pk)
    duel.refresh_from_db()
    return duel


def accept(user: TelegramUser, duel_id: int, now=None) -> Duel:
    """پیشنهاد حریف را قبول می‌کند (همان مقدار را پیشنهاد می‌دهد)."""
    duel = Duel.objects.get(pk=duel_id)
    side = duel.side_of(user.pk)
    if side is None:
        raise DuelError("not_your_duel")
    theirs = duel.offer_b if side == "a" else duel.offer_a
    if theirs is None:
        raise DuelError("no_offer")
    return offer(user, duel_id, theirs, now)


def cancel(user: TelegramUser, duel_id: int) -> Duel:
    with transaction.atomic():
        duel, side = _locked(duel_id, user)
        duel.status = Duel.Status.CANCELLED
        duel.cancel_reason = f"left_{side}"
        duel.version += 1
        duel.save(update_fields=["status", "cancel_reason", "version"])
    return duel


# ------------------------------------------------------------------ شروع و پایان
def _start(duel_id: int) -> None:
    """مسابقه‌ی دونفره را می‌سازد، ورودی‌ها را کم می‌کند و صفحه‌ی بازی را آماده می‌کند.
    اگر یکی سکه‌ی کافی نداشته باشد هیچ چیزی کم نمی‌شود و دوئل لغو می‌شود."""
    from arcade import board

    duel = Duel.objects.select_related("player_a", "player_b").get(pk=duel_id)
    stake = duel.offer_a or 0
    try:
        with transaction.atomic():
            locked = Duel.objects.select_for_update().get(pk=duel_id)
            if locked.status != Duel.Status.NEGOTIATING:
                return
            match = Match.objects.create(
                group=None,
                creator=duel.player_a,
                game_type=duel.game_type,
                entry_fee=stake,
                prize_split=[100],
                join_deadline=timezone.now() + timedelta(seconds=60),
                min_players=2,
                max_players=2,
                options={"duel": duel.pk},
            )
            for player in (duel.player_a, duel.player_b):
                services.join_match(match.pk, player)
            match = services.start_match(match.pk)
            order = [duel.player_a_id, duel.player_b_id]
            random.Random(match.seed).shuffle(order)
            import time

            board.start(match.pk, board.new_state(duel.game_type, order, time.time(), seed=str(match.seed)))
            locked.status = Duel.Status.PLAYING
            locked.stake = stake
            locked.match = match
            locked.version += 1
            locked.save(update_fields=["status", "stake", "match", "version"])
    except MatchError as exc:
        reason = "coins" if exc.code == "not_enough_coins" else exc.code
        Duel.objects.filter(pk=duel_id, status=Duel.Status.NEGOTIATING).update(
            status=Duel.Status.CANCELLED, cancel_reason=reason[:32], version=duel.version + 1
        )


def finish_if_over(duel_id: int):
    """برای ربات: اگر بازی دوئل تمام شده، جایزه را می‌دهد و نتیجه را برمی‌گرداند (وگرنه ``None``)."""
    from arcade import board

    duel = Duel.objects.select_related("match").get(pk=duel_id)
    if duel.status != Duel.Status.PLAYING or duel.match is None:
        return None
    match = duel.match
    if match.status == MatchStatus.CANCELLED:  # لغو از پنل ادمین (ورودی‌ها آن‌جا برگشته)
        Duel.objects.filter(pk=duel_id).update(status=Duel.Status.CANCELLED, cancel_reason="admin", version=duel.version + 1)
        return None
    state = board.tick(match.pk)
    if state is None or not state["over"]:
        return None
    import time

    now = time.time()
    standings = [Standing(uid, score, now if score > 0 else None) for uid, score in board.standings(state)]
    result = services.finish_match(match.pk, standings)
    Duel.objects.filter(pk=duel_id).update(status=Duel.Status.FINISHED, version=duel.version + 1)
    return result


def expire(now=None) -> list[DuelTicket]:
    """جستجوها و توافق‌های تاریخ‌گذشته را می‌بندد و جستجوهای منقضی‌شده را برای اطلاع‌رسانی برمی‌گرداند.
    دوئل‌های لغوشده نسخه‌شان بالا می‌رود تا ربات پیامشان را به‌روز کند."""
    now = now or timezone.now()
    tickets = list(
        DuelTicket.objects.filter(status=DuelTicket.Status.SEARCHING, expires_at__lte=now).select_related("user")
    )
    DuelTicket.objects.filter(pk__in=[t.pk for t in tickets], status=DuelTicket.Status.SEARCHING).update(
        status=DuelTicket.Status.EXPIRED
    )
    stale = list(Duel.objects.filter(status=Duel.Status.NEGOTIATING, expires_at__lte=now).values_list("pk", "version"))
    for pk, version in stale:
        Duel.objects.filter(pk=pk, status=Duel.Status.NEGOTIATING).update(
            status=Duel.Status.CANCELLED, cancel_reason="timeout", version=version + 1
        )
    return tickets
