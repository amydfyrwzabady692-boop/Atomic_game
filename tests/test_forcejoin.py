"""جوین اجباری در ربات: /start و کارهای پیوی تا عضویت در کانال‌ها منتظر می‌مانند (دعوت و شرکت در مسابقه بعد از
تأیید ادامه پیدا می‌کند)، مدیران مستثنا هستند، ورود/خروج کانال و بلاک ربات ثبت و به ربات‌های دیگر اعلام می‌شود،
و پنل مدیریت کانال‌ها و کلیدهای API را مدیریت می‌کند."""

from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async

from bot.handlers import admin as admin_handlers
from bot.handlers import common, forcejoin, group, membership_admin, private
from core import texts
from core.models import BotAdmin, TelegramUser
from core.redis import get_redis, reset_clients
from games.models import Match
from membership import checks
from membership.models import ForcedChannel, PartnerKey

from .fake_telegram import FakeApplication
from .test_handlers import GROUP_ID, buttons_of, click, get_user, make_callback, make_update, open_game_menu, start_user
from .test_wallet_handlers import press, send_private

pytestmark = pytest.mark.django_db(transaction=True)

CHANNEL = -1001234
BOT_ID = 1  # FakeBot.get_me


@pytest.fixture(autouse=True)
def _fresh_redis():
    reset_clients()
    yield
    reset_clients()


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    async def always(*args, **kwargs):
        return True

    monkeypatch.setattr("bot.ratelimit.allow", always)


@pytest.fixture(autouse=True)
def _start_coins(economy_settings):
    economy_settings(signup_bonus=1000)


@pytest.fixture
def app():
    from bot.runner import MatchManager

    application = FakeApplication()
    application.bot_data["manager"] = MatchManager(application)
    application.user_data = {}
    return application


class Members:
    """عضویت ساختگی کانال‌ها برای getChatMember ربات."""

    def __init__(self, app, bot_admin_in=(CHANNEL,)):
        self.joined: set[tuple[int, int]] = set()
        self.bot_admin_in = set(bot_admin_in)
        self.calls = 0
        app.bot.get_chat_member = self.get_chat_member

    async def get_chat_member(self, chat_id, user_id, **kwargs):
        self.calls += 1
        if user_id == BOT_ID:
            return SimpleNamespace(status="administrator" if chat_id in self.bot_admin_in else "left")
        return SimpleNamespace(status="member" if (chat_id, user_id) in self.joined else "left")


@sync_to_async
def add_channel(chat_id=CHANNEL, title="کانال وینزون", username="winzon_ch", **fields):
    row = ForcedChannel.objects.create(chat_id=chat_id, title=title, username=username, **fields)
    checks.forget_channels()
    return row


async def check_press(app, tg_id):
    update, context = make_callback(app, tg_id, "fj:ok", 7000, chat_id=tg_id, chat_type="private")
    await forcejoin.check_callback(update, context)
    return update


def texts_of(update) -> str:
    return "\n".join([r["text"] for r in update.replies] + [e["text"] or "" for e in update.edits])


# ====================================================================== /start و کارهای پیوی
async def test_start_waits_for_the_channel_then_finishes_signup_and_referral(app, hook_events):
    members = Members(app)
    await start_user(app, 300, name="دعوت‌کننده")  # قبل از جوین اجباری استارت کرده
    await add_channel()

    update = await start_user(app, 301, payload="ref_300", name="تازه")
    reply = update.replies[-1]
    assert "کانال وینزون" in reply["text"] and "عضو شدم" in reply["text"]
    buttons = buttons_of(reply["reply_markup"])
    assert buttons[0].url == "https://t.me/winzon_ch" and buttons[-1].callback_data == "fj:ok"
    newcomer = await get_user(301)
    # استارت همان لحظه ثبت و اعلام شد، ولی هدیه و دعوت هنوز نه
    assert newcomer.started_at is not None and not newcomer.started_bot and newcomer.coins == 0
    assert ("start", {"user_id": 301, "first": True}) in hook_events

    still = await check_press(app, 301)
    assert still.answers[-1][1] is True and "کانال وینزون" in still.answers[-1][0]
    assert not (await get_user(301)).started_bot

    members.joined.add((CHANNEL, 301))
    done = await check_press(app, 301)
    assert texts.FJ_VERIFIED in texts_of(done)
    newcomer = await get_user(301)
    assert newcomer.started_bot and newcomer.coins == 1000 and newcomer.referred_by_id == (await get_user(300)).pk
    assert any("دعوت" in r["text"] for r in done.replies)  # «با دعوت … وارد شدی»


async def test_private_commands_and_buttons_need_the_channel_but_admins_do_not(app):
    members = Members(app)
    await start_user(app, 310)
    await add_channel()

    update, context = make_update(app, 310, text="/me")
    await private.me(update, context)
    assert "کانال وینزون" in update.replies[-1]["text"]  # به‌جای پروفایل پیام عضویت

    clicked = await press(app, 310, "pm:me", handler=private.menu_callback)
    assert clicked.answers[0][0] == texts.FJ_ALERT
    assert "کانال وینزون" in app.bot.sent[-1]["text"]

    members.joined.add((CHANNEL, 310))
    redis = get_redis()
    await redis.delete(checks.member_key(CHANNEL, 310))  # کش «عضو نیست» چند ثانیه می‌ماند
    update, context = make_update(app, 310, text="/me")
    await private.me(update, context)
    assert "کانال وینزون" not in update.replies[-1]["text"]

    # مدیر ربات بدون عضویت هم کار می‌کند
    await start_user(app, 311)
    await sync_to_async(BotAdmin.objects.create)(tg_id=311, permissions=["stats"])
    await common.refresh_admin_ids()
    update, context = make_update(app, 311, text="/me")
    await private.me(update, context)
    assert "کانال وینزون" not in update.replies[-1]["text"]


async def test_no_channels_means_no_gate_and_unreachable_channels_never_lock_users_out(app):
    members = Members(app)
    update = await start_user(app, 320)
    assert "🔒" not in update.replies[-1]["text"] and members.calls == 0  # بدون کانال اصلاً پرسیده نمی‌شود
    await add_channel()

    async def broken(chat_id, user_id, **kwargs):
        from telegram.error import BadRequest

        raise BadRequest("Bad Request: member list is inaccessible")

    app.bot.get_chat_member = broken  # ربات ادمین کانال نیست
    update, context = make_update(app, 320, text="/me")
    await private.me(update, context)
    assert "🔒" not in update.replies[-1]["text"]


async def test_joining_a_match_in_a_group_sends_non_members_through_the_bot(app):
    members = Members(app)
    await start_user(app, 330)
    await start_user(app, 331)
    _, menu_id = await open_game_menu(app, 330)
    for step in ("n:g:quick_math", "n:f:100", "n:s:60-30-10", "n:t:30"):
        await click(app, 330, step, menu_id)
    match = await sync_to_async(Match.objects.get)()
    await add_channel()

    blocked = await click(app, 331, f"j:{match.pk}", menu_id, group.join_callback)
    assert blocked.urls == [f"https://t.me/test_bot?start=join_{match.pk}"]
    # پیوی: /start join_… پیام عضویت می‌دهد و بعد از «✅ عضو شدم» خودکار عضو همان مسابقه می‌شود
    update = await start_user(app, 331, payload=f"join_{match.pk}")
    assert "کانال وینزون" in update.replies[-1]["text"]
    members.joined.add((CHANNEL, 331))
    done = await check_press(app, 331)
    assert any("عضو مسابقه شدی" in r["text"] for r in done.replies)
    players = await sync_to_async(lambda: sorted(match.players.values_list("user__tg_id", flat=True)))()
    assert players == [330, 331]

    # ساخت مسابقه در گروه هم عضویت می‌خواهد
    update, context = make_update(app, 332, chat_id=GROUP_ID, chat_type="supergroup", text="/game")
    from bot.handlers import flow

    await flow.game(update, context)
    assert "🔒" in update.replies[-1]["text"]
    assert buttons_of(update.replies[-1]["reply_markup"])[0].url == "https://t.me/test_bot?start=fj"


# ====================================================================== رویدادهای کانال و بلاک
def member_update(chat_type, old, new, user_id=340, chat_id=CHANNEL, username="winzon_ch"):
    user = SimpleNamespace(id=user_id, is_bot=False, first_name="عضو", username="u")
    change = SimpleNamespace(
        old_chat_member=SimpleNamespace(status=old, user=user),
        new_chat_member=SimpleNamespace(status=new, user=user),
        from_user=user,
    )
    chat = SimpleNamespace(id=chat_id, type=chat_type, username=username, title="کانال وینزون")
    return SimpleNamespace(chat_member=change, my_chat_member=change, effective_chat=chat, effective_user=user)


async def test_channel_joins_and_leaves_update_the_cache_and_reach_partner_bots(app, hook_events):
    context = SimpleNamespace(bot=app.bot, application=app, bot_data=app.bot_data)
    await forcejoin.chat_member(member_update("channel", "left", "member"), context)
    redis = get_redis()
    assert await redis.get(checks.member_key(CHANNEL, 340)) == "1"
    assert await redis.get(checks.member_key("@winzon_ch", 340)) == "1"
    assert hook_events[-1] == (
        "join",
        {"user_id": 340, "chat_id": CHANNEL, "chat_username": "winzon_ch", "chat_title": "کانال وینزون"},
    )
    await forcejoin.chat_member(member_update("channel", "member", "left"), context)
    assert await redis.get(checks.member_key(CHANNEL, 340)) == "0" and hook_events[-1][0] == "leave"
    # گروه‌ها فقط کش را درست می‌کنند (بدون وب‌هوک)
    await forcejoin.chat_member(member_update("supergroup", "left", "member", chat_id=-100999, username=None), context)
    assert await redis.get(checks.member_key(-100999, 340)) == "1" and len(hook_events) == 2


async def test_blocking_and_unblocking_the_bot_is_tracked(app, hook_events):
    await start_user(app, 350)
    context = SimpleNamespace(bot=app.bot, application=app, bot_data=app.bot_data)
    await group.my_chat_member(member_update("private", "member", "kicked", user_id=350, chat_id=350), context)
    assert (await get_user(350)).blocked_bot and hook_events[-1] == ("block", {"user_id": 350})
    await group.my_chat_member(member_update("private", "kicked", "member", user_id=350, chat_id=350), context)
    assert not (await get_user(350)).blocked_bot and hook_events[-1] == ("unblock", {"user_id": 350})
    # /start هم بلاک را پاک می‌کند
    await sync_to_async(TelegramUser.objects.filter(tg_id=350).update)(blocked_bot=True)
    await start_user(app, 350)
    assert not (await get_user(350)).blocked_bot


# ====================================================================== پنل مدیریت
OWNER = 999  # settings_test.SUPERADMIN_IDS


async def fj(app, tg_id, data):
    return await press(app, tg_id, data, handler=membership_admin.panel_callback)


def panel_text(update) -> str:
    return "\n".join([e["text"] or "" for e in update.edits] + [r["text"] for r in update.replies])


async def test_admin_adds_checks_pauses_and_removes_forced_channels(app):
    members = Members(app, bot_admin_in=(CHANNEL, -100777))
    await start_user(app, OWNER, name="مالک")
    home = await press(app, OWNER, "adm:home", handler=admin_handlers.admin_callback)
    assert "adm:fj:list" in [b.callback_data for b in buttons_of(home.edits[-1]["reply_markup"])]

    screen = await fj(app, OWNER, "adm:fj:list")
    assert texts.ADMIN_FJ_EMPTY in panel_text(screen)
    await fj(app, OWNER, "adm:fj:add")

    async def get_chat(ref, **kwargs):
        chats = {
            "@winzon_ch": SimpleNamespace(id=CHANNEL, type="channel", title="کانال وینزون", username="winzon_ch", invite_link=None),
            -100777: SimpleNamespace(id=-100777, type="channel", title="کانال خصوصی", username=None, invite_link=None),
            "@nobotadmin": SimpleNamespace(id=-100888, type="channel", title="بدون ادمین", username="nobotadmin", invite_link=None),
        }
        if ref not in chats:
            from telegram.error import BadRequest

            raise BadRequest("Chat not found")
        return chats[ref]

    async def export_chat_invite_link(chat_id, **kwargs):
        return "https://t.me/+secretLink"

    async def get_chat_member_count(chat_id, **kwargs):
        return 1234

    app.bot.get_chat, app.bot.export_chat_invite_link = get_chat, export_chat_invite_link
    app.bot.get_chat_member_count = get_chat_member_count

    bad = await send_private(app, OWNER, "سلام دنیا")
    assert texts.ADMIN_FJ_BAD_REF in bad.replies[-1]["text"]
    missing = await send_private(app, OWNER, "@nothere")
    assert texts.ADMIN_FJ_NOT_FOUND in missing.replies[-1]["text"]
    not_admin = await send_private(app, OWNER, "https://t.me/nobotadmin")
    assert "ادمین نیست" in not_admin.replies[-1]["text"]
    added = await send_private(app, OWNER, "@winzon_ch")
    assert "اضافه شد" in added.replies[-1]["text"]
    await fj(app, OWNER, "adm:fj:add")
    private_added = await send_private(app, OWNER, "-100777")
    assert "اضافه شد" in private_added.replies[-1]["text"]

    rows = await sync_to_async(lambda: list(ForcedChannel.objects.order_by("position")))()
    assert [(r.chat_id, r.link) for r in rows] == [(CHANNEL, "https://t.me/winzon_ch"), (-100777, "https://t.me/+secretLink")]
    assert [row["chat_id"] for row in await forcejoin.active_channels()] == [CHANNEL, -100777]

    detail = await fj(app, OWNER, f"adm:fj:show:{rows[0].pk}")
    assert "۱٬۲۳۴" in panel_text(detail) and texts.ADMIN_FJ_BOT_ADMIN in panel_text(detail)
    await fj(app, OWNER, f"adm:fj:toggle:{rows[0].pk}")
    assert [row["chat_id"] for row in await forcejoin.active_channels()] == [-100777]
    await fj(app, OWNER, f"adm:fj:delok:{rows[1].pk}")
    assert await forcejoin.active_channels() == []
    assert members.calls >= 3

    # بدون دسترسی «تنظیمات» بخش جوین اجباری بسته است
    await start_user(app, 361)
    await sync_to_async(BotAdmin.objects.create)(tg_id=361, permissions=["stats"])
    await common.refresh_admin_ids()
    denied = await fj(app, 361, "adm:fj:list")
    assert denied.answers[-1] == (texts.ADMIN_NO_ACCESS, True)


async def test_admin_manages_partner_api_keys(app):
    await start_user(app, OWNER, name="مالک")
    screen = await fj(app, OWNER, "adm:api:list")
    assert texts.ADMIN_API_EMPTY in panel_text(screen)
    await fj(app, OWNER, "adm:api:new")
    created = await send_private(app, OWNER, "ربات دوستم")
    key = await sync_to_async(PartnerKey.objects.get)()
    assert key.name == "ربات دوستم" and key.key.startswith("wz_") and key.key in created.replies[-1]["text"]

    await fj(app, OWNER, f"adm:api:hook:{key.pk}")
    wrong = await send_private(app, OWNER, "http://insecure.example/hook")
    assert texts.ADMIN_API_BAD_HOOK in wrong.replies[-1]["text"]
    await send_private(app, OWNER, "https://partner.example/hook")
    await sync_to_async(key.refresh_from_db)()
    assert key.webhook_url == "https://partner.example/hook"

    old = key.key
    await fj(app, OWNER, f"adm:api:rotok:{key.pk}")
    await fj(app, OWNER, f"adm:api:toggle:{key.pk}")
    await sync_to_async(key.refresh_from_db)()
    assert key.key != old and not key.is_active
    await fj(app, OWNER, f"adm:api:delok:{key.pk}")
    assert not await sync_to_async(PartnerKey.objects.exists)()

    # کلیدها رمزند: فقط با دسترسی «مدیران»
    await start_user(app, 371)
    await sync_to_async(BotAdmin.objects.create)(tg_id=371, permissions=["settings", "stats"])
    await common.refresh_admin_ids()
    denied = await fj(app, 371, "adm:api:list")
    assert denied.answers[-1] == (texts.ADMIN_NO_ACCESS, True)
