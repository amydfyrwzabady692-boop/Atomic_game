import itertools

import pytest
from django.db import connection

from core.models import TelegramGroup, TelegramUser
from games import config as game_config
from wallet.models import TxType
from wallet.services import apply_transaction

_ids = itertools.count(1000)

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql", reason="قفل ردیفی واقعی فقط روی PostgreSQL تست می‌شود"
)


@pytest.fixture
def make_user(db):
    def _make(coins: int = 0, **kwargs) -> TelegramUser:
        n = next(_ids)
        kwargs.setdefault("started_bot", True)
        user = TelegramUser.objects.create(tg_id=n, first_name=kwargs.pop("first_name", f"کاربر{n}"), **kwargs)
        if coins:
            apply_transaction(user, coins, TxType.ADMIN_GRANT, f"test-grant:{user.pk}")
        return user

    return _make


@pytest.fixture
def group(db):
    return TelegramGroup.objects.create(chat_id=-100123, title="گروه تست")


@pytest.fixture(autouse=True)
def fresh_game_settings():
    """کش تنظیمات بازی‌ها بین تست‌ها نشت نکند."""
    game_config.reset()
    yield
    game_config.reset()


@pytest.fixture(autouse=True)
def close_edit_queues(monkeypatch):
    """ویرایش‌های معوق هر تست بسته می‌شوند تا task نیمه‌کاره‌ای بعد از پایان تست باقی نماند."""
    from bot.tg import EditQueue

    created = []
    original = EditQueue.__init__

    def tracking(self, *args, **kwargs):
        original(self, *args, **kwargs)
        created.append(self)

    monkeypatch.setattr(EditQueue, "__init__", tracking)
    yield
    for queue in created:
        tasks = [task for task in queue._tasks.values() if not task.done()]
        if not tasks:
            continue
        loop = tasks[0].get_loop()
        if not loop.is_closed() and not loop.is_running():
            loop.run_until_complete(queue.close())


@pytest.fixture
def economy_settings(db):
    """تنظیمات اقتصاد (پنل ادمین) را برای یک تست عوض می‌کند: ``economy_settings(daily_enabled=True)``"""
    from wallet.models import EconomySettings

    def _set(**fields) -> EconomySettings:
        obj = EconomySettings.load()
        for name, value in fields.items():
            setattr(obj, name, value)
        obj.save()
        return obj

    return _set
