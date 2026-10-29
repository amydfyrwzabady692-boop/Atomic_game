"""پنل مدیریت: نقش‌ها و دسترسی‌ها، کارت کاربر و دادن/کم کردن سکه با تأیید، روشن/خاموش کردن بازی‌ها،
لغو مسابقه‌ی در جریان با برگشت ورودی، تنظیمات اقتصاد و حسابرسی سکه."""

import pytest
from asgiref.sync import sync_to_async

from bot.handlers import admin as admin_handlers
from bot.handlers import common
from core import texts
from core.models import BotAdmin, TelegramGroup, TelegramUser
from games.engine import services as match_services
from games.models import GameSetting, Match, MatchStatus
from wallet.management.commands.audit_wallets import full_audit
from wallet.models import CoinTransaction, EconomySettings, TopUpRequest, TxType

from .fake_telegram import FakeApplication
from .test_handlers import buttons_of, get_user, start_user
from .test_wallet_handlers import ADMIN, give, press, send_private

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _fresh_redis():
    from core.redis import reset_clients

    reset_clients()
    yield
    reset_clients()


@pytest.fixture
def app():
    from bot.runner import MatchManager

    application = FakeApplication()
    application.bot_data["manager"] = MatchManager(application)
    application.user_data = {}
    return application


@pytest.fixture(autouse=True)
def _start_coins(economy_settings):
    economy_settings(signup_bonus=1000)


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    async def always(*args, **kwargs):
        return True

    monkeypatch.setattr("bot.ratelimit.allow", always)


async def panel(app, tg_id, data):
    return await press(app, tg_id, data, handler=admin_handlers.admin_callback)


def shown(update) -> str:
    return "\n".join(e["text"] or "" for e in update.edits) + "\n".join(r["text"] for r in update.replies)


def data_of(update) -> list[str]:
    markup = (update.edits or update.replies)[-1]["reply_markup"]
    return [b.callback_data for b in buttons_of(markup)] if markup else []


async def make_admin(tg_id, perms):
    await sync_to_async(BotAdmin.objects.create)(tg_id=tg_id, permissions=list(perms), name=f"مدیر{tg_id}")
    await common.refresh_admin_ids()


async def test_roles_limit_what_each_admin_sees_and_receives(app):
    await start_user(app, 501, name="مالی")
    await start_user(app, 502, name="پشتیبان")
    await make_admin(501, ["payments", "stats"])
    await make_admin(502, ["support", "users"])
    assert await common.get_all_admin_ids("payments") == [*common._static_admin_ids(), 501]
    assert 502 in await common.get_all_admin_ids("support") and 501 not in await common.get_all_admin_ids("support")

    home = await panel(app, 501, "adm:home")
    buttons = data_of(home)
    assert "adm:topup:list:0" in buttons and "adm:stats:show" in buttons and "adm:audit" in buttons
    assert "adm:usr:find" not in buttons and "adm:admins:list" not in buttons and "adm:settings" not in buttons
    assert "مالی" in shown(home)
    blocked = await panel(app, 501, "adm:admins:list")
    assert blocked.answers[0] == (texts.ADMIN_NO_ACCESS, True)
    assert (await panel(app, 502, "adm:topup:list:0")).answers[0] == (texts.ADMIN_NO_ACCESS, True)
    # کاربر عادی هیچ بخشی را نمی‌بیند
    await start_user(app, 503)
    assert (await panel(app, 503, "adm:home")).answers[0] == (texts.ADMIN_ONLY, True)
    # دستور مدیریتی بدون دسترسی بی‌صدا نادیده گرفته می‌شود
    from .test_handlers import make_update

    update, context = make_update(app, 502, text="/grant 501 10")
    await admin_handlers.grant(update, context)
    assert update.replies == [] and (await get_user(501)).coins == 1000  # هدیه‌ی ثبت‌نام تست‌ها


async def test_owner_adds_edits_and_removes_an_admin_from_the_panel(app):
    await start_user(app, ADMIN, name="مالک")
    await start_user(app, 511, name="نیلوفر")
    await panel(app, ADMIN, "adm:admin:add")
    picked = await send_private(app, ADMIN, "@user511")
    assert "نقش" in picked.replies[0]["text"]
    assert "adm:admin:new:511:finance" in [b.callback_data for b in buttons_of(picked.replies[0]["reply_markup"])]
    done = await panel(app, ADMIN, "adm:admin:new:511:finance")
    assert "مالی" in shown(done)
    row = await sync_to_async(BotAdmin.objects.get)(tg_id=511)
    assert row.permissions == ["payments", "coins", "stats"] and row.name == "نیلوفر" and row.added_by == ADMIN
    assert any("مدیر ربات" in m["text"] for m in app.bot.sent if m["chat_id"] == 511)
    assert await common.has_permission(511, "payments") and not await common.has_permission(511, "users")

    toggled = await panel(app, ADMIN, "adm:admin:perm:511:users")
    assert "✅ " + "👤 کاربران و مسدود کردن" in [b.text for b in buttons_of(toggled.edits[-1]["reply_markup"])]
    assert await common.has_permission(511, "users")
    await panel(app, ADMIN, "adm:admin:preset:511:viewer")
    assert (await sync_to_async(BotAdmin.objects.get)(tg_id=511)).permissions == ["stats"]
    # مدیر غیرمالک با دسترسی «مدیران» هم نمی‌تواند دسترسی «مدیران» بدهد
    await make_admin(512, ["admins"])
    denied = await panel(app, 512, "adm:admin:perm:511:admins")
    assert denied.answers[0] == (texts.ADMIN_ONLY_OWNER, True)

    sure = await panel(app, ADMIN, "adm:admin:del:511")
    assert "adm:admin:delok:511" in data_of(sure)
    await panel(app, ADMIN, "adm:admin:delok:511")
    assert not await sync_to_async(BotAdmin.objects.filter(tg_id=511).exists)()
    assert not await common.is_superadmin(511)
    # مالک را نمی‌شود به‌عنوان مدیر اضافه کرد (همیشه همه‌ی دسترسی‌ها را دارد)
    await panel(app, ADMIN, "adm:admin:add")
    again = await send_private(app, ADMIN, str(ADMIN))
    assert again.replies[0]["text"] == texts.ADMIN_ALREADY_OWNER


async def test_user_card_gives_and_takes_coins_once_with_confirmation(app):
    await start_user(app, ADMIN, name="مالک")
    await start_user(app, 521, name="سارا")
    await panel(app, ADMIN, "adm:usr:find")
    card = await send_private(app, ADMIN, "521")
    assert "سارا" in card.replies[0]["text"] and "۱٬۰۰۰" in card.replies[0]["text"]
    assert "adm:usr:give:521" in [b.callback_data for b in buttons_of(card.replies[0]["reply_markup"])]

    await panel(app, ADMIN, "adm:usr:give:521")
    bad = await send_private(app, ADMIN, "abc")
    assert bad.replies[0]["text"] == texts.ADMIN_BAD_AMOUNT
    confirm = await send_private(app, ADMIN, "250")
    assert "تأیید نهایی" in confirm.replies[0]["text"] and "۱٬۲۵۰" in confirm.replies[0]["text"]
    ok = next(b.callback_data for b in buttons_of(confirm.replies[0]["reply_markup"]) if b.callback_data.startswith("adm:usr:gok:"))
    assert (await get_user(521)).coins == 1000  # هنوز چیزی داده نشده
    await panel(app, ADMIN, ok)
    twice = await panel(app, ADMIN, ok)
    assert twice.answers[0] == (texts.WALLET_EXPIRED, True)
    assert (await get_user(521)).coins == 1250
    assert any("از طرف مدیریت" in m["text"] for m in app.bot.sent if m["chat_id"] == 521)

    await panel(app, ADMIN, "adm:usr:take:521")
    too_much = await send_private(app, ADMIN, "5000")
    assert "کافی نیست" in too_much.replies[0]["text"]
    confirm = await send_private(app, ADMIN, "50")
    ok = next(b.callback_data for b in buttons_of(confirm.replies[0]["reply_markup"]) if b.callback_data.startswith("adm:usr:gok:"))
    await panel(app, ADMIN, ok)
    assert (await get_user(521)).coins == 1200
    grants = await sync_to_async(list)(CoinTransaction.objects.filter(type=TxType.ADMIN_GRANT).values_list("amount", flat=True))
    assert sorted(grants) == [-50, 250]

    banned = await panel(app, ADMIN, "adm:usr:ban:521")
    assert (await get_user(521)).is_banned and "رفع مسدودی" in [b.text for b in buttons_of(banned.edits[-1]["reply_markup"])][2]
    await panel(app, ADMIN, "adm:usr:unban:521")
    assert not (await get_user(521)).is_banned
    no = await panel(app, ADMIN, f"adm:usr:ban:{ADMIN}")
    assert no.answers[0] == (texts.ADMIN_CANT_BAN_ADMIN, True)
    report = await sync_to_async(full_audit)()
    assert report["wallets"] == [] and report["matches"] == [] and report["requests"] == []


async def test_games_toggle_and_cancelling_a_live_match_refunds_everyone(app):
    await start_user(app, ADMIN, name="مالک")
    screen = await panel(app, ADMIN, "adm:games")
    assert "adm:game:t:quick_math" in data_of(screen)
    await panel(app, ADMIN, "adm:game:t:quick_math")
    assert not await sync_to_async(lambda: GameSetting.objects.get(game_key="quick_math").is_enabled)()
    await panel(app, ADMIN, "adm:game:t:quick_math")
    assert await sync_to_async(lambda: GameSetting.objects.get(game_key="quick_math").is_enabled)()

    await start_user(app, 531)
    await start_user(app, 532)

    @sync_to_async
    def lobby():
        group = TelegramGroup.objects.create(chat_id=-100931, title="گروه بازی")
        match = match_services.create_match(
            group, TelegramUser.objects.get(tg_id=531), "quick_math", entry_fee=100, prize_split=[100],
            join_seconds=60, min_players=2, max_players=5,
        )  # fmt: skip
        for tg_id in (531, 532):
            match_services.join_match(match.pk, TelegramUser.objects.get(tg_id=tg_id))
        return match

    match = await lobby()
    assert (await get_user(531)).coins == 900
    listing = await panel(app, ADMIN, "adm:live:list:0")
    assert f"#{match.pk}" in shown(listing) and "گروه بازی" in shown(listing)
    detail = await panel(app, ADMIN, f"adm:live:show:{match.pk}")
    assert f"adm:live:cx:{match.pk}" in data_of(detail)
    sure = await panel(app, ADMIN, f"adm:live:cx:{match.pk}")
    assert f"adm:live:cxok:{match.pk}" in data_of(sure)
    await panel(app, ADMIN, f"adm:live:cxok:{match.pk}")
    assert (await sync_to_async(Match.objects.get)(pk=match.pk)).status == MatchStatus.CANCELLED
    assert (await get_user(531)).coins == (await get_user(532)).coins == 1000
    gone = await panel(app, ADMIN, f"adm:live:cxok:{match.pk}")
    assert gone.answers[0] == (texts.ADMIN_LIVE_GONE, True)


async def test_settings_stats_and_audit_screens(app):
    await start_user(app, ADMIN, name="مالک")
    settings_screen = await panel(app, ADMIN, "adm:settings")
    assert "هدیه‌ی ثبت‌نام" in shown(settings_screen)
    await panel(app, ADMIN, "adm:set:bonus")
    await send_private(app, ADMIN, "25")
    await panel(app, ADMIN, "adm:set:ref")
    wrong = await send_private(app, ADMIN, "30")
    assert wrong.replies[0]["text"] == texts.ADMIN_BAD_NUMBERS
    await send_private(app, ADMIN, "40 5")
    eco = await sync_to_async(EconomySettings.load)()
    assert (eco.signup_bonus, eco.referral_reward, eco.referral_every) == (25, 40, 5)

    stats = await panel(app, ADMIN, "adm:stats:show")
    assert "آمار ربات" in shown(stats) and "شارژ تأییدشده" in shown(stats)
    audit = await panel(app, ADMIN, "adm:audit")
    assert "همه‌چیز دقیق است" in shown(audit)
    # رسیدی که بدون سکه «تأیید» شده در حسابرسی دیده می‌شود
    await sync_to_async(lambda: TopUpRequest.objects.create(
        user=TelegramUser.objects.get(tg_id=ADMIN), coins=5, amount_toman=1, fee_toman=0, total_toman=1, status="APPROVED"
    ))()  # fmt: skip
    audit = await panel(app, ADMIN, "adm:audit")
    assert "مغایرت" in shown(audit)
    await give(ADMIN, 1)  # حساب کاربرها همچنان درست است
