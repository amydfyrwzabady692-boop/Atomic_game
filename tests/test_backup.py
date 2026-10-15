"""پشتیبان خودکار دیتابیس که در پیوی مدیرها فرستاده می‌شود."""

import gzip
import json
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from django.core.management import call_command

from bot import backup
from bot.handlers import admin as admin_handlers
from core import texts
from core.models import TelegramUser

pytestmark = pytest.mark.django_db(transaction=True)


class Recorder:
    def __init__(self):
        self.documents, self.messages = [], []

    async def send_document(self, chat_id, document, filename=None, caption=None, **kwargs):
        self.documents.append({"chat_id": chat_id, "data": document, "filename": filename, "caption": caption})
        return SimpleNamespace(message_id=1)

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append({"chat_id": chat_id, "text": text})
        return SimpleNamespace(message_id=2)


def test_backup_file_contains_the_data_and_restores(make_user):
    user = make_user(coins=75, first_name="پشتیبان")
    path, name = backup.make_backup()
    try:
        assert name.startswith("backup-") and name.endswith(".json.gz")
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            rows = json.load(handle)
        models = {row["model"] for row in rows}
        assert {"core.telegramuser", "wallet.cointransaction"} <= models
        assert not any(model.startswith(("contenttypes", "sessions")) for model in models)
        TelegramUser.objects.filter(pk=user.pk).update(first_name="عوض‌شده")
        call_command("loaddata", path, verbosity=0)
        assert TelegramUser.objects.get(pk=user.pk).first_name == "پشتیبان"
    finally:
        import os

        os.remove(path)


async def test_backup_is_sent_to_admins_and_too_big_files_are_reported(settings, monkeypatch):
    await sync_to_async(TelegramUser.objects.create)(tg_id=4242, first_name="الف")
    settings.BACKUP_CHAT_IDS = [11, 22]
    bot = Recorder()
    assert await backup.send_backup(bot) == 2
    assert [d["chat_id"] for d in bot.documents] == [11, 22]
    first = bot.documents[0]
    assert first["filename"].endswith(".json.gz") and gzip.decompress(first["data"]).startswith(b"[")
    assert "پشتیبان دیتابیس" in first["caption"]

    monkeypatch.setattr(backup, "TELEGRAM_FILE_LIMIT", 10)
    bot = Recorder()
    assert await backup.send_backup(bot) == 0
    assert bot.documents == [] and bot.messages[0]["text"] == texts.BACKUP_TOO_BIG

    settings.BACKUP_CHAT_IDS, settings.SUPERADMIN_IDS = [], []
    assert await backup.send_backup(Recorder()) == 0


async def test_backup_command_is_for_superadmins_only(monkeypatch):
    sent = []

    async def fake_send(bot, chat_ids=None):
        sent.append(chat_ids)
        return 1

    monkeypatch.setattr(backup, "send_backup", fake_send)

    async def run(tg_id):
        replies = []

        async def reply_text(text, **kwargs):
            replies.append(text)

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=tg_id, first_name="م", username="", is_bot=False),
            effective_chat=SimpleNamespace(id=tg_id, type="private"),
            effective_message=SimpleNamespace(reply_text=reply_text),
        )
        await admin_handlers.backup_cmd(update, SimpleNamespace(bot=Recorder(), args=[]))
        return replies

    assert await run(12345) == []  # کاربر عادی: هیچ جوابی
    assert await run(999) == [texts.BACKUP_STARTED] and sent == [[999]]
