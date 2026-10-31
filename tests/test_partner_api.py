"""API ربات‌های دیگر (استارت ربات و عضویت کانال)، جوین اجباری مینی‌اپ و ارسال امضاشده‌ی وب‌هوک‌ها."""

import hashlib
import hmac
import json

import httpx
import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone

from bot import partner_hooks
from core.models import BotAdmin
from core.redis import reset_clients
from membership import api, checks
from membership.models import ForcedChannel, PartnerKey

CHANNEL = -1001234


@pytest.fixture(autouse=True)
def _fresh_redis():
    reset_clients()
    yield
    reset_clients()


class FakeTelegram:
    """جواب getChatMember از سرویس وب: ``joined`` اعضا و ``broken`` کانال‌هایی که ربات ادمینشان نیست."""

    def __init__(self, monkeypatch):
        self.joined: set[tuple[str, int]] = set()
        self.broken: set[str] = set()
        self.calls = 0
        monkeypatch.setattr(checks, "telegram", self.call)

    def call(self, method, **params):
        assert method == "getChatMember"
        self.calls += 1
        chat = str(params["chat_id"]).lower()
        if chat in self.broken:
            return {"ok": False, "description": "Bad Request: member list is inaccessible"}
        status = "member" if (chat, params["user_id"]) in self.joined else "left"
        return {"ok": True, "result": {"status": status}}


@pytest.fixture
def telegram(monkeypatch):
    return FakeTelegram(monkeypatch)


@pytest.fixture
def key(db):
    return PartnerKey.objects.create(name="ربات دوست")


def call(client, path, key_text=None, how="query", method="get", **params):
    url = f"/api/v1/{path}"
    headers = {}
    if key_text and how == "bearer":
        headers["HTTP_AUTHORIZATION"] = f"Bearer {key_text}"
    elif key_text and how == "header":
        headers["HTTP_X_API_KEY"] = key_text
    elif key_text:
        params["key"] = key_text
    if method == "post":
        response = client.post(url, data=json.dumps(params), content_type="application/json", **headers)
    else:
        response = client.get(url, params, **headers)
    return response.status_code, response.json()


def test_keys_are_required_and_started_status_is_reported(client, key, make_user):
    assert call(client, "user", user_id=5) == (401, {"ok": False, "error": "bad_key"})
    assert call(client, "user", "wz_wrong", user_id=5)[0] == 401
    assert call(client, "user", key.key, user_id="abc") == (400, {"ok": False, "error": "bad_user_id"})

    status, data = call(client, "user", key.key, user_id=777)
    assert status == 200 and data == {"ok": True, "user_id": 777, "started": False, "blocked": False, "started_at": None}

    fan = make_user(started_at=timezone.now())
    for how in ("query", "bearer", "header"):
        status, data = call(client, "started", key.key, how=how, user_id=fan.tg_id)
        assert status == 200 and data["started"] is True and data["started_at"]
    # POST با JSON هم، و / آخر آدرس هم مهم نیست
    status, data = call(client, "user/", key.key, method="post", user_id=fan.tg_id)
    assert data["started"] is True

    fan.blocked_bot = True
    fan.save(update_fields=["blocked_bot"])
    assert call(client, "user", key.key, user_id=fan.tg_id)[1] | {"started_at": None} == {
        "ok": True, "user_id": fan.tg_id, "started": False, "blocked": True, "started_at": None,
    }  # fmt: skip

    key.is_active = False
    key.save(update_fields=["is_active"])
    assert call(client, "user", key.key, user_id=fan.tg_id)[0] == 401


def test_check_reports_each_channel_and_caches_telegram_answers(client, key, make_user, telegram):
    fan = make_user(started_bot=True)
    telegram.joined.add(("@winzon_ch", fan.tg_id))
    telegram.broken.add("@notadmin")
    status, data = call(client, "check", key.key, user_id=fan.tg_id, channels="@winzon_ch,https://t.me/other_ch,@notadmin")
    assert status == 200 and data["started"] is True
    assert data["channels"] == [
        {"chat": "@winzon_ch", "joined": True},
        {"chat": "@other_ch", "joined": False},
        {"chat": "@notadmin", "joined": False, "error": "bot_not_admin"},
    ]
    assert data["all_joined"] is False and data["passed"] is False
    calls = telegram.calls
    call(client, "check", key.key, user_id=fan.tg_id, channels="@winzon_ch")
    assert telegram.calls == calls  # جواب «عضو است» کش شده

    # بدون channels: کانال‌های جوین اجباری همین ربات
    ForcedChannel.objects.create(chat_id=CHANNEL, title="کانال ما", username="")
    checks.forget_channels()
    telegram.joined.add((str(CHANNEL), fan.tg_id))
    status, data = call(client, "check", key.key, user_id=fan.tg_id)
    assert data["channels"] == [{"chat": str(CHANNEL), "joined": True}] and data["passed"] is True
    assert call(client, "check", key.key, user_id=fan.tg_id, channels="not a channel!")[1]["error"] == "bad_channels"

    status, data = call(client, "me", key.key)
    assert data["ok"] and data["name"] == "ربات دوست" and data["channels"] == [str(CHANNEL)]
    assert PartnerKey.objects.get(pk=key.pk).last_used_at is not None


def test_partner_api_rate_limit(client, key, monkeypatch):
    monkeypatch.setattr(api, "RATE_LIMIT", 2)
    assert call(client, "user", key.key, user_id=1)[0] == 200
    assert call(client, "user", key.key, user_id=1)[0] == 200
    assert call(client, "user", key.key, user_id=1) == (429, {"ok": False, "error": "rate_limited"})


# ====================================================================== مینی‌اپ
def hub(client, path, user, **body):
    from .test_live_chess import post

    return post(client, path, user, **body)


def test_mini_app_asks_for_the_channels_first(client, make_user, telegram):
    user = make_user(started_bot=True)
    assert hub(client, "hub/me", user)[0] == 200  # بدون کانال جوین اجباری خاموش است
    ForcedChannel.objects.create(chat_id=CHANNEL, title="کانال ما", username="winzon_ch")
    checks.forget_channels()
    status, data = hub(client, "hub/me", user)
    assert status == 403 and data == {
        "ok": False, "error": "join_required", "channels": [{"title": "کانال ما", "link": "https://t.me/winzon_ch"}],
    }  # fmt: skip
    assert hub(client, "hub/daily", user)[1]["error"] == "join_required"
    assert hub(client, "duel/search", user, game="chess", stake=0)[1]["error"] == "join_required"
    # عضو شد: «✅ عضو شدم» بدون کش دوباره می‌پرسد
    telegram.joined.add((str(CHANNEL), user.tg_id))
    assert hub(client, "hub/me", user)[0] == 403  # جواب قبلی «عضو نیست» هنوز در کش است
    status, data = hub(client, "hub/me", user, fresh=True)
    assert status == 200 and data["ok"]
    # مدیر ربات بدون عضویت هم وارد می‌شود
    admin = make_user()
    BotAdmin.objects.create(tg_id=admin.tg_id, permissions=["stats"])
    assert hub(client, "hub/me", admin)[0] == 200


# ====================================================================== وب‌هوک
@pytest.mark.django_db(transaction=True)
async def test_webhooks_are_signed_retried_and_recorded(monkeypatch):
    received = []
    replies = iter([500, 200, 404])

    def handler(request):
        received.append(request)
        return httpx.Response(next(replies))

    monkeypatch.setattr(partner_hooks, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(partner_hooks, "RETRY_DELAYS", (0, 0))
    key = await sync_to_async(PartnerKey.objects.create)(name="دوست", webhook_url="https://partner.example/hook")
    await sync_to_async(PartnerKey.objects.create)(name="بی‌وب‌هوک")
    await partner_hooks._emit("start", "test_bot", {"user_id": 42, "first": True})

    assert len(received) == 2  # ۵۰۰ یک بار دوباره امتحان شد؛ کلید بی‌وب‌هوک چیزی نگرفت
    request = received[-1]
    body = request.content
    assert request.headers["X-Event"] == "start"
    assert request.headers["X-Signature"] == hmac.new(key.key.encode(), body, hashlib.sha256).hexdigest()
    data = json.loads(body)
    assert data["event"] == "start" and data["bot"] == "test_bot" and data["user_id"] == 42 and data["first"] is True
    assert (await partner_hooks.last_result(key.pk))["status"] == "200"

    # ۴xx یعنی گیرنده نمی‌خواهد: تکرار نمی‌شود
    await partner_hooks._emit("block", "test_bot", {"user_id": 42})
    assert len(received) == 3 and (await partner_hooks.last_result(key.pk))["status"] == "404"


def test_unreachable_telegram_is_remembered_and_slow_checks_stop_asking(db, monkeypatch, settings):
    settings.BOT_TOKEN = "123:abc"
    attempts = []

    class Broken:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json):
            attempts.append(url)
            raise httpx.ConnectError("no route to api.telegram.org")

    monkeypatch.setattr(httpx, "Client", Broken)
    assert checks.is_member("@winzon_ch", 5) == (None, "network")
    assert checks.is_member("@winzon_ch", 6) == (None, "network")
    assert len(attempts) == 1  # یک دقیقه دوباره امتحان نمی‌شود؛ کاربرها هم گیر نمی‌افتند
    ForcedChannel.objects.create(chat_id=CHANNEL, title="کانال ما", username="winzon_ch")
    checks.forget_channels()
    assert checks.missing_channels(5) == [] and len(attempts) == 1

    # وقت پرسیدن تمام شده: فقط کش خوانده می‌شود
    monkeypatch.setattr(checks, "ASK_BUDGET", 0)
    checks.remember("@a", 7, True)
    assert checks.members(["@a", "@b"], 7) == [(True, ""), (None, "timeout")]
