"""کیف پول در لایه‌ی ربات: انتقال با تأیید، فروش با تأیید کارت، شارژ با رسید و رسیدگی ادمین‌ها."""

import itertools
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async

from bot.handlers import admin as admin_handlers
from bot.handlers import private
from bot.handlers import wallet as wallet_handlers
from bot.runner import MatchManager
from core import texts
from core.models import TelegramUser
from core.redis import reset_clients
from wallet.management.commands.audit_wallets import find_mismatches
from wallet.models import CoinTransaction, SellRequest, TopUpRequest, TxType
from wallet.services import apply_transaction

from .fake_telegram import FakeApplication
from .test_handlers import buttons_of, get_user, make_update, start_user, tg_user

pytestmark = pytest.mark.django_db(transaction=True)
GROUP_ID = -100777
ADMIN = 999  # سوپرادمین تست (settings_test)
_ids = itertools.count(1)


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


@pytest.fixture
def app():
    application = FakeApplication()
    application.bot_data["manager"] = MatchManager(application)
    application.user_data = {}
    return application


def user_data(app, tg_id) -> dict:
    return app.user_data.setdefault(tg_id, {})


@sync_to_async
def give(tg_id, coins):
    apply_transaction(TelegramUser.objects.get(tg_id=tg_id), coins, TxType.ADMIN_GRANT, f"give:{tg_id}:{coins}")


@sync_to_async
def audit():
    return find_mismatches()


def callback_update(app, tg_id, data, chat_id=None, chat_type="private", photo=False):
    """یک کلیک دکمه‌ی اینلاین با پیام کامل (متن یا عکس‌دار)."""
    chat_id = tg_id if chat_id is None else chat_id
    answers, edits, replies = [], [], []
    message_id = 5000 + next(_ids)

    async def answer(text=None, show_alert=False, **kwargs):
        answers.append((text, show_alert))

    async def edit_message_text(text, **kwargs):
        edits.append({"text": text, **kwargs})
        return True

    async def edit_message_caption(caption=None, **kwargs):
        edits.append({"text": caption, "caption": True, **kwargs})
        return True

    async def edit_message_reply_markup(markup=None, **kwargs):
        edits.append({"text": None, "reply_markup": kwargs.get("reply_markup", markup)})
        return True

    async def reply_text(text, **kwargs):
        replies.append({"text": text, **kwargs})
        return SimpleNamespace(message_id=message_id + 1)

    async def delete():
        return True

    message = SimpleNamespace(
        message_id=message_id, chat_id=chat_id, reply_text=reply_text, delete=delete,
        photo=[SimpleNamespace(file_id="P")] if photo else None, document=None,
    )  # fmt: skip
    query = SimpleNamespace(
        id=f"cq{next(_ids)}", data=data, message=message, answer=answer, edit_message_text=edit_message_text,
        edit_message_caption=edit_message_caption, edit_message_reply_markup=edit_message_reply_markup,
    )  # fmt: skip
    update = SimpleNamespace(
        update_id=next(_ids),
        effective_user=tg_user(tg_id),
        effective_chat=SimpleNamespace(id=chat_id, type=chat_type, title="گروه"),
        effective_message=message,
        callback_query=query,
    )
    update.answers, update.edits, update.replies = answers, edits, replies
    context = SimpleNamespace(
        args=[], bot=app.bot, application=app, bot_data=app.bot_data, user_data=user_data(app, tg_id)
    )
    return update, context


async def press(app, tg_id, data, handler=wallet_handlers.wallet_callback, **kwargs):
    update, context = callback_update(app, tg_id, data, **kwargs)
    await handler(update, context)
    return update


async def send_private(app, tg_id, text="", photo=None):
    """پیام پیوی کاربر در وسط یک مرحله‌ی کیف پول (عدد، کارت، آیدی یا عکس رسید)."""
    update, context = make_update(app, tg_id, text=text)
    update.effective_message.photo = [SimpleNamespace(file_id=photo)] if photo else []
    update.effective_message.document = None
    update.effective_message.caption = None
    context.user_data = user_data(app, tg_id)
    await wallet_handlers.private_message(update, context)
    return update


def token_of(markup) -> str:
    return next(b.callback_data for b in buttons_of(markup) if b.callback_data.startswith("wal:tc:")).split(":")[2]


# ====================================================================== انتقال سکه
async def test_private_transfer_needs_confirmation_and_happens_once(app):
    await start_user(app, 301, name="فرستنده")
    await start_user(app, 302, name="گیرنده")
    await give(301, 500)
    await press(app, 301, "wal:trans:menu")
    asked = await send_private(app, 301, "@user302")
    assert "گیرنده" in asked.replies[0]["text"]
    small = await send_private(app, 301, "3")
    assert "حداقل" in small.replies[0]["text"]
    confirm = await send_private(app, 301, "۱۲۰")
    text = confirm.replies[0]["text"]
    assert "تأیید انتقال" in text and "۱۲۰" in text and "۳۸۰" in text  # موجودی بعد از انتقال در پیوی
    token = token_of(confirm.replies[0]["reply_markup"])
    # تا تأیید نشده چیزی جابه‌جا نشده است
    assert (await get_user(301)).coins == 500

    done = await press(app, 301, f"wal:tc:{token}")
    assert "انتقال انجام شد" in done.edits[-1]["text"]
    assert ((await get_user(301)).coins, (await get_user(302)).coins) == (380, 120)
    received = [m for m in app.bot.sent if m["chat_id"] == 302]
    assert received and "+۱۲۰" in received[-1]["text"]

    # دوبار زدن همان دکمه دوباره منتقل نمی‌کند
    again = await press(app, 301, f"wal:tc:{token}")
    assert again.answers[0] == (texts.WALLET_EXPIRED, True)
    assert ((await get_user(301)).coins, (await get_user(302)).coins) == (380, 120)
    assert await audit() == []


async def test_group_transfer_by_reply_only_the_sender_can_confirm(app):
    await start_user(app, 311, name="فرستنده")
    await start_user(app, 312, name="گیرنده")
    await give(311, 200)
    update, context = make_update(app, 311, chat_id=GROUP_ID, chat_type="supergroup", text="/transfer 50")
    update.effective_message.reply_to_message = SimpleNamespace(from_user=tg_user(312, "گیرنده"))
    await wallet_handlers.transfer_cmd(update, context)
    ask = update.replies[0]
    assert "۵۰" in ask["text"] and "موجودی تو بعد" not in ask["text"]  # موجودی جلوی گروه نشان داده نمی‌شود
    token = token_of(ask["reply_markup"])

    stranger = await press(app, 312, f"wal:tc:{token}", chat_id=GROUP_ID, chat_type="supergroup")
    assert stranger.answers[0] == (texts.WALLET_NOT_YOUR_TRANSFER, True)
    assert (await get_user(312)).coins == 0

    done = await press(app, 311, f"wal:tc:{token}", chat_id=GROUP_ID, chat_type="supergroup")
    assert "انتقال انجام شد" in done.edits[-1]["text"] and "موجودی" not in done.edits[-1]["text"]
    assert ((await get_user(311)).coins, (await get_user(312)).coins) == (150, 50)


async def test_transfer_can_be_cancelled_and_checks_balance(app):
    await start_user(app, 321)
    await start_user(app, 322)
    await give(321, 100)
    update, context = make_update(app, 321, text="/transfer @user322 500")
    context.user_data = user_data(app, 321)
    await wallet_handlers.transfer_cmd(update, context)
    assert "کافی نیست" in update.replies[0]["text"]

    update, context = make_update(app, 321, text="/transfer 987654 40")
    await wallet_handlers.transfer_cmd(update, context)
    assert "پیدا نشد" in update.replies[0]["text"]

    update, context = make_update(app, 321, text="/transfer @user322 40")
    await wallet_handlers.transfer_cmd(update, context)
    token = token_of(update.replies[0]["reply_markup"])
    cancelled = await press(app, 321, f"wal:tx:{token}")
    assert cancelled.edits[-1]["text"] == texts.WALLET_TRANSFER_CANCELLED_TEXT
    late = await press(app, 321, f"wal:tc:{token}")
    assert late.answers[0] == (texts.WALLET_EXPIRED, True)
    assert (await get_user(321)).coins == 100


# ====================================================================== فروش سکه
async def test_sell_flow_validates_the_card_and_asks_before_debiting(app):
    await start_user(app, 331, name="فروشنده")
    await give(331, 350)
    menu = await press(app, 331, "wal:sell:menu")
    labels = [b.callback_data for b in buttons_of(menu.edits[-1]["reply_markup"])]
    assert "wal:sell:p:100" in labels and "wal:sell:p:200" in labels and "wal:sell:p:350" in labels
    await press(app, 331, "wal:sell:p:200")
    typo = await send_private(app, 331, "6037991234567890 علی محمدی")  # یک رقم اشتباه
    assert "معتبر نیست" in typo.replies[0]["text"]
    confirm = await send_private(app, 331, "6037-9912-3456-7893 علی محمدی")
    assert "6037 9912 3456 7893" in confirm.replies[0]["text"] and "علی محمدی" in confirm.replies[0]["text"]
    assert (await get_user(331)).coins == 350  # هنوز چیزی کم نشده

    done = await press(app, 331, "wal:sell:ok")
    assert "درخواست فروش ثبت شد" in done.edits[-1]["text"]
    assert (await get_user(331)).coins == 150
    req = await sync_to_async(SellRequest.objects.get)()
    assert (req.coins, req.amount_toman, req.card_number, req.card_holder) == (200, 200_000, "6037991234567893", "علی محمدی")
    alerts = [m for m in app.bot.sent if m["chat_id"] == ADMIN]
    assert alerts and "درخواست فروش" in alerts[-1]["text"] and "6037991234567893" in alerts[-1]["text"]
    # دوبار زدن تأیید، درخواست دوم نمی‌سازد
    again = await press(app, 331, "wal:sell:ok")
    assert again.answers[0] == (texts.WALLET_EXPIRED, True)
    assert await sync_to_async(SellRequest.objects.count)() == 1
    assert await audit() == []


async def test_admin_refunds_a_sell_request_once(app):
    await start_user(app, 341)
    await start_user(app, ADMIN, name="مدیر")
    await give(341, 300)
    await press(app, 341, "wal:sell:p:100")
    await send_private(app, 341, "6037991234567893 علی")
    await press(app, 341, "wal:sell:ok")
    req = await sync_to_async(SellRequest.objects.get)()

    ask = await press(app, ADMIN, f"adm:sell:rej:{req.pk}", handler=wallet_handlers.admin_sell_callback)
    sure = [b.callback_data for b in buttons_of(ask.edits[-1]["reply_markup"])]
    assert f"adm:sell:crej:{req.pk}" in sure  # دو مرحله‌ای
    await press(app, ADMIN, f"adm:sell:crej:{req.pk}", handler=wallet_handlers.admin_sell_callback)
    assert (await get_user(341)).coins == 300
    twice = await press(app, ADMIN, f"adm:sell:cpay:{req.pk}", handler=wallet_handlers.admin_sell_callback)
    assert "قبلاً بررسی شده" in twice.answers[0][0]
    assert (await sync_to_async(SellRequest.objects.get)()).status == SellRequest.Status.REJECTED
    notes = [m["text"] for m in app.bot.sent if m["chat_id"] == 341]
    assert any("برگشت" in t for t in notes)
    assert await audit() == []


# ====================================================================== شارژ با رسید
async def test_topup_receipt_reaches_admins_and_is_credited_once(app):
    await start_user(app, 351, name="خریدار")
    await start_user(app, ADMIN, name="مدیر")
    from wallet.models import EconomySettings

    await sync_to_async(lambda: EconomySettings.objects.filter(pk=EconomySettings.load().pk).update(card_number="6037991234567893", card_holder="وینزون"))()
    pay = await press(app, 351, "wal:topup:p:100")
    assert "6037991234567893" in pay.edits[-1]["text"] and "۱۱۰٬۰۰۰" in pay.edits[-1]["text"]
    no_photo = await send_private(app, 351, "واریز کردم")
    assert "عکس رسید" in no_photo.replies[0]["text"]
    got = await send_private(app, 351, photo="RECEIPT-FILE")
    assert "رسید دریافت شد" in got.replies[0]["text"]
    req = await sync_to_async(TopUpRequest.objects.get)()
    assert (req.coins, req.total_toman, req.receipt_photo_id) == (100, 110_000, "RECEIPT-FILE")
    alert = [m for m in app.bot.sent if m["chat_id"] == ADMIN and m.get("photo") == "RECEIPT-FILE"]
    assert alert and "۱۰٪" in alert[-1]["text"]

    await press(app, ADMIN, f"adm:top:app:{req.pk}", handler=wallet_handlers.admin_topup_callback, photo=True)
    done = await press(app, ADMIN, f"adm:top:capp:{req.pk}", handler=wallet_handlers.admin_topup_callback, photo=True)
    assert "تأیید و شارژ شد" in done.edits[-1]["text"]
    assert (await get_user(351)).coins == 100
    told = [m["text"] for m in app.bot.sent if m["chat_id"] == 351]
    assert any("تأیید شد" in t and "#" in t for t in told)
    # ادمین دوم روی پیام کهنه‌ی خودش دوباره تأیید می‌زند: سکه‌ی اضافه داده نمی‌شود
    other = await press(app, 639344728, f"adm:top:capp:{req.pk}", handler=wallet_handlers.admin_topup_callback, photo=True)
    assert "قبلاً بررسی شده" in other.answers[0][0]
    assert (await get_user(351)).coins == 100
    assert await sync_to_async(CoinTransaction.objects.filter(type=TxType.TOPUP).count)() == 1
    assert await audit() == []


async def test_non_admin_cannot_review_requests(app):
    await start_user(app, 361)
    await give(361, 200)
    req = await sync_to_async(lambda: TopUpRequest.objects.create(
        user=TelegramUser.objects.get(tg_id=361), coins=10, amount_toman=1, fee_toman=0, total_toman=1
    ))()  # fmt: skip
    attempt = await press(app, 361, f"adm:top:capp:{req.pk}", handler=wallet_handlers.admin_topup_callback)
    assert attempt.answers[0] == (texts.ADMIN_ONLY, True)
    assert (await get_user(361)).coins == 200


# ====================================================================== پنل مدیریت
async def test_admin_panel_lists_and_approves_topups_from_the_panel(app):
    await start_user(app, ADMIN, name="مدیر")
    await start_user(app, 371)
    reqs = await sync_to_async(lambda: [
        TopUpRequest.objects.create(user=TelegramUser.objects.get(tg_id=371), coins=c, amount_toman=c * 1000,
                                    fee_toman=c * 100, total_toman=c * 1100, receipt_photo_id=f"R{c}")
        for c in (10, 20)
    ])()  # fmt: skip
    update, context = make_update(app, ADMIN, text="/admin")
    context.user_data = user_data(app, ADMIN)
    await admin_handlers.admin_cmd(update, context)
    panel = update.replies[0]
    assert "پنل مدیریت" in panel["text"] and "<b>۲</b> رسید شارژ" in panel["text"]
    listing = await press(app, ADMIN, "adm:topup:list:0", handler=admin_handlers.admin_callback)
    photo = [m for m in app.bot.sent if m.get("photo") == "R10"]
    assert photo or listing.edits  # رسید با عکسش نشان داده می‌شود
    await press(app, ADMIN, f"adm:top:capp:{reqs[0].pk}:p", handler=wallet_handlers.admin_topup_callback, photo=True)
    assert (await get_user(371)).coins == 10
    # بعد از رسیدگی، درخواست بعدی (حالا تنها درخواست مانده) نشان داده می‌شود
    shown = [m["text"] for m in app.bot.sent] + [e["text"] or "" for e in app.bot.edits]
    assert any("رسید شارژ (۱ از ۱)" in t for t in shown)
    toggled = await press(app, ADMIN, "adm:daily:toggle", handler=admin_handlers.admin_callback)
    assert toggled.answers and "خاموش" in toggled.answers[0][0]


async def test_admin_broadcast_from_the_panel_asks_first(app):
    await start_user(app, ADMIN, name="مدیر")
    await start_user(app, 381)
    await press(app, ADMIN, "adm:bcast:prompt", handler=admin_handlers.admin_callback)
    update, context = make_update(app, ADMIN, text="سلام به همه")
    context.user_data = user_data(app, ADMIN)
    update.effective_message.photo, update.effective_message.document, update.effective_message.caption = [], None, None
    await wallet_handlers.private_message(update, context)
    assert "فرستاده شود" in update.replies[0]["text"]
    assert not [m for m in app.bot.sent if m.get("copy_of")]
    await press(app, ADMIN, "adm:bcast:go", handler=admin_handlers.admin_callback)
    import asyncio

    await asyncio.gather(*app.tasks)
    copies = [m for m in app.bot.sent if m.get("copy_of")]
    assert {m["chat_id"] for m in copies} >= {381, ADMIN}


async def test_wallet_history_button_works(app):
    await start_user(app, 391)
    await give(391, 70)
    update, context = callback_update(app, 391, "pm:history")
    await private.menu_callback(update, context)
    assert "تراکنش" in update.replies[0]["text"] and "۷۰" in update.replies[0]["text"]


async def test_mini_app_wallet_shortcuts_open_the_right_section(app):
    async def start(tg_id, payload):
        update, context = make_update(app, tg_id, text=f"/start {payload}")
        context.user_data = user_data(app, tg_id)
        await private.start(update, context)
        return update

    await start_user(app, 401)
    await give(401, 150)
    for payload, phrase in (("wallet", "کیف پول من"), ("topup", "شارژ کیف پول"), ("sell", "فروش سکه"), ("transfer", "آیدی عددی")):
        update = await start(401, payload)
        assert len(update.replies) == 1 and phrase in update.replies[0]["text"], payload
    assert user_data(app, 401)["wallet_flow"] == {"step": "transfer_target"}
    # کاربر تازه اول خوش‌آمد و منو را می‌بیند، بعد همان بخش
    fresh = await start(402, "topup")
    assert "خوش آمدی" in fresh.replies[0]["text"] and "شارژ کیف پول" in fresh.replies[1]["text"]
