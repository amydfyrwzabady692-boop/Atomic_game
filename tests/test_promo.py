"""پیام دعوت به بازی در گروه‌ها (هر ۲ ساعت، با دکمه)، دکمه‌های آن، خاموش کردنش در گروه، لینک‌های ?start=…
و پست‌های آماده‌ی کانال در پنل مدیریت."""

import time
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from telegram.error import Forbidden

from bot.handlers import group_settings, promo
from core import texts
from core.models import TelegramGroup
from core.redis import get_redis, reset_clients
from games.models import Match
from membership.models import ForcedChannel
from wallet.models import EconomySettings

from .fake_telegram import FakeApplication
from .test_handlers import GROUP_ID, buttons_of, click, make_callback, make_update, open_game_menu, start_user
from .test_wallet_handlers import press, send_private

pytestmark = pytest.mark.django_db(transaction=True)
OWNER = 999


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
    monkeypatch.setattr(promo, "SEND_GAP", 0)


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


@sync_to_async
def make_groups(*specs):
    for chat_id, promo_on in specs:
        TelegramGroup.objects.create(chat_id=chat_id, title=f"گروه {chat_id}", promo_enabled=promo_on)


def sent_to(app, chat_id):
    return [m for m in app.bot.sent if m["chat_id"] == chat_id]


def test_invite_texts_and_buttons(settings):
    settings.MINIAPP_BASE_URL = "https://arcade.example"
    text, markup = promo.promo_message(0, "winzon_bot", daily=True)
    data = {b.text: (b.callback_data or b.url) for b in buttons_of(markup)}
    assert text.split("\n")[0] == texts.PROMO_VARIANTS[0][0].split("\n")[0]
    assert "روی هم ۱۸ بازی گروهی" in text and "{" not in text  # تعداد واقعی بازی‌ها (با حکم، حکم سه‌نفره و چهاربرگ)
    assert data[texts.PROMO_GAME_BTN] == "promo:game" and data[texts.PROMO_HELP_BTN] == "promo:help"
    assert data[texts.PROMO_DUEL_BTN] == "https://t.me/winzon_bot?start=duel"
    assert data[texts.PROMO_DAILY_BTN] == "https://t.me/winzon_bot?start=daily"
    assert data[texts.PROMO_MINIAPP_BTN].startswith("https://t.me/winzon_bot")
    # بدون مینی‌اپ و جایزه‌ی روزانه: متن‌ها و دکمه‌های مربوط نمی‌آیند
    settings.MINIAPP_BASE_URL = ""
    shown = {promo.promo_message(i, "winzon_bot", daily=False)[0] for i in range(30)}
    always = [text for text, need in texts.PROMO_VARIANTS if need == ""]
    assert len(shown) == len(always) >= 5 and not any("مینی‌اپ" in t and "🕹" in t.split("\n")[0] for t in shown)
    every_variant = {promo.promo_message(i, "winzon_bot", daily=True)[0] for i in range(60)}
    assert len(every_variant) == len(texts.PROMO_VARIANTS) or not promo.render.arcade_ready()
    labels = [b.text for b in buttons_of(promo.promo_message(1, "winzon_bot", daily=False)[1])]
    assert texts.PROMO_DUEL_BTN not in labels and texts.PROMO_DAILY_BTN not in labels
    assert len(texts.PROMO_HELP_ALERT) <= 200


async def test_invites_go_out_on_schedule_replace_the_last_one_and_skip_busy_groups(app):
    await make_groups((-1001, True), (-1002, True), (-1003, False))

    async def blocked(chat_id, text, **kwargs):
        if chat_id == -1002:
            raise Forbidden("bot was kicked from the supergroup chat")
        return await original(chat_id, text, **kwargs)

    original = app.bot.send_message
    app.bot.send_message = blocked
    context = SimpleNamespace(application=app, bot=app.bot)
    await promo.promo_job(context)
    first = sent_to(app, -1001)
    assert len(first) == 1 and first[0]["disable_notification"] is True and first[0]["reply_markup"]
    assert not sent_to(app, -1003)  # ادمین این گروه خاموشش کرده
    assert not (await sync_to_async(TelegramGroup.objects.get)(chat_id=-1002)).is_active  # ربات بیرون شده بود

    await promo.promo_job(context)
    assert len(sent_to(app, -1001)) == 1  # هنوز ۲ ساعت نگذشته
    await get_redis().set("promo:last_run", int(time.time()) - 100 * 60)
    await promo.promo_job(context)
    assert len(sent_to(app, -1001)) == 1  # ۱۰۰ دقیقه هم کافی نیست

    await get_redis().set("promo:last_run", int(time.time()) - 121 * 60)
    await promo.promo_job(context)
    second = sent_to(app, -1001)
    assert len(second) == 2 and second[1]["text"] != second[0]["text"]  # متن بعدی
    assert (-1001, first[0]["message_id"]) in app.bot.deleted  # پیام قبلی پاک شد

    # گروهی که همین حالا مسابقه دارد رد می‌شود
    await start_user(app, 401)
    _, menu_id = await open_game_menu(app, 401)
    for step in ("n:g:quick_math", "n:f:100", "n:s:60-30-10", "n:t:30"):
        await click(app, 401, step, menu_id)
    assert await sync_to_async(Match.objects.count)() == 1
    sent, skipped = await promo.run_promo(app)
    assert not sent_to(app, GROUP_ID) and len(sent_to(app, -1001)) == 3 and skipped == 1

    # خاموش از پنل: هیچ پیامی نمی‌رود
    await sync_to_async(EconomySettings.objects.update)(promo_enabled=False)
    await get_redis().set("promo:last_run", 0)
    count = len(app.bot.sent)
    await promo.promo_job(context)
    assert len(app.bot.sent) == count


async def test_invite_buttons_open_the_game_menu_and_explain_how_to_play(app):
    await start_user(app, 410)
    update, context = make_callback(app, 410, "promo:help", 777, chat_id=GROUP_ID)
    await promo.promo_callback(update, context)
    assert update.answers[-1] == (texts.PROMO_HELP_ALERT, True)

    update, context = make_callback(app, 410, "promo:game", 777, chat_id=GROUP_ID)
    await promo.promo_callback(update, context)
    menu = update.replies[-1]
    labels = [b.text for b in buttons_of(menu["reply_markup"])]
    assert any("حساب سریع" in label for label in labels)
    # منو مال کسی است که دکمه را زد: می‌تواند ادامه بدهد
    step = await click(app, 410, "n:g:quick_math", 777 + 9000)
    assert "ورودی" in step.edits[-1]["text"]

    update, context = make_callback(app, 410, "promo:game", 778, chat_id=410, chat_type="private")
    await promo.promo_callback(update, context)
    assert update.answers[-1] == (texts.PROMO_ONLY_GROUP, True)


async def test_group_admin_can_turn_invites_off(app):
    await start_user(app, 420)
    app.bot.admins.add((GROUP_ID, 420))
    await get_redis().set(f"promo:msg:{GROUP_ID}", 4321)  # آخرین پیام دعوت در همین گروه
    update, context = make_update(app, 420, chat_id=GROUP_ID, chat_type="supergroup", text="/settings")
    await group_settings.settings_cmd(update, context)
    assert "پیام دعوت" in update.replies[-1]["text"]
    assert "set:promo" in [b.callback_data for b in buttons_of(update.replies[-1]["reply_markup"])]
    click_update, click_context = make_callback(app, 420, "set:promo", 900)
    await group_settings.settings_callback(click_update, click_context)
    group = await sync_to_async(TelegramGroup.objects.get)(chat_id=GROUP_ID)
    assert not group.promo_enabled
    assert (GROUP_ID, 4321) in app.bot.deleted and await get_redis().get(f"promo:msg:{GROUP_ID}") is None


async def test_start_links_open_the_right_section(app):
    update = await start_user(app, 430, payload="help")
    assert any("راهنما" in r["text"] or "/game" in r["text"] for r in update.replies)
    update = await start_user(app, 431, payload="duel")
    assert any("حریف" in r["text"] for r in update.replies)
    update = await start_user(app, 432, payload="channel")
    assert len(update.replies) == 1  # همان خوش‌آمد معمولی


# ====================================================================== پنل: تبلیغ و پست‌های کانال
async def panel(app, tg_id, data):
    return await press(app, tg_id, data, handler=promo.panel_callback)


def shown(update) -> str:
    return "\n".join([e["text"] or "" for e in update.edits] + [r["text"] for r in update.replies])


async def test_admin_controls_invites_and_publishes_channel_posts(app, settings):
    settings.MINIAPP_BASE_URL = "https://arcade.example"
    await start_user(app, OWNER, name="مالک")
    await make_groups((-2001, True))
    home = await panel(app, OWNER, "adm:promo:home")
    assert "هر <b>۲ ساعت</b>" in shown(home) and "گروه‌های فعال: ۱" in shown(home)
    every = await panel(app, OWNER, "adm:promo:every")
    assert (await sync_to_async(EconomySettings.load)()).promo_minutes == 180 and "۳ ساعت" in every.answers[-1][0]
    assert promo.next_every(360) == 5 and promo.fa_every(90) == "۹۰ دقیقه" and promo.fa_every(240) == "۴ ساعت"
    await panel(app, OWNER, "adm:promo:toggle")
    assert not (await sync_to_async(EconomySettings.load)()).promo_enabled
    preview = await panel(app, OWNER, "adm:promo:preview")
    assert preview.answers and sent_to(app, OWNER)[-1]["reply_markup"]
    await panel(app, OWNER, "adm:promo:nowok")
    assert len(sent_to(app, -2001)) == 1  # «ارسال همین حالا» حتی وقتی خاموش است
    # وقتی یک دور (زمان‌بندی‌شده یا در پروسه‌ی دیگر) در جریان است، ارسال دستی دور دوم نمی‌سازد
    await get_redis().set("promo:running", "1", ex=60)
    busy = await panel(app, OWNER, "adm:promo:nowok")
    assert busy.answers[-1] == (texts.ADMIN_PROMO_BUSY, True) and len(sent_to(app, -2001)) == 1
    await sync_to_async(EconomySettings.objects.update)(promo_enabled=True)
    await get_redis().set("promo:last_run", 0)
    await promo.promo_job(SimpleNamespace(application=app, bot=app.bot))
    assert len(sent_to(app, -2001)) == 1  # زمان‌بندی هم صبر می‌کند
    await get_redis().delete("promo:running")
    await sync_to_async(EconomySettings.objects.update)(promo_enabled=False)

    posts = await panel(app, OWNER, "adm:post:list")
    keys = [b.callback_data for b in buttons_of(posts.edits[-1]["reply_markup"])]
    assert "adm:post:show:intro" in keys and "adm:post:show:wallet" in keys
    wallet = await panel(app, OWNER, "adm:post:show:wallet")
    text = shown(wallet)
    assert "۱٬۰۰۰ تومان" in text and "۱۰٪" in text and "حداقل ۱۰۰ سکه" in text
    intro = await panel(app, OWNER, "adm:post:show:intro")
    assert "@test_bot" in shown(intro) and "۱۸ بازی گروهی" in shown(intro) and "۵ بازی آرکید" in shown(intro)

    channel = await sync_to_async(ForcedChannel.objects.create)(chat_id=-1007, title="کانال ما", username="winzon_ch")
    picked = await panel(app, OWNER, "adm:post:pick:intro")
    assert f"adm:post:to:intro:{channel.pk}" in [b.callback_data for b in buttons_of(picked.edits[-1]["reply_markup"])]
    published = await panel(app, OWNER, f"adm:post:to:intro:{channel.pk}")
    post = sent_to(app, -1007)[-1]
    assert "بازی گروهی با جایزه" in post["text"] and all(b.url for b in buttons_of(post["reply_markup"]))
    assert "منتشر شد" in published.answers[-1][0]

    await panel(app, OWNER, "adm:post:other:faq")
    done = await send_private(app, OWNER, "@another_channel")
    assert sent_to(app, "@another_channel") and "منتشر شد" in done.replies[-1]["text"]


def test_every_channel_post_renders_with_link_buttons(db, settings):
    settings.MINIAPP_BASE_URL = "https://arcade.example"
    eco = EconomySettings.load()
    for key, _title, _body in texts.CHANNEL_POSTS:
        text, markup = promo.channel_post(key, "winzon_bot", eco)
        assert "{" not in text and len(text) < 4096
        assert all(button.url and button.url.startswith("https://t.me/winzon_bot") for button in buttons_of(markup))
