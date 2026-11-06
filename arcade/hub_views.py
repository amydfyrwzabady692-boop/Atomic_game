"""API صفحه‌ی اصلی مینی‌اپ (هاب): پروفایل، رتبه‌بندی، تاریخچه، فروشگاه، جایزه‌ی روزانه، دعوت و حریف تصادفی.

احراز هویت مثل بقیه‌ی مینی‌اپ با ``initData`` امضاشده‌ی تلگرام است. همه‌ی کارها از همان سرویس‌هایی
می‌گذرند که ربات استفاده می‌کند (ledger سکه، فروشگاه، دوئل)، پس منطق دوبار نوشته نشده است.
"""

from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.models import TelegramUser
from core.textutils import fa_date
from games import duels
from games.catalog import get_info
from games.models import Duel, MatchPlayer, MatchStatus
from leaderboard.progress import xp_for_level
from leaderboard.queries import profile_stats, top_players
from membership.web import join_required_response, joined_required
from shop import services as shop
from wallet import economy
from wallet.models import CoinTransaction, TxType

from . import chat
from .views import authenticated, error, rate_limited


def bot_username() -> str:
    """یوزرنیم ربات: از .env، وگرنه همانی که پروسه‌ی ربات موقع بالا آمدن در Redis گذاشته است."""
    if settings.BOT_USERNAME:
        return settings.BOT_USERNAME
    try:
        from core.redis import get_sync_redis

        return get_sync_redis().get("bot:username") or ""
    except Exception:
        return ""


def _ok(**data) -> JsonResponse:
    return JsonResponse({"ok": True, **data})


def _game(key: str) -> dict:
    info = get_info(key)
    data = {"key": key, "title": info.title_fa if info else key, "emoji": info.emoji if info else "🎮"}
    data["kind"] = "arcade" if duels.is_arcade(key) else "board"
    if duels.is_arcade(key):
        # دوئل آرکید: همان بازی با همان شرایط برای هر دو، چند دقیقه و چند تلاش؛ بهترین امتیاز برنده
        from core.texts import fa_num

        # «·» کنار رقم فارسی شبیه «۰» دیده می‌شد؛ «و» خواناست
        data["note"] = f"{fa_num(duels.ARCADE_MINUTES)} دقیقه و {fa_num(duels.ARCADE_ATTEMPTS)} تلاش"
        data["icon"] = key[len("arcade_") :]
    if key == "chess":
        # کنترل زمانی شطرنج حریف تصادفی (مثل ۵+۳)؛ نشانه‌ی چپ‌به‌راست جلوی برعکس شدن «+» را می‌گیرد
        from core.texts import fa_num
        from games.chess import live

        base, increment = live.TIME_CONTROLS[live.DEFAULT_CONTROL]
        data["note"] = f"\u200e{fa_num(base // 60)}+{fa_num(increment)}"
    if key == "poker":
        data["note"] = "میز نقدی"  # سکه به اندازه‌ی ژتون هر نفر، نه برنده‌ی همه
    notes = {"hokm": "۴ نفره؛ یار تصادفی", "hokm3": "۳ نفره", "hokm2": "۳ امتیازی", "chaharbarg": "یک دست", "crash": "۳ دور"}
    if key in notes:
        data["note"] = notes[key]
    if key in duels.TABLE_SIZES:
        data["table"] = duels.TABLE_SIZES[key]
    return data


# ------------------------------------------------------------------ پروفایل و رتبه‌بندی
@csrf_exempt
@require_POST
@rate_limited("hub", 120, 10)
@authenticated
def me(request, user, payload):
    # جوین اجباری: تا عضو کانال‌های ربات نشود صفحه‌ی اصلی فهرست کانال‌ها را نشان می‌دهد («✅ عضو شدم» با fresh)
    blocked = join_required_response(user, fresh=bool(payload.get("fresh")))
    if blocked is not None:
        return blocked
    stats = profile_stats(user)
    config = economy.get_settings()
    # جایزه‌ی دعوت با استارت دوست پرداخت می‌شود؛ پیشرفت هم بر اساس همه‌ی دعوت‌شده‌هاست
    invited = TelegramUser.objects.filter(referred_by=user).count()
    every = max(1, config.referral_every)
    username = bot_username()
    records = []
    for key, score in stats["records"]:
        info = get_info("arcade_" + key)
        records.append({"title": info.title_fa if info else key, "emoji": info.emoji if info else "🕹", "score": score})
    best = get_info(stats["best_game"]) if stats["best_game"] else None
    return _ok(
        name=user.display_name,
        coins=user.coins,
        level=user.level,
        xp=user.xp,
        level_xp=xp_for_level(user.level),
        next_xp=xp_for_level(user.level + 1),
        games=user.games_played,
        wins=user.wins,
        best_game=f"{best.emoji} {best.title_fa}" if best else "",
        badges=stats["badges"],
        decor=stats["decor"],
        records=records,
        daily_enabled=config.daily_enabled,
        invite={
            "link": f"https://t.me/{username}?start=ref_{user.tg_id}" if username else "",
            "count": invited,
            "rewarded": invited,
            "every": every,
            "reward": config.referral_reward,
            "progress": invited % every,
        },
    )


@csrf_exempt
@require_POST
@rate_limited("hub", 120, 10)
@authenticated
def top(request, user, payload):
    period = payload.get("period") if payload.get("period") in ("day", "week", "all") else "week"
    rows = top_players(None, period, limit=20)
    return _ok(
        period=period,
        rows=[
            {
                "rank": r.rank,
                "name": r.user.display_name,
                "coins": r.coins,
                "wins": r.wins,
                "games": r.games,
                "badge": r.badge,
                "title": r.title,
                "me": r.user.pk == user.pk,
            }
            for r in rows
        ],
    )


@csrf_exempt
@require_POST
@rate_limited("hub", 120, 10)
@authenticated
def history(request, user, payload):
    labels = dict(TxType.choices)
    rows = CoinTransaction.objects.filter(user=user).order_by("-id")[:30]
    return _ok(
        rows=[
            {
                "amount": tx.amount,
                "type": labels.get(tx.type, tx.type),
                "at": fa_date(timezone.localtime(tx.created_at)),
            }
            for tx in rows
        ]
    )


@csrf_exempt
@require_POST
@rate_limited("hub_daily", 10, 60)
@authenticated
@joined_required
def daily(request, user, payload):
    result = economy.claim_daily(user)
    user.refresh_from_db()
    if result.disabled:
        return error("daily_disabled", 409)
    left = int((result.next_at - timezone.now()).total_seconds()) if result.next_at else 0
    return _ok(
        claimed=result.claimed, amount=result.amount, streak=result.streak, rescue=result.rescue, coins=user.coins,
        next_in=max(0, left),
    )  # fmt: skip


# ------------------------------------------------------------------ فروشگاه
KIND_TITLES = {"title": "🏷 عنوان‌ها", "emoji": "😎 ایموجی‌ها", "frame": "🖼 قاب‌ها"}


def _coin_shop() -> dict:
    """بسته‌های خرید سکه با همان قیمت و کارمزد منوی شارژ ربات. خرید در پیوی ربات کامل می‌شود
    (/start topup_<تعداد>: شماره کارت، مبلغ، ارسال رسید و تأیید مدیر)، پس منطق پرداخت فقط یک جا است."""
    from wallet import services as wallet_services
    from wallet.models import EconomySettings

    eco = EconomySettings.load()
    packs = []
    for count in wallet_services.TOPUP_PACKAGES:
        quote = wallet_services.topup_quote(count, eco)
        packs.append({"coins": quote.coins, "amount": quote.amount, "fee": quote.fee, "total": quote.total, "start": f"topup_{count}"})
    return {
        "ready": bool(eco.card_number),
        "price": eco.coin_price_toman,
        "fee_percent": eco.topup_fee_percent,
        "packs": packs,
        "sell_price": eco.coin_sell_price_toman,
        "min_sell": max(1, eco.min_sell_coins),
    }


def _shop_data(user) -> dict:
    user.refresh_from_db(fields=["coins"])
    kinds = []
    for kind, title in KIND_TITLES.items():
        items = [
            {
                "id": item.pk,
                "name": item.name,
                "value": item.value,
                "price": item.price,
                "owned": owned is not None,
                "equipped": bool(owned and owned.equipped),
            }
            for item, owned in shop.catalog_for(user, kind)
        ]
        kinds.append({"kind": kind, "title": title, "items": items})
    return {"coins": user.coins, "kinds": kinds, "coin_shop": _coin_shop()}


@csrf_exempt
@require_POST
@rate_limited("hub", 120, 10)
@authenticated
def shop_list(request, user, payload):
    return _ok(**_shop_data(user))


def _item_id(payload) -> int:
    value = payload.get("item_id")
    if isinstance(value, bool) or not isinstance(value, int):
        raise shop.ShopError("not_found")
    return value


@csrf_exempt
@require_POST
@rate_limited("hub_shop", 20, 10)
@authenticated
@joined_required
def shop_buy(request, user, payload):
    try:
        shop.buy_item(user, _item_id(payload))
    except shop.ShopError as exc:
        return error(exc.code, 409)
    return _ok(**_shop_data(user))


@csrf_exempt
@require_POST
@rate_limited("hub_shop", 20, 10)
@authenticated
def shop_equip(request, user, payload):
    try:
        shop.toggle_equipped(user, _item_id(payload))
    except shop.ShopError as exc:
        return error(exc.code, 409)
    return _ok(**_shop_data(user))


# ------------------------------------------------------------------ حریف تصادفی
def _duel_dict(duel: Duel, user) -> dict:
    side = duel.side_of(user.pk)
    them = duel.player_b if side == "a" else duel.player_a
    data = {
        "duel_id": duel.pk,
        "game": _game(duel.game_type),
        "opponent": {"name": them.display_name, "level": them.level},
        "stake": duel.stake,
    }
    if duel.status in (Duel.Status.NEGOTIATING, Duel.Status.PLAYING):
        data["chat"] = chat.recent(chat.duel_room(duel.pk), user.pk)  # گفت‌وگوی دو حریف
    if duel.status == Duel.Status.NEGOTIATING:
        data.update(
            mode="negotiating",
            mine=duel.offer_a if side == "a" else duel.offer_b,
            theirs=duel.offer_b if side == "a" else duel.offer_a,
            seconds_left=max(0, int((duel.expires_at - timezone.now()).total_seconds())),
        )
    elif duel.status == Duel.Status.PLAYING:
        url = ""
        if duel.match and duels.is_arcade(duel.game_type):
            url = reverse("arcade:app") + "?tgWebAppStartParam=" + duel.match.token  # صفحه‌ی همان بازی آرکید
        elif duel.match:
            url = reverse("arcade:board", args=[duel.match.token])
        data.update(mode="playing", url=url)
    elif duel.status == Duel.Status.FINISHED:
        rows = {uid: (prize, rank or 0) for uid, prize, rank in MatchPlayer.objects.filter(match_id=duel.match_id).values_list("user_id", "prize", "rank")}
        mine, theirs = rows.get(user.pk, (0, 0)), rows.get(them.pk, (0, 0))
        outcome = "draw" if mine[1] == theirs[1] else "win" if mine[1] < theirs[1] else "lose"
        data.update(mode="finished", outcome=outcome, prize=mine[0])
    else:
        reason = duel.cancel_reason
        if reason.startswith("left_"):
            reason = "me" if reason == f"left_{side}" else "them"
        data.update(mode="cancelled", reason=reason)
    return data


def _table_dict(match, user) -> dict:
    """میز تصادفی چندنفره (حکم چهارنفره و سه‌نفره) که شروع شده: فقط دکمه‌ی میز؛ گفت‌وگو داخل خود میز است."""
    others = [
        p.user.display_name for p in match.players.select_related("user").order_by("pk") if p.user_id != user.pk
    ]
    return {
        "mode": "playing",
        "table": True,
        "players": len(others) + 1,
        "game": _game(match.game_type),
        "opponent": {"name": "، ".join(others), "level": 0},
        "stake": match.entry_fee,
        "url": reverse("arcade:board", args=[match.token]),
    }


def duel_state_for(user) -> dict:
    active = duels.active_duel(user.pk)
    if active is not None and duels.close_if_expired(active):
        active = duels.active_duel(user.pk)
    if active is not None:
        return _duel_dict(active, user)
    table = duels.table_ticket(user.pk)
    if table is not None and table.match.status == MatchStatus.RUNNING:
        return _table_dict(table.match, user)
    ticket = duels.searching_ticket(user.pk)
    if ticket is not None:
        return {
            "mode": "searching",
            "game": _game(ticket.game_type),
            "stake": ticket.stake,
            "seconds_left": max(0, int((ticket.expires_at - timezone.now()).total_seconds())),
        }
    # نتیجه‌ی آخرین دوئلی که همین تازگی تمام یا لغو شده
    recent = (
        Duel.objects.filter(Q(player_a=user) | Q(player_b=user), created_at__gte=timezone.now() - timedelta(minutes=30))
        .exclude(status__in=[Duel.Status.NEGOTIATING, Duel.Status.PLAYING])
        .select_related("player_a", "player_b", "match")
        .order_by("-pk")
        .first()
    )
    data = {"mode": "idle"}
    if recent is not None:
        data["last"] = _duel_dict(recent, user)
    return data


def _duel_response(user) -> JsonResponse:
    return _ok(
        state=duel_state_for(user),
        games=[_game(g.key) for g in duels.available_games()],
        stakes=list(duels.STAKE_CHOICES),
        max_stake=duels.MAX_STAKE,
        quick=list(chat.QUICK),
        coins=TelegramUser.objects.filter(pk=user.pk).values_list("coins", flat=True).first(),
    )


def _duel_call(user, action):
    try:
        action()
    except duels.DuelError as exc:
        return error(exc.code, 409)
    return _duel_response(user)


def _int_or_none(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise duels.DuelError("bad_stake")
    return value


@csrf_exempt
@require_POST
@rate_limited("duel", 90, 10)
@authenticated
def duel_state(request, user, payload):
    return _duel_response(user)


@csrf_exempt
@require_POST
@rate_limited("duel_act", 20, 10)
@authenticated
@joined_required
def duel_search(request, user, payload):
    return _duel_call(user, lambda: duels.search(user, str(payload.get("game") or ""), _int_or_none(payload.get("stake"))))


@csrf_exempt
@require_POST
@rate_limited("duel_act", 20, 10)
@authenticated
def duel_cancel_search(request, user, payload):
    return _duel_call(user, lambda: duels.cancel_search(user))


def _duel_id(payload) -> int:
    value = payload.get("duel_id")
    if isinstance(value, bool) or not isinstance(value, int):
        raise duels.DuelError("not_your_duel")
    return value


@csrf_exempt
@require_POST
@rate_limited("duel_act", 20, 10)
@authenticated
@joined_required
def duel_offer(request, user, payload):
    return _duel_call(user, lambda: duels.offer(user, _duel_id(payload), _int_or_none(payload.get("amount"))))


@csrf_exempt
@require_POST
@rate_limited("duel_act", 20, 10)
@authenticated
@joined_required
def duel_accept(request, user, payload):
    return _duel_call(user, lambda: duels.accept(user, _duel_id(payload)))


@csrf_exempt
@require_POST
@rate_limited("duel_act", 20, 10)
@authenticated
def duel_cancel(request, user, payload):
    return _duel_call(user, lambda: duels.cancel(user, _duel_id(payload)))


@csrf_exempt
@require_POST
@rate_limited("duel_chat", 30, 10)
@authenticated
def duel_chat(request, user, payload):
    """پیام کوتاه به حریف (موقع توافق روی سکه و حین بازی)."""
    duel = duels.active_duel(user.pk)
    if duel is None or duel.pk != payload.get("duel_id"):
        return error("not_your_duel", 409)
    try:
        chat.post(chat.duel_room(duel.pk), user, payload.get("text"))
    except chat.ChatError as exc:
        return error(exc.code, 409)
    return _duel_response(user)
