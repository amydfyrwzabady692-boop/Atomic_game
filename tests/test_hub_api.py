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
    assert data["daily_enabled"] is False
    status, data = post(client, "hub/top", user, period="all")
    assert status == 200 and data["rows"] == []
    status, data = post(client, "hub/history", user)
    assert data["rows"][0]["amount"] == 250
    # بدون initData معتبر چیزی برنمی‌گردد
    assert client.post("/arcade/api/hub/me", data="{}", content_type="application/json").status_code == 401


def test_daily_from_the_hub_follows_admin_settings(client, make_user, economy_settings):
    user = make_user()
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


def test_duel_through_the_mini_app(client, make_user):
    a, b = make_user(1000), make_user(1000)
    status, data = post(client, "duel/state", a)
    assert data["state"]["mode"] == "idle" and {g["key"] for g in data["games"]} == {"chess", "tictactoe", "connect4", "poker"}
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
