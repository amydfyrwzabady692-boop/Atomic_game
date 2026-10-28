"""bot و job queue ساختگی برای تست لایه‌ی ربات بدون اتصال به تلگرام."""

import itertools
from types import SimpleNamespace


class FakeJob:
    def __init__(self, queue, callback, name, repeat):
        self.queue, self.callback, self.name, self.repeat = queue, callback, name, repeat
        self.removed = False

    def schedule_removal(self):
        self.removed = True


class FakeJobQueue:
    def __init__(self):
        self.jobs: list[FakeJob] = []

    def run_once(self, callback, when, name=None, **kwargs):
        job = FakeJob(self, callback, name or "", False)
        self.jobs.append(job)
        return job

    def run_repeating(self, callback, interval, first=None, name=None, **kwargs):
        job = FakeJob(self, callback, name or "", True)
        self.jobs.append(job)
        return job

    def run_daily(self, callback, time, days=(), name=None, **kwargs):
        return self.run_repeating(callback, 86400, name=name)

    def pending(self, suffix: str) -> list[FakeJob]:
        return [j for j in self.jobs if not j.removed and j.name.endswith(suffix)]

    async def fire(self, suffix: str) -> None:
        """اولین job فعال با این پسوند نام را اجرا می‌کند."""
        jobs = self.pending(suffix)
        assert jobs, f"no pending job named *{suffix}; have {[j.name for j in self.jobs if not j.removed]}"
        job = jobs[0]
        if not job.repeat:
            job.removed = True
        await job.callback(None)


class FakeBot:
    def __init__(self):
        self.sent: list[dict] = []
        self.edits: list[dict] = []
        self.deleted: list[tuple] = []
        self._ids = itertools.count(500)
        self.admins: set[tuple[int, int]] = set()
        self.dice_values: list[int] = []

    async def get_me(self):
        return SimpleNamespace(username="test_bot", id=1)

    async def send_message(self, chat_id, text, **kwargs):
        message_id = next(self._ids)
        self.sent.append({"chat_id": chat_id, "text": text, "message_id": message_id, **kwargs})
        return SimpleNamespace(message_id=message_id, chat_id=chat_id)

    async def send_photo(self, chat_id, photo, **kwargs):
        message_id = next(self._ids)
        self.sent.append({"chat_id": chat_id, "text": kwargs.get("caption") or "", "photo": photo, "message_id": message_id, **kwargs})
        return SimpleNamespace(message_id=message_id)

    async def send_dice(self, chat_id, emoji=None, **kwargs):
        value = self.dice_values.pop(0) if self.dice_values else 4
        self.sent.append({"chat_id": chat_id, "text": "", "dice": emoji, "value": value})
        return SimpleNamespace(message_id=next(self._ids), dice=SimpleNamespace(value=value))

    async def edit_message_text(self, text=None, chat_id=None, message_id=None, **kwargs):
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": text, **kwargs})
        return True

    async def edit_message_media(self, chat_id=None, message_id=None, media=None, **kwargs):
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": getattr(media, "caption", None), **kwargs})
        return True

    async def edit_message_caption(self, chat_id=None, message_id=None, caption=None, **kwargs):
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": caption, **kwargs})
        return True

    async def send_document(self, chat_id, document, **kwargs):
        message_id = next(self._ids)
        self.sent.append({"chat_id": chat_id, "text": kwargs.get("caption") or "", "document": document, "message_id": message_id})
        return SimpleNamespace(message_id=message_id)

    async def copy_message(self, chat_id, from_chat_id, message_id, **kwargs):
        self.sent.append({"chat_id": chat_id, "text": "", "copy_of": (from_chat_id, message_id)})
        return SimpleNamespace(message_id=next(self._ids))

    async def edit_message_reply_markup(self, chat_id=None, message_id=None, **kwargs):
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": None, **kwargs})
        return True

    async def delete_message(self, chat_id, message_id, **kwargs):
        self.deleted.append((chat_id, message_id))
        return True

    async def get_chat_member(self, chat_id, user_id, **kwargs):
        status = "administrator" if (chat_id, user_id) in self.admins else "member"
        return SimpleNamespace(status=status)

    async def set_my_commands(self, *args, **kwargs):
        return True

    def texts_to(self, chat_id) -> list[str]:
        return [m["text"] for m in self.sent if m["chat_id"] == chat_id]

    def all_text(self, chat_id) -> str:
        edits = [e["text"] for e in self.edits if e["chat_id"] == chat_id and e["text"]]
        return "\n".join(self.texts_to(chat_id) + edits)


class FakeApplication:
    def __init__(self):
        self.bot = FakeBot()
        self.job_queue = FakeJobQueue()
        self.bot_data = {"username": "test_bot"}
        self.tasks = []

    def create_task(self, coro):
        import asyncio

        task = asyncio.ensure_future(coro)
        self.tasks.append(task)
        return task
