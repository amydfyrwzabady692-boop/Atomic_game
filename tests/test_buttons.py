"""همه‌ی دکمه‌ها کار می‌کنند: از هر صفحه‌ی شروع (منوی پیوی، کیف پول، فروشگاه، دوئل، منوی ساخت بازی، لابی،
تنظیمات گروه، پنل مدیریت، پیام دعوت) هر دکمه‌ی اینلاین را در همان چت و پیامی که آمده با جدول handlerهای واقعی
ربات (``register_handlers``) فشار می‌دهیم و هر دکمه‌ی تازه را هم دنبال می‌کنیم. هر دکمه‌ای که handler نداشته
باشد، خطا بدهد یا بی‌جواب بماند (چرخک تلگرام نمی‌ایستد) تست را رد می‌کند."""

import itertools
import re
from collections import deque
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from telegram.ext import CallbackQueryHandler

from bot.app import register_handlers
from bot.handlers import admin as admin_handlers
from bot.handlers import arcade, duel, flow, group, group_settings, private, promo, shop
from bot.handlers import wallet as wallet_handlers
from core.models import TelegramUser
from core.redis import reset_clients
from games.models import Match
from membership.models import ForcedChannel, PartnerKey
from wallet.models import TopUpRequest

from .fake_telegram import FakeApplication
from .test_handlers import GROUP_ID, buttons_of, make_update, start_user, tg_user

pytestmark = pytest.mark.django_db(transaction=True)
OWNER = 999
_ids = itertools.count(70_000)


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
    economy_settings(signup_bonus=1000, card_number="6037991234567893", card_holder="مدیر")


@pytest.fixture
def app(settings):
    from bot.runner import MatchManager

    settings.MINIAPP_BASE_URL = "https://arcade.example"
    application = FakeApplication()
    application.bot_data["manager"] = MatchManager(application)
    application.user_data = {}
    return application


class Recorder:
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler, group=0):
        self.handlers.append(handler)

    def add_error_handler(self, callback):
        pass


def callback_handlers() -> list[CallbackQueryHandler]:
    recorder = Recorder()
    register_handlers(recorder)
    return [h for h in recorder.handlers if isinstance(h, CallbackQueryHandler)]


def handler_for(handlers, data: str):
    for handler in handlers:
        pattern = handler.pattern
        if pattern is None:
            return handler
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        if pattern.match(data):
            return handler
    return None


def click_update(app, tg_id, data, chat_id, chat_type, message_id, has_photo=False):
    """کلیک روی دکمه‌ی پیامی مشخص؛ جواب‌ها، ویرایش‌ها و پیام‌های تازه (با شناسه‌شان) جمع می‌شوند."""
    answers, edits, replies = [], [], []

    async def answer(text=None, show_alert=False, **kwargs):
        answers.append((text, show_alert))

    async def edit_message_text(text, **kwargs):
        edits.append({"text": text, **kwargs})
        return True

    async def edit_message_caption(caption=None, **kwargs):
        edits.append({"text": caption, **kwargs})
        return True

    async def edit_message_reply_markup(markup=None, **kwargs):
        edits.append({"text": None, "reply_markup": kwargs.get("reply_markup", markup)})
        return True

    async def reply_text(text, **kwargs):
        new_id = next(_ids)
        replies.append({"text": text, "message_id": new_id, **kwargs})
        return SimpleNamespace(message_id=new_id, chat_id=chat_id)

    async def delete():
        return True

    message = SimpleNamespace(
        message_id=message_id, chat_id=chat_id, reply_text=reply_text, delete=delete,
        photo=[SimpleNamespace(file_id="P")] if has_photo else None, document=None, text="", caption=None,
        forward_origin=None, reply_to_message=None,
    )  # fmt: skip
    query = SimpleNamespace(
        id=f"crawl{next(_ids)}", data=data, message=message, answer=answer, edit_message_text=edit_message_text,
        edit_message_caption=edit_message_caption, edit_message_reply_markup=edit_message_reply_markup,
        from_user=tg_user(tg_id),
    )  # fmt: skip
    update = SimpleNamespace(
        update_id=next(_ids),
        effective_user=tg_user(tg_id),
        effective_chat=SimpleNamespace(id=chat_id, type=chat_type, title="گروه تست"),
        effective_message=message,
        callback_query=query,
        my_chat_member=None,
        chat_member=None,
    )
    update.answers, update.edits, update.replies = answers, edits, replies
    store = app.user_data.setdefault(tg_id, {})
    context = SimpleNamespace(args=[], bot=app.bot, application=app, bot_data=app.bot_data, user_data=store, job_queue=app.job_queue)
    return update, context


# دکمه‌هایی که صفحه را می‌بندند یا چیزی را پاک می‌کنند آخر از همه زده می‌شوند تا مسیرهای عمیق‌تر (مثلاً منوی
# ساخت بازی تا لابی) اول کامل طی شوند
LATE = re.compile(r"(^x:|close|cancel|:del|delok|rotok|nowok|:b$|:back|home|leave|:list|unhook|:off$)")


def missing_families(crawler, prefixes) -> list[str]:
    """خانواده‌های دکمه (پیشوند داده) که هیچ‌کدامشان زده نشد."""
    return [p for p in prefixes if not any(data.startswith(p) for data in crawler.done)]


class Crawler:
    def __init__(self, app, handlers):
        self.app = app
        self.handlers = handlers
        self.queue = deque()
        self.seen = set()
        self.problems: list[str] = []
        self.pressed = 0
        self.done: list[str] = []

    def add(self, markup, tg_id, chat_id, chat_type, message_id, has_photo=False):
        """عمق‌اول: دکمه‌های تازه زودتر از هم‌سطح‌های قبلی زده می‌شوند (به همان ترتیب صفحه)."""
        if markup is None or not hasattr(markup, "inline_keyboard"):
            return
        fresh = []
        for button in buttons_of(markup):
            data = button.callback_data
            if not data:
                assert button.url or button.web_app, f"button without action: {button.text}"
                continue
            key = (tg_id, chat_id, data)
            if key not in self.seen:
                self.seen.add(key)
                item = (tg_id, chat_id, chat_type, message_id, data, has_photo)
                if LATE.search(data):
                    self.queue.append(item)
                else:
                    fresh.append(item)
        self.queue.extendleft(reversed(fresh))

    def add_replies(self, update, tg_id, chat_id, chat_type, default_id):
        for item in update.replies:
            self.add(item.get("reply_markup"), tg_id, chat_id, chat_type, item.get("message_id", default_id))

    async def run(self, limit=900):
        import asyncio

        sent_seen = len(self.app.bot.sent)
        edits_seen = len(self.app.bot.edits)
        while self.queue and self.pressed < limit:
            tg_id, chat_id, chat_type, message_id, data, has_photo = self.queue.popleft()
            handler = handler_for(self.handlers, data)
            if handler is None:
                self.problems.append(f"no handler for {data!r}")
                continue
            update, context = click_update(self.app, tg_id, data, chat_id, chat_type, message_id, has_photo)
            try:
                await handler.callback(update, context)
            except Exception as exc:  # هر خطا یعنی دکمه‌ی خراب
                self.problems.append(f"{data!r} raised {type(exc).__name__}: {exc}")
                continue
            self.pressed += 1
            self.done.append(data)
            if not update.answers:
                self.problems.append(f"{data!r} left the button spinning (no answer)")
            for edit in update.edits:
                self.add(edit.get("reply_markup"), tg_id, chat_id, chat_type, message_id, has_photo)
            self.add_replies(update, tg_id, chat_id, chat_type, message_id)
            for _ in range(3):
                await asyncio.sleep(0)  # ویرایش‌های فوری صف (مثل تبدیل منو به لابی) اجرا شوند
            for sent in self.app.bot.sent[sent_seen:]:
                if sent.get("reply_markup") is not None:
                    kind = chat_type if sent["chat_id"] == chat_id else "private"
                    self.add(sent["reply_markup"], tg_id, sent["chat_id"], kind, sent.get("message_id", 0), bool(sent.get("photo")))
            for edit in self.app.bot.edits[edits_seen:]:
                if edit.get("chat_id") is not None and edit.get("message_id") is not None:
                    kind = chat_type if edit["chat_id"] == chat_id else "private"
                    self.add(edit.get("reply_markup"), tg_id, edit["chat_id"], kind, edit["message_id"])
            sent_seen, edits_seen = len(self.app.bot.sent), len(self.app.bot.edits)
        return self


async def command(app, handler, tg_id, text, chat_id=None, chat_type="private"):
    update, context = make_update(app, tg_id, chat_id=chat_id, chat_type=chat_type, text=text)
    context.user_data = app.user_data.setdefault(tg_id, {})
    context.job_queue = app.job_queue
    for item in update.replies:
        item.setdefault("message_id", None)
    await handler(update, context)
    return update


def seed(crawler, update, tg_id, chat_id, chat_type):
    for item in update.replies:
        crawler.add(item.get("reply_markup"), tg_id, chat_id, chat_type, item.get("message_id") or update.effective_message.message_id + 5000)


async def test_every_user_button_has_a_working_handler(app):
    crawler = Crawler(app, callback_handlers())
    user = 801
    start = await start_user(app, user, name="کاربر")
    seed(crawler, start, user, user, "private")
    for handler, text in [
        (wallet_handlers.wallet_cmd, "/wallet"),
        (shop.shop, "/shop"),
        (duel.duel, "/duel"),
        (arcade.arcade, "/arcade"),
        (private.me, "/me"),
        (private.daily, "/daily"),
        (private.invite, "/invite"),
        (private.help_cmd, "/help"),
        (private.history, "/history"),
        (group.rules, "/rules"),
    ]:
        seed(crawler, await command(app, handler, user, text), user, user, "private")
    await crawler.run()
    assert not crawler.problems, "\n".join(crawler.problems)
    print("\nuser buttons pressed:", crawler.pressed)
    assert not missing_families(crawler, ["pm:", "wal:", "shop:", "du:", "rules:"])


async def test_every_group_button_has_a_working_handler(app):
    crawler = Crawler(app, callback_handlers())
    creator, player = 811, 812
    await start_user(app, creator)
    await start_user(app, player)
    app.bot.admins.add((GROUP_ID, creator))
    menu = await command(app, flow.game, creator, "/game", chat_id=GROUP_ID, chat_type="supergroup")
    seed(crawler, menu, creator, GROUP_ID, "supergroup")
    for handler, text in [(group_settings.settings_cmd, "/settings"), (group.top, "/top"), (group.rules, "/rules")]:
        seed(crawler, await command(app, handler, creator, text, chat_id=GROUP_ID, chat_type="supergroup"), creator, GROUP_ID, "supergroup")
    text, markup = promo.promo_message(0, "test_bot", daily=True)
    crawler.add(markup, player, GROUP_ID, "supergroup", 4242)
    await crawler.run()
    assert not crawler.problems, "\n".join(crawler.problems)
    print("\ngroup buttons pressed:", crawler.pressed)
    # منوی ساخت بازی واقعاً تا لابی رفت و دکمه‌های لابی هم فشار داده شدند
    assert await sync_to_async(Match.objects.exists)()
    assert not missing_families(crawler, ["n:", "j:", "x:", "rl:", "set:", "top:", "promo:"])


async def test_every_admin_panel_button_has_a_working_handler(app):
    crawler = Crawler(app, callback_handlers())
    await start_user(app, OWNER, name="مالک")
    payer = 821
    await start_user(app, payer)
    payer_user = await sync_to_async(TelegramUser.objects.get)(tg_id=payer)
    from wallet import services as wallet

    await sync_to_async(wallet.create_topup_request)(payer_user, 100, "photo-file-id")
    await sync_to_async(wallet.create_sell_request)(payer_user, 150, "6037991234567893", "بهار")
    await sync_to_async(ForcedChannel.objects.create)(chat_id=-100555000, title="کانال", username="ch_test")
    await sync_to_async(PartnerKey.objects.create)(name="ربات دوست", webhook_url="https://partner.example/hook")

    async def fake_deliver(*args, **kwargs):
        return "200"

    from bot import partner_hooks

    partner_hooks_deliver = partner_hooks.deliver
    partner_hooks.deliver = fake_deliver
    try:
        panel = await command(app, admin_handlers.admin_cmd, OWNER, "/admin")
        seed(crawler, panel, OWNER, OWNER, "private")
        await crawler.run()
    finally:
        partner_hooks.deliver = partner_hooks_deliver
    assert not crawler.problems, "\n".join(crawler.problems)
    print("\nadmin buttons pressed:", crawler.pressed)
    families = ["adm:topup:", "adm:top:", "adm:sellreq:", "adm:sell:", "adm:games", "adm:game:", "adm:live:", "adm:settings",
                "adm:daily:", "adm:admins:", "adm:stats:", "adm:audit", "adm:fj:", "adm:api:", "adm:promo:", "adm:post:"]  # fmt: skip
    assert not missing_families(crawler, families), missing_families(crawler, families)
    # رسید شارژ و درخواست فروش واقعاً بررسی شدند (تأیید/رد با همان دکمه‌ها)
    assert await sync_to_async(TopUpRequest.objects.exclude(status=TopUpRequest.Status.PENDING).exists)()


async def test_every_in_game_button_has_a_working_handler(app, settings):
    """بازی‌های دکمه‌دار داخل گروه (بدون مینی‌اپ): همه‌ی دکمه‌های حین بازی، از طرف هر دو بازیکن."""
    from games.catalog import get_info
    from wallet.models import TxType
    from wallet.services import apply_transaction

    settings.MINIAPP_BASE_URL = ""
    manager = app.bot_data["manager"]
    players = [await sync_to_async(TelegramUser.objects.create)(tg_id=830 + i, first_name=f"بازیکن{i}", started_bot=True) for i in range(2)]
    for user in players:
        await sync_to_async(apply_transaction)(user, 5000, TxType.ADMIN_GRANT, f"crawl:{user.pk}")
    from core.models import TelegramGroup

    chat = await sync_to_async(TelegramGroup.objects.create)(chat_id=GROUP_ID, title="گروه تست")
    crawler = Crawler(app, callback_handlers())
    for key in ("quiz", "tictactoe", "connect4", "dice_games", "chess", "poker"):
        sent_before = len(app.bot.sent)
        active = await manager.create_lobby(chat, players[0], get_info(key), fee=10, split=[100], join_seconds=60, options={})
        for user in players:
            await manager.join(active, user)
        await app.job_queue.fire("lobby_close")
        for message in app.bot.sent[sent_before:]:
            for user in players:
                crawler.add(message.get("reply_markup"), user.tg_id, message["chat_id"], "supergroup", message.get("message_id", 0))
        await crawler.run(limit=300)
        await manager.cancel(active, "admin")
    assert not crawler.problems, "\n".join(crawler.problems)
    print("\nin-game buttons pressed:", crawler.pressed)
    assert not missing_families(crawler, ["g:"])


async def test_forced_join_prompt_button_works(app):
    """پیام جوین اجباری: «✅ عضو شدم» قبل و بعد از عضویت."""
    await sync_to_async(ForcedChannel.objects.create)(chat_id=-100600, title="کانال ما", username="our_channel")

    async def left(chat_id, user_id, **kwargs):
        return SimpleNamespace(status="left")

    app.bot.get_chat_member = left
    crawler = Crawler(app, callback_handlers())
    start = await start_user(app, 840)
    seed(crawler, start, 840, 840, "private")
    await crawler.run()
    assert not crawler.problems, "\n".join(crawler.problems)
    assert crawler.done == ["fj:ok"]
