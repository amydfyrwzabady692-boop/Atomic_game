import pytest

from games.models import Duel, MatchStatus
from shop.models import ShopItem, UserItem

from .test_live_chess import post

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh_redis():
    from core.redis import reset_clients

    reset_clients()
    yield
    reset_clients()


def test_hub_page_is_the_mini_app_home(client):
    page = client.get("/arcade/")
    html = page.content.decode()
    assert page.status_code == 200 and "hub.js" in html and 'data-tab="duel"' in html
    assert len(page.context["games"]) == 14
    # صفحه‌ی بازی‌ها و لینک مسابقه همان صفحه‌ی بازی قبلی‌اند
    assert "shell.js" in client.get("/arcade/play/pins/").content.decode()


def test_me_top_and_history(client, make_user, economy_settings, settings):
    settings.BOT_USERNAME = "test_bot"
    economy_settings(referral_every=10, referral_reward=3)
    user = make_user(250, first_name="رضا")
    status, data = post(client, "hub/me", user)
    assert status == 200 and data["name"] == "رضا" and data["coins"] == 250 and data["level"] == 1
    assert data["invite"]["link"] == f"https://t.me/test_bot?start=ref_{user.tg_id}"
    assert (data["invite"]["every"], data["invite"]["reward"]) == (10, 3)
    assert data["daily_enabled"] is True  # گردونه‌ی روزانه پیش‌فرض روشن است
    status, data = post(client, "hub/top", user, period="all")
    assert status == 200 and data["rows"] == []
    status, data = post(client, "hub/history", user)
    assert data["rows"][0]["amount"] == 250
    # بدون initData معتبر چیزی برنمی‌گردد
    assert client.post("/arcade/api/hub/me", data="{}", content_type="application/json").status_code == 401


def test_daily_from_the_hub_follows_admin_settings(client, make_user, economy_settings):
    user = make_user()
    economy_settings(daily_enabled=False)
    assert post(client, "hub/daily", user)[1]["error"] == "daily_disabled"
    economy_settings(daily_enabled=True)
    status, data = post(client, "hub/daily", user)
    assert data["claimed"] and data["coins"] == data["amount"]
    again = post(client, "hub/daily", user)[1]
    assert again["claimed"] is False and again["next_in"] > 0


def test_shop_buy_and_equip(client, make_user):
    item = ShopItem.objects.create(kind="emoji", name="آتش", value="🔥", price=100)
    poor, rich = make_user(10), make_user(500)
    assert post(client, "hub/shop/buy", poor, item_id=item.pk)[1]["error"] == "no_coins"
    status, data = post(client, "hub/shop/buy", rich, item_id=item.pk)
    assert status == 200 and data["coins"] == 400
    emoji = next(k for k in data["kinds"] if k["kind"] == "emoji")["items"][0]
    assert emoji["owned"] and emoji["equipped"]
    assert post(client, "hub/shop/buy", rich, item_id=item.pk)[1]["error"] == "already_owned"
    status, data = post(client, "hub/shop/equip", rich, item_id=item.pk)
    assert not UserItem.objects.get(user=rich, item=item).equipped


def test_shop_sells_coin_packs_with_the_bot_top_up_prices(client, make_user, economy_settings):
    """بخش «خرید سکه»ی فروشگاه همان بسته‌ها، قیمت و کارمزد منوی شارژ ربات را دارد و هر بسته پیوی ربات را با
    /start topup_<تعداد> باز می‌کند؛ بدون شماره کارت، خرید غیرفعال است."""
    from wallet.services import TOPUP_PACKAGES, topup_quote

    eco = economy_settings(card_number="6037991234567893", coin_price_toman=1000, topup_fee_percent=10, min_sell_coins=100)
    status, data = post(client, "hub/shop", make_user(30))
    shop = data["coin_shop"]
    assert status == 200 and shop["ready"] and shop["fee_percent"] == 10 and shop["min_sell"] == 100
    assert [p["coins"] for p in shop["packs"]] == list(TOPUP_PACKAGES)
    hundred = next(p for p in shop["packs"] if p["coins"] == 100)
    assert (hundred["amount"], hundred["fee"], hundred["total"], hundred["start"]) == (100_000, 10_000, 110_000, "topup_100")
    assert all(p["total"] == topup_quote(p["coins"], eco).total for p in shop["packs"])
    assert "6037991234567893" not in str(data)  # شماره کارت فقط در پیوی ربات نشان داده می‌شود
    economy_settings(card_number="")
    assert post(client, "hub/shop", make_user())[1]["coin_shop"]["ready"] is False


def test_duel_through_the_mini_app(client, make_user):
    a, b = make_user(1000), make_user(1000)
    status, data = post(client, "duel/state", a)
    keys = [g["key"] for g in data["games"]]
    assert data["state"]["mode"] == "idle" and keys[:4] == ["chess", "poker", "tictactoe", "connect4"] and len(keys) == 18
    kinds = {g["key"]: g["kind"] for g in data["games"]}
    assert kinds["chess"] == "board" and kinds["arcade_snake"] == "arcade" and data["quick"] and data["max_stake"] > 0
    # شطرنج حریف تصادفی کنترل زمانی ۵+۳ دارد و برچسبش در متن راست‌به‌چپ برعکس نمی‌شود
    assert {g["key"]: g.get("note") for g in data["games"]}["chess"] == "\u200e۵+۳"
    status, data = post(client, "duel/search", a, game="poker", stake=None)
    assert data["state"]["mode"] == "searching" and data["state"]["stake"] is None
    status, data = post(client, "duel/search", b, game="poker", stake=250)
    state = data["state"]
    assert state["mode"] == "negotiating" and (state["mine"], state["theirs"]) == (250, None)
    status, data = post(client, "duel/state", a)
    assert data["state"]["theirs"] == 250 and data["state"]["opponent"]["name"] == b.display_name
    status, data = post(client, "duel/accept", a, duel_id=state["duel_id"])
    assert data["state"]["mode"] == "playing" and data["state"]["url"].startswith("/arcade/board/")
    duel = Duel.objects.get()
    assert duel.match.status == MatchStatus.RUNNING and duel.match.pot == 500
    # صفحه‌ی بازی همان میز پوکر است
    assert "poker.js" in client.get(data["state"]["url"]).content.decode()
    # دیگران نمی‌توانند در دوئل دخالت کنند
    c = make_user()
    assert post(client, "duel/cancel", c, duel_id=duel.pk)[1]["error"] == "not_your_duel"
    assert post(client, "duel/offer", a, duel_id=duel.pk, amount="x")[1]["error"] == "bad_stake"


def test_arcade_duel_and_chat_between_the_two_players(client, make_user):
    a, b, outsider = make_user(500), make_user(500), make_user(500)
    post(client, "duel/search", a, game="arcade_snake", stake=None)
    status, data = post(client, "duel/search", b, game="arcade_snake", stake=None)
    duel_id = data["state"]["duel_id"]
    assert data["state"]["mode"] == "negotiating" and data["state"]["chat"] == []
    # گفت‌وگو برای توافق روی مبلغ
    status, data = post(client, "duel/chat", b, duel_id=duel_id, text="  سلام، ۷۵ سکه؟  ")
    assert status == 200 and data["state"]["chat"][-1]["text"] == "سلام، ۷۵ سکه؟" and data["state"]["chat"][-1]["mine"]
    seen = post(client, "duel/state", a)[1]["state"]["chat"]
    assert seen[-1]["text"] == "سلام، ۷۵ سکه؟" and not seen[-1]["mine"] and seen[-1]["name"] == b.display_name
    assert post(client, "duel/chat", a, duel_id=duel_id, text="بیا t.me/scam")[1]["error"] == "chat_no_links"
    assert post(client, "duel/chat", a, duel_id=duel_id, text="   ")[1]["error"] == "chat_empty"
    assert post(client, "duel/chat", outsider, duel_id=duel_id, text="سلام")[1]["error"] == "not_your_duel"
    assert post(client, "duel/chat", b, duel_id=duel_id, text="دوباره")[1]["error"] == "chat_too_fast"
    # مبلغ دلخواه (نه فقط دکمه‌های آماده) و شروع با توافق
    post(client, "duel/offer", b, duel_id=duel_id, amount=75)
    status, data = post(client, "duel/accept", a, duel_id=duel_id)
    state = data["state"]
    assert state["mode"] == "playing" and state["url"].startswith("/arcade/?tgWebAppStartParam=") and state["chat"]
    assert state["game"]["kind"] == "arcade" and "تلاش" in state["game"]["note"]
    duel = Duel.objects.get()
    assert duel.stake == 75 and duel.match.pot == 150 and duel.match.token in state["url"]
    # همان لینک صفحه‌ی بازی آرکید را با توکن مسابقه باز می‌کند
    page = client.get(state["url"]).content.decode()
    assert "shell.js" in page and duel.match.token in page
