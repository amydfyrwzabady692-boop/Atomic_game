"""تست handlerهای ربات با Update ساختگی (بدون اتصال به تلگرام)."""

import itertools
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings

from bot.handlers import admin as admin_handlers
from bot.handlers import flow, group, group_settings, private
from bot.handlers import shop as shop_handlers
from bot.runner import MatchManager
from core.models import TelegramGroup, TelegramUser
from core.redis import reset_clients
from games.models import Match, MatchStatus
from shop.models import ShopItem, UserItem
from shop.services import seed_default_items
from wallet.management.commands.audit_wallets import find_mismatches
from wallet.models import CoinTransaction, TxType

from .fake_telegram import FakeApplication

pytestmark = pytest.mark.django_db(transaction=True)

GROUP_ID = -100555
_ids = itertools.count(1)


@pytest.fixture(autouse=True)
def _fresh_redis():
    reset_clients()
    yield
    reset_clients()


@pytest.fixture(autouse=True)
def _no_rate_limit(request, monkeypatch):
    """تست‌ها خیلی سریع‌تر از یک کاربر واقعی دستور می‌فرستند؛ محدودیت نرخ جداگانه تست می‌شود."""
    if "rate_limited" in request.node.name:
        return

    async def always(*args, **kwargs):
        return True

    monkeypatch.setattr("bot.ratelimit.allow", always)


@pytest.fixture
def app():
    application = FakeApplication()
    application.bot_data["manager"] = MatchManager(application)
    return application


def tg_user(tg_id, name="علی"):
    return SimpleNamespace(id=tg_id, first_name=name, username=f"user{tg_id}", is_bot=False)


def make_update(app, tg_id, chat_id=None, chat_type="private", text="", name="علی"):
    """یک پیام دستور. پاسخ‌های ربات در ``update.replies`` جمع می‌شوند."""
    replies = []
    message_id = 1000 + next(_ids)

    async def reply_text(text, **kwargs):
        replies.append({"text": text, **kwargs})
        return SimpleNamespace(message_id=message_id + 5000)

    chat_id = chat_id if chat_id is not None else tg_id
    message = SimpleNamespace(
        text=text,
        message_id=message_id,
        chat_id=chat_id,
        reply_text=reply_text,
        reply_to_message=None,
        forward_origin=None,
        via_bot=None,
        date=datetime.now(UTC),
    )
    update = SimpleNamespace(
        update_id=next(_ids),
        effective_user=tg_user(tg_id, name),
        effective_chat=SimpleNamespace(id=chat_id, type=chat_type, title="گروه تست"),
        effective_message=message,
        callback_query=None,
        my_chat_member=None,
    )
    update.replies = replies
    context = SimpleNamespace(
        args=text.split()[1:], bot=app.bot, application=app, bot_data=app.bot_data
    )
    return update, context


def make_callback(app, tg_id, data, message_id, chat_id=GROUP_ID, chat_type="supergroup"):
    """یک کلیک دکمه‌ی اینلاین. جواب‌ها در ``update.answers`` و ویرایش‌ها در ``update.edits``."""
    answers, edits, deleted = [], [], []

    async def answer(text=None, show_alert=False, **kwargs):
        answers.append((text, show_alert))

    async def edit_message_text(text, **kwargs):
        edits.append({"text": text, **kwargs})

    async def edit_message_reply_markup(markup=None, **kwargs):
        edits.append({"text": None, "reply_markup": markup})

    async def delete():
        deleted.append(True)

    query = SimpleNamespace(
        id=f"q{next(_ids)}",
        data=data,
        message=SimpleNamespace(message_id=message_id, delete=delete),
        answer=answer,
        edit_message_text=edit_message_text,
        edit_message_reply_markup=edit_message_reply_markup,
    )
    update = SimpleNamespace(
        update_id=next(_ids),
        effective_user=tg_user(tg_id),
        effective_chat=SimpleNamespace(id=chat_id, type=chat_type, title="گروه تست"),
        effective_message=query.message,
        callback_query=query,
    )
    update.answers, update.edits, update.deleted = answers, edits, deleted
    context = SimpleNamespace(args=[], bot=app.bot, application=app, bot_data=app.bot_data)
    return update, context


def buttons_of(markup):
    return [button for row in markup.inline_keyboard for button in row]


@sync_to_async
def get_user(tg_id):
    return TelegramUser.objects.get(tg_id=tg_id)


async def start_user(app, tg_id, payload="", name="علی"):
    update, context = make_update(app, tg_id, text=f"/start {payload}".strip(), name=name)
    await private.start(update, context)
    return update


# ====================================================================== /start و اقتصاد
async def test_start_gives_signup_bonus_once(app):
    first = await start_user(app, 11)
    assert "هدیه‌ی شروع" in first.replies[0]["text"]
    user = await get_user(11)
    assert user.coins == settings.SIGNUP_BONUS and user.started_bot
    again = await start_user(app, 11)
    assert "خوش برگشتی" in again.replies[0]["text"]
    assert (await get_user(11)).coins == settings.SIGNUP_BONUS
    assert await sync_to_async(CoinTransaction.objects.filter(type=TxType.SIGNUP_BONUS).count)() == 1


async def test_start_with_referral_link_records_referrer_but_not_self(app):
    await start_user(app, 21, name="دعوت‌کننده")
    invited = await start_user(app, 22, payload="ref_21")
    assert "دعوت‌کننده" in invited.replies[0]["text"]
    assert (await get_user(22)).referred_by_id == (await get_user(21)).pk
    await start_user(app, 23, payload="ref_23")  # خوددعوتی
    assert (await get_user(23)).referred_by_id is None
    # جایزه‌ی دعوت هنوز داده نشده (دعوت‌شده بازی نکرده)
    assert not await sync_to_async(CoinTransaction.objects.filter(type=TxType.REFERRAL).exists)()


async def test_daily_only_in_private_and_once_a_day(app):
    await start_user(app, 31)
    update, context = make_update(app, 31, text="/daily")
    await private.daily(update, context)
    assert "جایزه‌ی روزانه" in update.replies[0]["text"]
    assert (await get_user(31)).coins == settings.SIGNUP_BONUS + settings.DAILY_BASE

    again, context = make_update(app, 31, text="/daily")
    await private.daily(again, context)
    assert "امروز جایزه‌ت رو گرفتی" in again.replies[0]["text"]

    in_group, context = make_update(app, 31, chat_id=GROUP_ID, chat_type="supergroup", text="/daily")
    await private.daily(in_group, context)
    assert "پیوی" in in_group.replies[0]["text"]
    assert (await get_user(31)).coins == settings.SIGNUP_BONUS + settings.DAILY_BASE


async def test_me_history_and_invite(app):
    await start_user(app, 41)
    for handler, expected in [(private.me, "سطح"), (private.history, "هدیه‌ی ثبت‌نام"), (private.invite, "start=ref_41")]:
        update, context = make_update(app, 41)
        await handler(update, context)
        assert expected in update.replies[0]["text"]


async def test_banned_user_is_ignored(app):
    await start_user(app, 51)
    await sync_to_async(TelegramUser.objects.filter(tg_id=51).update)(is_banned=True)
    update, context = make_update(app, 51, text="/daily")
    await private.daily(update, context)
    assert update.replies[0]["text"].startswith("⛔️")
    assert (await get_user(51)).coins == settings.SIGNUP_BONUS


# ====================================================================== ساخت بازی در گروه
async def click(app, tg_id, data, message_id, handler=flow.new_game_callback):
    update, context = make_callback(app, tg_id, data, message_id)
    await handler(update, context)
    return update


async def open_game_menu(app, tg_id):
    update, context = make_update(app, tg_id, chat_id=GROUP_ID, chat_type="supergroup", text="/game")
    await flow.game(update, context)
    return update, update.effective_message.message_id + 5000


async def test_game_menu_flow_creates_lobby_and_only_creator_can_use_it(app):
    await start_user(app, 61)
    await start_user(app, 62)
    menu, menu_id = await open_game_menu(app, 61)
    labels = [b.text for b in buttons_of(menu.replies[0]["reply_markup"])]
    assert any("حساب سریع" in label for label in labels)
    assert any("آرکید" in label for label in labels)

    stranger = await click(app, 62, "n:g:quick_math", menu_id)
    assert stranger.answers[0][1] is True and "یکی دیگه" in stranger.answers[0][0]

    step = await click(app, 61, "n:g:quick_math", menu_id)
    assert "ورودی" in step.edits[-1]["text"]
    step = await click(app, 61, "n:f:100", menu_id)
    assert "تقسیم" in step.edits[-1]["text"]
    back = await click(app, 61, "n:b", menu_id)
    assert "ورودی" in back.edits[-1]["text"]
    await click(app, 61, "n:f:250", menu_id)
    step = await click(app, 61, "n:s:60-30-10", menu_id)
    assert "عضوگیری" in step.edits[-1]["text"]
    await click(app, 61, "n:t:30", menu_id)

    match = await sync_to_async(Match.objects.select_related("group").get)()
    assert (match.game_type, match.entry_fee, match.prize_split, match.status) == (
        "quick_math",
        250,
        [60, 30, 10],
        MatchStatus.LOBBY,
    )
    assert match.lobby_message_id == menu_id  # همان پیام منو به لابی تبدیل شد
    # سازنده خودکار عضو شده و ورودی‌اش کسر شده
    assert (await get_user(61)).coins == settings.SIGNUP_BONUS - 250
    manager = app.bot_data["manager"]
    assert manager.active[GROUP_ID].match_id == match.pk

    # نفر دوم با دکمه‌ی «شرکت» وارد می‌شود؛ کلیک دوباره هزینه‌ای ندارد
    joined = await click(app, 62, f"j:{match.pk}", menu_id, group.join_callback)
    assert "وارد شدی" in joined.answers[0][0]
    twice = await click(app, 62, f"j:{match.pk}", menu_id, group.join_callback)
    assert "قبلاً" in twice.answers[0][0]
    assert (await get_user(62)).coins == settings.SIGNUP_BONUS - 250

    # تا وقتی مسابقه فعال است منوی جدید باز نمی‌شود
    blocked, _ = await open_game_menu(app, 62)
    assert "در جریانه" in blocked.replies[0]["text"]
    assert await sync_to_async(find_mismatches)() == []


async def test_join_requires_private_start_and_enough_coins(app):
    await start_user(app, 71)
    _, menu_id = await open_game_menu(app, 71)
    for data in ("n:g:quick_math", "n:f:1000", "n:s:100", "n:t:60"):
        await click(app, 71, data, menu_id)
    match = await sync_to_async(Match.objects.get)()

    newcomer = await click(app, 72, f"j:{match.pk}", menu_id, group.join_callback)
    assert newcomer.answers[0][1] is True and "/start" in newcomer.answers[0][0]

    await start_user(app, 73)
    await sync_to_async(TelegramUser.objects.filter(tg_id=73).update)(coins=10)
    await sync_to_async(CoinTransaction.objects.filter(user__tg_id=73).count)()
    poor = await click(app, 73, f"j:{match.pk}", menu_id, group.join_callback)
    assert poor.answers[0][1] is True and "/daily" in poor.answers[0][0]
    assert await sync_to_async(match.players.count)() == 1


async def test_cancel_only_by_creator_or_admin(app):
    await start_user(app, 81)
    await start_user(app, 82)
    _, menu_id = await open_game_menu(app, 81)
    for data in ("n:g:quick_math", "n:f:100", "n:s:100", "n:t:60"):
        await click(app, 81, data, menu_id)
    match = await sync_to_async(Match.objects.get)()

    denied = await click(app, 82, f"x:{match.pk}", menu_id, group.cancel_callback)
    assert denied.answers[0][1] is True and "سازنده" in denied.answers[0][0]
    assert (await sync_to_async(Match.objects.get)()).status == MatchStatus.LOBBY

    app.bot.admins.add((GROUP_ID, 82))
    reset_clients()  # کش ادمین بودن
    update, context = make_update(app, 82, chat_id=GROUP_ID, chat_type="supergroup", text="/cancel")
    await group.cancel(update, context)
    assert (await sync_to_async(Match.objects.get)()).status == MatchStatus.CANCELLED
    assert (await get_user(81)).coins == settings.SIGNUP_BONUS  # ورودی برگشت


async def test_group_can_restrict_game_creation_to_admins(app):
    await start_user(app, 91)
    await sync_to_async(TelegramGroup.objects.create)(chat_id=GROUP_ID, title="x", allow_user_created_games=False)
    menu, _ = await open_game_menu(app, 91)
    assert "فقط ادمین‌ها" in menu.replies[0]["text"]


async def test_arcade_flow_asks_for_play_window(app):
    await start_user(app, 95)
    _, menu_id = await open_game_menu(app, 95)
    category = await click(app, 95, "n:c:stage", menu_id)
    assert any("سیخ‌زن" in b.text for b in buttons_of(category.edits[-1]["reply_markup"]))
    await click(app, 95, "n:g:arcade_pins", menu_id)
    await click(app, 95, "n:f:0", menu_id)
    step = await click(app, 95, "n:s:70-30", menu_id)
    assert "مدت مسابقه" in step.edits[-1]["text"]
    await click(app, 95, "n:w:5", menu_id)
    await click(app, 95, "n:t:60", menu_id)
    match = await sync_to_async(Match.objects.get)()
    assert match.game_type == "arcade_pins" and match.options["window_minutes"] == 5
    assert match.options["attempts"] == settings.ARCADE_DEFAULT_ATTEMPTS


# ====================================================================== پیام‌های بازی
async def test_group_text_routes_only_valid_player_messages(app):
    await start_user(app, 101)
    await start_user(app, 102)
    _, menu_id = await open_game_menu(app, 101)
    for data in ("n:g:quick_math", "n:f:0", "n:s:100", "n:t:30"):
        await click(app, 101, data, menu_id)
    match = await sync_to_async(Match.objects.get)()
    await click(app, 102, f"j:{match.pk}", menu_id, group.join_callback)
    manager = app.bot_data["manager"]
    active = manager.active[GROUP_ID]
    await app.job_queue.fire("lobby_close")
    answer = str(active.game.answer)

    async def say(tg_id, text, **overrides):
        update, context = make_update(app, tg_id, chat_id=GROUP_ID, chat_type="supergroup", text=text)
        for key, value in overrides.items():
            setattr(update.effective_message, key, value)
        await group.group_text(update, context)

    await say(999, answer)  # عضو مسابقه نیست
    await say(101, answer, forward_origin=object())  # فورواردی
    await say(101, answer, via_bot=object())  # از طریق ربات
    assert sum(active.game.scores.values()) == 0
    await say(102, answer)
    assert active.game.scores[(await get_user(102)).pk] == 10


# ====================================================================== تنظیمات گروه
async def test_settings_only_for_admins_and_toggles(app):
    await start_user(app, 111)
    update, context = make_update(app, 111, chat_id=GROUP_ID, chat_type="supergroup", text="/settings")
    await group_settings.settings_cmd(update, context)
    assert "فقط برای ادمین" in update.replies[0]["text"]

    app.bot.admins.add((GROUP_ID, 111))
    reset_clients()
    update, context = make_update(app, 111, chat_id=GROUP_ID, chat_type="supergroup", text="/settings")
    await group_settings.settings_cmd(update, context)
    assert "تنظیمات گروه" in update.replies[0]["text"]

    await click(app, 111, "set:users", 1, group_settings.settings_callback)
    await click(app, 111, "set:min", 1, group_settings.settings_callback)
    await click(app, 111, "set:tg:quiz", 1, group_settings.settings_callback)
    chat_group = await sync_to_async(TelegramGroup.objects.get)(chat_id=GROUP_ID)
    assert chat_group.allow_user_created_games is False and chat_group.min_entry == 50
    assert not chat_group.game_enabled("quiz") and chat_group.game_enabled("anagram")

    outsider = await click(app, 112, "set:users", 1, group_settings.settings_callback)
    assert outsider.answers[0][1] is True


# ====================================================================== سوپرادمین
async def test_grant_is_superadmin_only_and_logged_in_ledger(app):
    await start_user(app, 121)
    nobody, context = make_update(app, 121, text="/grant 121 500")
    await admin_handlers.grant(nobody, context)
    assert nobody.replies == [] and (await get_user(121)).coins == settings.SIGNUP_BONUS

    boss, context = make_update(app, settings.SUPERADMIN_IDS[0], text="/grant 121 500")
    await admin_handlers.grant(boss, context)
    assert "داده شد" in boss.replies[0]["text"]
    assert (await get_user(121)).coins == settings.SIGNUP_BONUS + 500
    tx = await sync_to_async(CoinTransaction.objects.get)(type=TxType.ADMIN_GRANT)
    assert tx.amount == 500
    assert any("از طرف مدیریت" in m["text"] for m in app.bot.sent if m["chat_id"] == 121)

    # همان update دوباره تحویل شود: سکه‌ی تکراری داده نمی‌شود
    await admin_handlers.grant(boss, context)
    assert (await get_user(121)).coins == settings.SIGNUP_BONUS + 500


async def test_ban_unban_and_stats(app):
    await start_user(app, 131)
    boss = settings.SUPERADMIN_IDS[0]
    update, context = make_update(app, boss, text="/ban 131")
    await admin_handlers.ban(update, context)
    assert (await get_user(131)).is_banned
    update, context = make_update(app, boss, text="/unban @user131")
    await admin_handlers.unban(update, context)
    assert not (await get_user(131)).is_banned
    update, context = make_update(app, boss, text="/stats")
    await admin_handlers.stats(update, context)
    assert "آمار ربات" in update.replies[0]["text"]


# ====================================================================== فروشگاه
async def test_shop_buy_and_equip(app):
    await start_user(app, 141)
    await sync_to_async(seed_default_items)()
    item = await sync_to_async(ShopItem.objects.filter(kind="emoji").order_by("price").first)()
    update, context = make_update(app, 141, text="/shop")
    await shop_handlers.shop(update, context)
    assert "فروشگاه" in update.replies[0]["text"]

    confirm = await click(app, 141, f"shop:i:{item.pk}", 1, shop_handlers.shop_callback)
    assert "قابل برگشت نیست" in confirm.edits[-1]["text"]
    bought = await click(app, 141, f"shop:b:{item.pk}", 1, shop_handlers.shop_callback)
    assert "خریدی" in bought.answers[0][0]
    user = await get_user(141)
    assert user.coins == settings.SIGNUP_BONUS - item.price
    owned = await sync_to_async(UserItem.objects.get)(user=user, item=item)
    assert owned.equipped

    toggled = await click(app, 141, f"shop:i:{item.pk}", 1, shop_handlers.shop_callback)
    assert "غیرفعال" in toggled.answers[0][0]
    assert await sync_to_async(CoinTransaction.objects.filter(type=TxType.SHOP).count)() == 1
    assert await sync_to_async(find_mismatches)() == []


# ====================================================================== محدودیت نرخ
async def test_commands_and_callbacks_are_rate_limited(app):
    await start_user(app, 151)
    replies = 0
    for _ in range(8):
        update, context = make_update(app, 151, text="/me")
        await private.me(update, context)
        replies += len(update.replies)
    assert 1 <= replies <= 3  # حداکثر ۳ دستور در ۲ ثانیه

    too_fast = 0
    for _ in range(10):
        update = await click(app, 151, "top:a:week", 1, group.top_callback)
        too_fast += any(text and "یواش" in text for text, _ in update.answers)
    assert too_fast >= 5
