"""پنل /admin ← «👥 گروه‌های ربات»: فهرست گروه‌ها با آمار، جزئیات زنده از تلگرام و بیرون بردن ربات."""

from datetime import timedelta

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone

from bot.handlers import admin as admin_handlers
from bot.handlers import common, groups_admin
from core import texts
from core.models import BotAdmin, TelegramGroup, TelegramUser
from core.redis import reset_clients
from games.models import Match

from .fake_telegram import FakeApplication
from .test_handlers import buttons_of, start_user
from .test_wallet_handlers import press

pytestmark = pytest.mark.django_db(transaction=True)
OWNER = 999


@pytest.fixture
def app():
    from bot.runner import MatchManager

    application = FakeApplication()
    application.bot_data["manager"] = MatchManager(application)
    application.user_data = {}
    return application


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


@sync_to_async
def seed_groups():
    creator = TelegramUser.objects.create(tg_id=5001, first_name="سازنده", started_bot=True)
    busy = TelegramGroup.objects.create(chat_id=-3001, title="گروه پرکار")
    quiet = TelegramGroup.objects.create(chat_id=-3002, title="گروه آرام", promo_enabled=False)
    gone = TelegramGroup.objects.create(chat_id=-3003, title="گروه قدیمی", is_active=False)
    now = timezone.now()
    for days in (0, 1, 2, 10):
        Match.objects.create(
            group=busy, creator=creator, game_type="quiz", entry_fee=0, prize_split=[100],
            join_deadline=now, min_players=2, max_players=10, created_at=now - timedelta(days=days),
        )  # fmt: skip
    Match.objects.filter(group=busy).update(created_at=now - timedelta(days=1))
    for i in range(10):
        TelegramGroup.objects.create(chat_id=-4000 - i, title=f"گروه {i}")
    return busy, quiet, gone


def panel(app, tg_id, data):
    return press(app, tg_id, data, handler=groups_admin.panel_callback)


def shown(update) -> str:
    return "\n".join([e["text"] or "" for e in update.edits] + [r["text"] for r in update.replies])


async def test_owner_sees_the_groups_with_activity_and_pages(app):
    await start_user(app, OWNER, name="مالک")
    busy, quiet, gone = await seed_groups()
    home = await admin_handlers.admin_panel_screen(await sync_to_async(TelegramUser.objects.get)(tg_id=OWNER))
    assert "adm:grp:a:0" in [b.callback_data for b in buttons_of(home[1])]

    first = await panel(app, OWNER, "adm:grp:a:0")
    text = shown(first)
    assert "فعال: <b>۱۲</b>" in text and "خارج‌شده: ۱" in text and "پیام دعوت روشن: ۱۱" in text
    # گروهی که آخرین مسابقه را داشته بالای فهرست است
    assert "۱. <b>گروه پرکار</b> — این هفته ۴ مسابقه" in text
    data = [b.callback_data for b in buttons_of(first.edits[-1]["reply_markup"])]
    assert f"adm:grp:show:{busy.pk}:a0" in data and "adm:grp:a:1" in data and "صفحه‌ی ۱ از ۲" in text
    second = await panel(app, OWNER, "adm:grp:a:1")
    assert "صفحه‌ی ۲ از ۲" in shown(second) and "adm:grp:a:0" in [b.callback_data for b in buttons_of(second.edits[-1]["reply_markup"])]

    left = await panel(app, OWNER, "adm:grp:l:0")
    assert "گروه قدیمی" in shown(left) and "گروه پرکار" not in shown(left)


async def test_group_detail_is_live_and_the_bot_can_leave_after_confirming(app):
    await start_user(app, OWNER, name="مالک")
    busy, _, _ = await seed_groups()
    app.bot_data["bot_id"] = 777
    app.bot.admins.add((busy.chat_id, 777))  # ربات ادمین گروه است
    detail = await panel(app, OWNER, f"adm:grp:show:{busy.pk}:a0")
    text = shown(detail)
    assert str(busy.chat_id) in text and "عضو: <b>۴۲</b>" in text and "✅ ادمین" in text and "کل: ۴" in text
    data = [b.callback_data for b in buttons_of(detail.edits[-1]["reply_markup"])]
    assert f"adm:grp:leave:{busy.pk}:a0" in data and "adm:grp:a:0" in data

    sure = await panel(app, OWNER, f"adm:grp:leave:{busy.pk}:a0")
    assert "بیرون برود" in shown(sure)
    assert not getattr(app.bot, "left", [])
    done = await panel(app, OWNER, f"adm:grp:leaveok:{busy.pk}:a0")
    assert app.bot.left == [busy.chat_id] and done.answers[-1][0] == texts.ADMIN_GROUP_LEFT_DONE
    assert not (await sync_to_async(TelegramGroup.objects.get)(pk=busy.pk)).is_active


async def test_groups_need_the_stats_permission_and_leaving_needs_settings(app):
    busy, _, _ = await seed_groups()
    await start_user(app, 6001, name="پشتیبان")
    await sync_to_async(BotAdmin.objects.create)(tg_id=6001, permissions=["support"])
    await common.refresh_admin_ids()
    denied = await panel(app, 6001, "adm:grp:a:0")
    assert denied.answers[-1] == (texts.ADMIN_NO_ACCESS, True)

    await start_user(app, 6002, name="آمار")
    await sync_to_async(BotAdmin.objects.create)(tg_id=6002, permissions=["stats"])
    await common.refresh_admin_ids()
    detail = await panel(app, 6002, f"adm:grp:show:{busy.pk}:a0")
    data = [b.callback_data for b in buttons_of(detail.edits[-1]["reply_markup"])]
    assert not any(d and d.startswith("adm:grp:leave") for d in data)
    refused = await panel(app, 6002, f"adm:grp:leaveok:{busy.pk}:a0")
    assert refused.answers[-1] == (texts.ADMIN_NO_ACCESS, True)
    assert (await sync_to_async(TelegramGroup.objects.get)(pk=busy.pk)).is_active
