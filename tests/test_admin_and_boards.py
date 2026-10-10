"""پنل ادمین، رتبه‌بندی‌ها، قهرمان هفته و فروشگاه."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from games.engine import services
from games.engine.payout import Standing
from games.models import Match, MatchStatus, WordEntry
from leaderboard import queries
from leaderboard.models import WeeklyChampion
from shop import services as shop
from shop.models import ShopItem, UserItem
from shop.services import ShopError
from wallet.management.commands.audit_wallets import find_mismatches
from wallet.models import CoinTransaction, TxType

pytestmark = pytest.mark.django_db
TEHRAN = ZoneInfo("Asia/Tehran")


@pytest.fixture
def staff_client(client):
    get_user_model().objects.create_superuser("admin", "a@example.com", "pass12345")
    client.login(username="admin", password="pass12345")
    return client


def finished_match(group, users, scores, fee=100, split=(60, 30, 10), game="quick_math", finished_at=None):
    match = services.create_match(
        group, users[0], game, entry_fee=fee, prize_split=list(split), join_seconds=60, min_players=2, max_players=10
    )
    for user in users:
        services.join_match(match.pk, user)
    services.start_match(match.pk)
    services.finish_match(match.pk, [Standing(u.pk, s, float(i)) for i, (u, s) in enumerate(zip(users, scores, strict=True))])
    if finished_at is not None:
        Match.objects.filter(pk=match.pk).update(finished_at=finished_at)
    return match


# ====================================================================== پنل ادمین
def test_admin_pages_load(staff_client, group, make_user):
    users = [make_user(1000) for _ in range(2)]
    finished_match(group, users, [5, 1])
    for name in [
        "admin:index",
        "admin_dashboard",
        "admin:core_telegramuser_changelist",
        "admin:core_telegramgroup_changelist",
        "admin:wallet_cointransaction_changelist",
        "admin:games_match_changelist",
        "admin:games_question_changelist",
        "admin:games_wordentry_changelist",
        "admin:games_emojipuzzle_changelist",
        "admin:games_typingsentence_changelist",
        "admin:leaderboard_achievement_changelist",
        "admin:shop_shopitem_changelist",
        "admin:arcade_arcadesession_changelist",
        "admin:arcade_arcaderecord_changelist",
    ]:
        response = staff_client.get(reverse(name))
        assert response.status_code == 200, name
    dashboard = staff_client.get(reverse("admin_dashboard")).content.decode()
    assert "حساب سریع" in dashboard and "کاربران فعال روزانه" in dashboard
    assert staff_client.get(reverse("admin:core_telegramuser_change", args=[users[0].pk])).status_code == 200


def test_dashboard_requires_staff(client):
    assert client.get(reverse("admin_dashboard")).status_code == 302


def test_ledger_is_read_only_in_admin(staff_client, make_user):
    user = make_user(500)
    tx = user.transactions.get()
    assert staff_client.get(reverse("admin:wallet_cointransaction_add")).status_code == 403
    assert staff_client.post(reverse("admin:wallet_cointransaction_delete", args=[tx.pk]), {"post": "yes"}).status_code == 403
    response = staff_client.post(
        reverse("admin:wallet_cointransaction_change", args=[tx.pk]), {"amount": 999999, "balance_after": 999999}
    )
    assert response.status_code == 403
    tx.refresh_from_db()
    assert tx.amount == 500
    # حذف گروهی هم در دسترس نیست
    listing = staff_client.post(
        reverse("admin:wallet_cointransaction_changelist"), {"action": "delete_selected", "_selected_action": [tx.pk]}
    )
    assert CoinTransaction.objects.filter(pk=tx.pk).exists() and listing.status_code in (200, 302, 403)


def test_user_coins_cannot_be_edited_from_admin(staff_client, make_user):
    user = make_user(500)
    staff_client.post(
        reverse("admin:core_telegramuser_change", args=[user.pk]),
        {"username": "x", "first_name": "y", "coins": 999999, "transactions-TOTAL_FORMS": 0, "transactions-INITIAL_FORMS": 0},
    )
    user.refresh_from_db()
    assert user.coins == 500
    assert find_mismatches() == []


def test_admin_cancel_action_refunds_entries(staff_client, group, make_user):
    a, b = make_user(500), make_user(500)
    match = services.create_match(
        group, a, "quick_math", entry_fee=200, prize_split=[100], join_seconds=60, min_players=2, max_players=5
    )
    services.join_match(match.pk, a)
    services.join_match(match.pk, b)
    response = staff_client.post(
        reverse("admin:games_match_changelist"),
        {"action": "cancel_and_refund", "_selected_action": [match.pk]},
        follow=True,
    )
    assert response.status_code == 200
    match.refresh_from_db()
    assert match.status == MatchStatus.CANCELLED and match.cancel_reason == "admin"
    a.refresh_from_db()
    b.refresh_from_db()
    assert (a.coins, b.coins) == (500, 500)
    assert CoinTransaction.objects.filter(type=TxType.REFUND).count() == 2
    # اجرای دوباره روی مسابقه‌ی لغوشده اثری ندارد
    staff_client.post(
        reverse("admin:games_match_changelist"), {"action": "cancel_and_refund", "_selected_action": [match.pk]}
    )
    assert CoinTransaction.objects.filter(type=TxType.REFUND).count() == 2
    assert find_mismatches() == []


def test_admin_csv_import_view(staff_client):
    url = reverse("admin:games_wordentry_import_csv")
    assert staff_client.get(url).status_code == 200
    upload = SimpleUploadedFile("words.csv", "word,category\nکهکشان,space\nسیاره,space\n".encode(), "text/csv")
    response = staff_client.post(url, {"file": upload}, follow=True)
    assert response.status_code == 200
    assert WordEntry.objects.filter(category="space").count() == 2
    bad = SimpleUploadedFile("bad.csv", b"nothing\nhere\n", "text/csv")
    response = staff_client.post(url, {"file": bad})
    assert "ستون‌های لازم" in response.content.decode()


# ====================================================================== رتبه‌بندی
def at(day, hour=12):
    return datetime(2026, 3, day, hour, tzinfo=TEHRAN)


def test_week_starts_on_saturday_in_tehran():
    # ۲۰۲۶/۰۳/۱۴ شنبه است
    assert queries.week_start(at(14, 0)).date().isoformat() == "2026-03-14"
    assert queries.week_start(at(18)).date().isoformat() == "2026-03-14"
    assert queries.week_start(at(13, 23)).date().isoformat() == "2026-03-07"
    assert queries.day_start(at(18, 15)).hour == 0


def test_top_players_by_coins_then_wins_and_scopes(group, make_user):
    from core.models import TelegramGroup

    other_group = TelegramGroup.objects.create(chat_id=-100321, title="دیگر")
    a, b, c = make_user(5000), make_user(5000), make_user(5000)
    finished_match(group, [a, b, c], [9, 5, 1])  # a: 180, b: 90, c: 30
    finished_match(group, [a, b], [1, 9], split=(100,))  # b: 200
    finished_match(other_group, [c, a], [9, 1], split=(100,))  # c: 200 در گروه دیگر

    in_group = queries.top_players(group.pk)
    assert [(r.user.pk, r.coins, r.wins) for r in in_group] == [(b.pk, 290, 1), (a.pk, 180, 1), (c.pk, 30, 0)]
    everywhere = queries.top_players(None)
    assert [(r.user.pk, r.coins) for r in everywhere] == [(b.pk, 290), (c.pk, 230), (a.pk, 180)]
    assert [r.rank for r in everywhere] == [1, 2, 3]


def test_top_players_period_filters(group, make_user):
    a, b = make_user(5000), make_user(5000)
    now = at(18)
    finished_match(group, [a, b], [9, 1], split=(100,), finished_at=at(18, 9))  # امروز
    finished_match(group, [a, b], [1, 9], split=(100,), finished_at=at(15))  # همین هفته
    finished_match(group, [a, b], [1, 9], split=(100,), finished_at=at(3))  # قدیمی

    def coins(period):
        since, until = queries.period_range(period, now)
        return {r.user.pk: r.coins for r in queries.top_players(group.pk, since=since, until=until)}

    assert coins("day") == {a.pk: 200, b.pk: 0}
    assert coins("week") == {a.pk: 200, b.pk: 200}
    assert coins("all") == {a.pk: 200, b.pk: 400}


def test_weekly_champion_announced_once(group, make_user):
    a, b = make_user(5000), make_user(5000)
    finished_match(group, [a, b], [9, 1], split=(100,), finished_at=at(10))  # هفته‌ی ۷ تا ۱۴ مارس
    finished_match(group, [a, b], [1, 9], split=(100,), finished_at=at(15))  # هفته‌ی بعد
    now = at(14, 1)  # شنبه
    first = queries.announce_weekly_champions(now)
    assert [(g.pk, row.user.pk, row.coins) for g, row in first] == [(group.pk, a.pk, 200)]
    assert queries.announce_weekly_champions(now) == []
    champion = WeeklyChampion.objects.get()
    assert champion.user_id == a.pk and champion.week_start.isoformat() == "2026-03-07"


def test_weekly_champion_skips_groups_without_games(group):
    assert queries.announce_weekly_champions(at(14, 1)) == []
    assert WeeklyChampion.objects.get().user is None


def test_profile_stats(group, make_user):
    a, b = make_user(5000), make_user(5000)
    finished_match(group, [a, b], [9, 1])
    finished_match(group, [a, b], [9, 1], game="anagram")
    finished_match(group, [a, b], [9, 1], game="anagram")
    stats = queries.profile_stats(a)
    assert stats["best_game"] == "anagram"
    assert "🥇" in stats["badges"]
    a.refresh_from_db()
    assert a.wins == 3 and a.games_played == 3


# ====================================================================== فروشگاه
def test_shop_purchase_is_cosmetic_irreversible_and_ledgered(make_user):
    shop.seed_default_items()
    user = make_user(1000)
    item = ShopItem.objects.filter(kind="emoji").order_by("price").first()
    owned = shop.buy_item(user, item.pk)
    user.refresh_from_db()
    assert owned.equipped and user.coins == 1000 - item.price
    tx = CoinTransaction.objects.get(type=TxType.SHOP)
    assert tx.amount == -item.price
    with pytest.raises(ShopError) as err:
        shop.buy_item(user, item.pk)
    assert err.value.code == "already_owned"
    assert shop.decorations([user.pk]) == {user.pk: {"emoji": item.value}}
    assert find_mismatches() == []


def test_shop_cannot_buy_without_coins(make_user):
    shop.seed_default_items()
    user = make_user(10)
    item = ShopItem.objects.order_by("-price").first()
    with pytest.raises(ShopError) as err:
        shop.buy_item(user, item.pk)
    assert err.value.code == "no_coins"
    assert not UserItem.objects.exists()
    user.refresh_from_db()
    assert user.coins == 10


def test_only_one_item_per_kind_is_equipped(make_user):
    shop.seed_default_items()
    user = make_user(50_000)
    first, second = ShopItem.objects.filter(kind="title").order_by("price")[:2]
    shop.buy_item(user, first.pk)
    shop.buy_item(user, second.pk)
    assert list(UserItem.objects.filter(equipped=True).values_list("item_id", flat=True)) == [second.pk]
    shop.toggle_equipped(user, first.pk)
    assert list(UserItem.objects.filter(equipped=True).values_list("item_id", flat=True)) == [first.pk]
    shop.toggle_equipped(user, first.pk)
    assert not UserItem.objects.filter(equipped=True).exists()


def test_leaderboard_shows_equipped_decorations(group, make_user):
    shop.seed_default_items()
    a, b = make_user(50_000), make_user(50_000)
    shop.buy_item(a, ShopItem.objects.filter(kind="title").first().pk)
    shop.buy_item(a, ShopItem.objects.filter(kind="emoji").first().pk)
    finished_match(group, [a, b], [9, 1])
    top = queries.top_players(group.pk)[0]
    assert top.user.pk == a.pk and top.badge and top.title


def test_no_real_money_or_transfer_paths_exist():
    """قانون غیرقابل‌تغییر: هیچ نوع تراکنشی برای خرید با پول، برداشت یا انتقال بین کاربران وجود ندارد."""
    names = {choice.lower() for choice in TxType.values}
    for forbidden in ("transfer", "withdraw", "deposit", "purchase", "payment", "cashout"):
        assert not any(forbidden in name for name in names)
    assert set(TxType.values) == {
        "DAILY", "REFERRAL", "ENTRY_FEE", "PRIZE", "REFUND", "ADMIN_GRANT", "SHOP", "ACHIEVEMENT", "SIGNUP_BONUS", "RESCUE",
    }
