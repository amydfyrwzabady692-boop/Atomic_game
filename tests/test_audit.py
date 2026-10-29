"""حسابرسی کامل سکه: هر مسیر پولی (شارژ، فروش، انتقال، ورودی و جایزه‌ی مسابقه، لغو، فروشگاه، دوئل)
بعد از اجرا دقیقاً با ledger جور است و هر دست‌کاری یا تسویه‌ی ناقص پیدا می‌شود."""

from datetime import timedelta

from django.utils import timezone

from games.engine import services as match_services
from games.engine.payout import Standing
from games.models import Match, MatchStatus
from shop.models import ShopItem
from shop.services import ShopError, buy_item
from wallet import services as wallet
from wallet.management.commands.audit_wallets import full_audit
from wallet.models import CoinTransaction, SellRequest, TopUpRequest, TxType


def clean(report):
    return report["wallets"] == [] and report["matches"] == [] and report["requests"] == []


def new_match(group, creator, fee=100):
    return match_services.create_match(
        group, creator, "quick_math", entry_fee=fee, prize_split=[60, 40], join_seconds=60, min_players=2, max_players=4
    )


def test_every_money_path_keeps_the_ledger_exact(group, make_user):
    a, b, c = make_user(1000), make_user(1000), make_user(0)

    # شارژ: یکی تأیید، یکی رد
    ok = wallet.create_topup_request(c, 300, "photo")
    no = wallet.create_topup_request(c, 50, "photo")
    wallet.approve_topup(ok.pk, 1)
    wallet.approve_topup(ok.pk, 2)  # کلیک دوباره‌ی ادمین دیگر بی‌اثر است
    wallet.reject_topup(no.pk, 1)
    # فروش: یکی واریز، یکی رد و برگشت
    paid = wallet.create_sell_request(a, 100, "6037991234567893", "علی")
    back = wallet.create_sell_request(a, 150, "6037991234567893", "علی")
    wallet.mark_sell_paid(paid.pk, 1)
    wallet.reject_sell(back.pk, 1)
    wallet.reject_sell(back.pk, 2)
    # انتقال با کلیک دوباره
    wallet.transfer_coins(a, b, 70, "confirm:1")
    wallet.transfer_coins(a, b, 70, "confirm:1")
    # مسابقه‌ی تمام‌شده، لغوشده و در جریان
    finished = new_match(group, a)
    for user in (a, b, c):
        match_services.join_match(finished.pk, user)
    match_services.start_match(finished.pk)
    match_services.finish_match(finished.pk, [Standing(a.pk, 30, 1.0), Standing(b.pk, 20, 2.0)])
    match_services.finish_match(finished.pk, [Standing(b.pk, 99, 1.0)])  # دوباره اثری ندارد
    cancelled = new_match(group, b)
    match_services.join_match(cancelled.pk, b)
    match_services.join_match(cancelled.pk, c)
    match_services.cancel_match(cancelled.pk, "manual")
    match_services.cancel_match(cancelled.pk, "manual")
    running = new_match(group, c, fee=50)
    match_services.join_match(running.pk, c)
    # فروشگاه: خرید دوباره رد می‌شود و دوبار سکه کم نمی‌شود
    item = ShopItem.objects.create(kind="emoji", name="آزمایشی", value="🧪", price=40)
    buy_item(b, item.pk)
    try:
        buy_item(b, item.pk)
    except ShopError as exc:
        assert exc.code == "already_owned"

    report = full_audit()
    assert clean(report), report
    assert report["users"] == 3 and report["transactions"] == CoinTransaction.objects.count()
    finished.refresh_from_db()
    prizes = CoinTransaction.objects.filter(ref_match=finished, type=TxType.PRIZE)
    assert sum(t.amount for t in prizes) == finished.pot == 300


def test_audit_spots_tampering_and_half_settled_requests(group, make_user):
    a, b = make_user(1000), make_user(1000)
    match = new_match(group, a)
    match_services.join_match(match.pk, a)
    match_services.join_match(match.pk, b)
    match_services.start_match(match.pk)
    match_services.finish_match(match.pk, [Standing(a.pk, 5, 1.0)])
    assert clean(full_audit())

    # جایزه‌ی اضافه برای همان مسابقه (مثلاً باگی که دوبار پرداخت کند)
    wallet.apply_transaction(b, 10, TxType.PRIZE, "bogus-prize", Match.objects.get(pk=match.pk))
    report = full_audit()
    assert report["wallets"] == [] and len(report["matches"]) == 1 and "prizes=210" in report["matches"][0]

    # رسیدی که «تأیید» شده ولی سکه‌اش نرسیده، و فروشی که رد شده ولی برنگشته
    top = wallet.create_topup_request(a, 25, "photo")
    TopUpRequest.objects.filter(pk=top.pk).update(status=TopUpRequest.Status.APPROVED)
    sell = wallet.create_sell_request(b, 100, "6037991234567893", "بهار")
    SellRequest.objects.filter(pk=sell.pk).update(status=SellRequest.Status.REJECTED, reviewed_at=timezone.now())
    problems = full_audit()["requests"]
    assert any(p.startswith(f"topup {top.pk}") for p in problems)
    assert any(p.startswith(f"sell {sell.pk}") for p in problems)

    # لابی باز و مسابقه‌ی لغوشده با حساب درست هیچ خطایی نمی‌دهند
    lobby = new_match(group, a)
    match_services.join_match(lobby.pk, a)
    Match.objects.filter(pk=lobby.pk).update(join_deadline=timezone.now() + timedelta(minutes=5))
    assert not any(f"match {lobby.pk} " in p for p in full_audit()["matches"])
    assert Match.objects.get(pk=lobby.pk).status == MatchStatus.LOBBY
