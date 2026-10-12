"""تست handlerهای ربات با Update ساختگی (بدون اتصال به تلگرام)."""

import itertools
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings

from bot import render
from bot.handlers import admin as admin_handlers
from bot.handlers import flow, group, group_settings, private
from bot.handlers import shop as shop_handlers
from bot.runner import MatchManager
from bot.ui import style_of
from core import texts
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
    answers, edits, deleted, replies = [], [], [], []

    async def answer(text=None, show_alert=False, **kwargs):
        answers.append((text, show_alert))

    async def reply_text(text, **kwargs):
        replies.append({"text": text, **kwargs})
        return SimpleNamespace(message_id=message_id + 9000)

    async def edit_message_text(text, **kwargs):
        edits.append({"text": text, **kwargs})

    async def edit_message_reply_markup(markup=None, **kwargs):
        edits.append({"text": None, "reply_markup": markup})

    async def delete():
        deleted.append(True)

    query = SimpleNamespace(
        id=f"q{next(_ids)}",
        data=data,
        message=SimpleNamespace(message_id=message_id, delete=delete, reply_text=reply_text),
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
    update.answers, update.edits, update.deleted, update.replies = answers, edits, deleted, replies
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
    assert "جایزه‌ی امروز را گرفته‌ای" in again.replies[0]["text"]

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
    assert stranger.answers[0][1] is True and "شخص دیگری" in stranger.answers[0][0]

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
    assert "در جریان است" in blocked.replies[0]["text"]
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
    menu, menu_id = await open_game_menu(app, 95)
    assert any("سیخ‌زن" in b.text for b in buttons_of(menu.replies[0]["reply_markup"]))
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
        too_fast += any(text == texts.TOO_FAST for text, _ in update.answers)
    # حد ۴ کلیک در ثانیه است؛ تعداد دقیق ردشده‌ها به سرعت اجرای تست بستگی دارد
    assert too_fast >= 1


# ====================================================================== دکمه‌های رنگی، منوی پیوی و قوانین
async def test_start_shows_a_coloured_menu_and_its_buttons_work(app):
    first = await start_user(app, 201)
    menu = buttons_of(first.replies[0]["reply_markup"])
    by_data = {b.callback_data: b for b in menu if b.callback_data}
    assert {"pm:daily", "pm:me", "pm:arcade", "pm:shop", "pm:invite", "pm:rules", "pm:help"} <= set(by_data)
    assert style_of(by_data["pm:daily"]) == "success"
    add_button = next(b for b in menu if b.url)
    assert "startgroup" in add_button.url and style_of(add_button) == "primary"

    async def press(data):
        update, context = make_callback(app, 201, data, 1, chat_id=201, chat_type="private")
        await private.menu_callback(update, context)
        return update

    assert "جایزه‌ی روزانه" in (await press("pm:daily")).replies[0]["text"]
    assert "علی" in (await press("pm:me")).replies[0]["text"]
    assert "راهنما" in (await press("pm:help")).replies[0]["text"]
    assert "فروشگاه" in (await press("pm:shop")).replies[0]["text"]
    assert "قوانین کلی" in (await press("pm:rules")).replies[0]["text"]
    assert (await press("pm:nonsense")).replies == []
    # همان دکمه‌ها در گروه کاری نمی‌کنند
    update, context = make_callback(app, 201, "pm:daily", 1)
    await private.menu_callback(update, context)
    assert update.replies == []


async def test_rules_command_lists_games_and_shows_each_games_rules(app):
    await start_user(app, 211)
    update, context = make_update(app, 211, chat_id=GROUP_ID, chat_type="supergroup", text="/rules")
    await group.rules(update, context)
    home = update.replies[0]
    assert "قوانین کلی" in home["text"] and texts.COINS_NOTE in home["text"]
    assert [b.callback_data for b in buttons_of(home["reply_markup"])] == ["rules:t", "rules:a"]

    listing = await click(app, 211, "rules:t", 1, group.rules_callback)
    labels = [b.text for b in buttons_of(listing.edits[-1]["reply_markup"])]
    assert any("شطرنج" in label for label in labels) and not any("سیخ‌زن" in label for label in labels)
    arcade = await click(app, 211, "rules:a", 1, group.rules_callback)
    assert any("سیخ‌زن" in b.text for b in buttons_of(arcade.edits[-1]["reply_markup"]))

    chess = await click(app, 211, "rules:g:chess", 1, group.rules_callback)
    text = chess.edits[-1]["text"]
    assert "قوانین شطرنج" in text and "۹۰ ثانیه" in text and "۲ بازیکن" in text
    assert buttons_of(chess.edits[-1]["reply_markup"])[0].callback_data == "rules:t"
    pins = await click(app, 211, "rules:g:arcade_pins", 1, group.rules_callback)
    assert "قوانین سیخ‌زن" in pins.edits[-1]["text"] and "بهترین امتیازت" in pins.edits[-1]["text"]
    unknown = await click(app, 211, "rules:g:nope", 1, group.rules_callback)
    assert unknown.edits == []


async def test_lobby_has_coloured_buttons_and_a_private_rules_popup(app):
    await start_user(app, 221)
    menu, _ = await open_game_menu(app, 221)
    styles = {b.text: style_of(b) for b in buttons_of(menu.replies[0]["reply_markup"])}
    assert styles[texts.CLOSE_BTN] == "danger" and "primary" in styles.values() and "success" in styles.values()

    keyboard = render.lobby_keyboard(7, "test_bot", "chess")
    cells = {b.callback_data or "url": b for b in buttons_of(keyboard)}
    assert style_of(cells["j:7"]) == "success" and style_of(cells["x:7"]) == "danger"
    assert style_of(cells["url"]) == "primary" and "rl:chess" in cells

    popup = await click(app, 221, "rl:chess", 1, group.rules_alert_callback)
    text, alert = popup.answers[0]
    assert alert is True and len(text) <= 200 and "مهره" in text
    silent = await click(app, 221, "rl:nope", 1, group.rules_alert_callback)
    assert silent.answers == [(None, False)]


async def test_buttons_of_a_finished_game_say_the_game_is_over(app):
    await start_user(app, 231)
    update, context = make_callback(app, 231, "g:999:m:0", 1)
    await group.game_callback(update, context)
    assert update.answers == [(texts.GAME_OVER, False)]


async def test_shop_confirmation_escapes_item_names(app):
    await start_user(app, 241)
    item = await sync_to_async(ShopItem.objects.create)(
        kind="title", name="<b>تند</b>", value="A&B", price=10, is_active=True
    )
    update = await click(app, 241, f"shop:i:{item.pk}", 1, shop_handlers.shop_callback)
    text = update.edits[-1]["text"]
    assert "&lt;b&gt;تند&lt;/b&gt;" in text and "A&amp;B" in text
    confirm = buttons_of(update.edits[-1]["reply_markup"])[0]
    assert style_of(confirm) == "success"


# ====================================================================== منوی کامل بازی‌ها و آرکیدِ راه‌اندازی‌نشده
async def test_game_menu_shows_every_game_on_one_screen(app):
    await start_user(app, 251)
    menu, menu_id = await open_game_menu(app, 251)
    buttons = buttons_of(menu.replies[0]["reply_markup"])
    games = [b for b in buttons if (b.callback_data or "").startswith("n:g:")]
    arcade = [b for b in games if b.callback_data.startswith("n:g:arcade_")]
    assert len(games) == 26 and len(arcade) == 14
    assert {style_of(b) for b in arcade} == {"success"}
    assert {style_of(b) for b in games if b not in arcade} == {"primary"}
    labels = " ".join(b.text for b in games)
    for title in ("هیزم‌شکن", "موش‌زن", "مار کلاسیک", "شطرنج", "دوز چهارتایی", "کوییز"):
        assert title in labels
    assert "۱۲ بازی گروهی" in menu.replies[0]["text"] and "۱۴ بازی آرکید" in menu.replies[0]["text"]
    # دکمه‌ی عنوان بخش آرکید فقط توضیح می‌دهد و منو را عوض نمی‌کند
    header = await click(app, 251, "n:h", menu_id)
    assert header.answers[0] == (texts.ARCADE_HEADER_NOTE, True) and header.edits == []
    assert len(texts.ARCADE_HEADER_NOTE) <= 200
    # برگشت از اولین مرحله‌ی یک بازی آرکید به همان منوی کامل می‌رسد
    await click(app, 251, "n:g:arcade_timber", menu_id)
    back = await click(app, 251, "n:b", menu_id)
    assert len(buttons_of(back.edits[-1]["reply_markup"])) == len(buttons)


async def test_arcade_games_are_not_offered_until_the_mini_app_is_set_up(app, settings):
    settings.MINIAPP_BASE_URL = ""
    await start_user(app, 261)
    menu, menu_id = await open_game_menu(app, 261)
    data = [b.callback_data for b in buttons_of(menu.replies[0]["reply_markup"])]
    assert not any((d or "").startswith("n:g:arcade_") for d in data) and "n:h" not in data
    assert "راه‌اندازی مینی‌اپ" in menu.replies[0]["text"] and "۱۲ بازی گروهی" in menu.replies[0]["text"]
    stale = await click(app, 261, "n:g:arcade_timber", menu_id)
    assert stale.answers[0] == (texts.MENU_EXPIRED, True)

    from bot.handlers import arcade as arcade_handlers

    update, context = make_update(app, 261, text="/arcade")
    await arcade_handlers.arcade(update, context)
    assert update.replies[0]["text"] == texts.ARCADE_NOT_CONFIGURED
    await start_user(app, 999)  # سوپرادمین تست راهنمای راه‌اندازی را هم می‌بیند
    update, context = make_update(app, 999, text="/arcade")
    await arcade_handlers.arcade(update, context)
    assert "MINIAPP_BASE_URL" in update.replies[0]["text"] and "/newapp" in update.replies[0]["text"]


async def test_practice_menu_lists_all_arcade_games_when_set_up(app):
    from bot.handlers import arcade as arcade_handlers

    await start_user(app, 271)
    update, context = make_update(app, 271, text="/arcade")
    await arcade_handlers.arcade(update, context)
    buttons = buttons_of(update.replies[0]["reply_markup"])
    assert len(buttons) == 14 and all(b.web_app.url.startswith("https://arcade.test/arcade/play/") for b in buttons)


async def test_game_menu_warns_when_the_bot_cannot_read_group_messages(app):
    await start_user(app, 291)
    app.bot_data["reads_all"] = False  # Privacy Mode روشن است
    menu, _ = await open_game_menu(app, 291)
    assert texts.GAME_MENU_CANNOT_READ in menu.replies[0]["text"]
    app.bot.admins.add((GROUP_ID, 0))  # ربات ادمین گروه شد
    reset_clients()
    menu, _ = await open_game_menu(app, 291)
    assert texts.GAME_MENU_CANNOT_READ not in menu.replies[0]["text"]
