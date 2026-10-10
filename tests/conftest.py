import itertools

import pytest
from django.db import connection

from core.models import TelegramGroup, TelegramUser
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
