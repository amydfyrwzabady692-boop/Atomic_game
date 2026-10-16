import contextvars
import threading

from bot import db as bot_db

request_id = contextvars.ContextVar("request_id", default="")


async def test_db_runs_in_thread_pool_and_keeps_context(monkeypatch):
    monkeypatch.setattr(bot_db, "_pool_size", lambda: 3)
    monkeypatch.setattr(bot_db, "_executor", None)
    monkeypatch.setattr(bot_db, "close_old_connections", lambda: None)
    request_id.set("abc")

    @bot_db.db
    def where(x, y=0):
        return threading.current_thread().name, request_id.get(), x + y

    name, ctx, total = await where(2, y=3)
    assert name.startswith("bot-db") and ctx == "abc" and total == 5
    bot_db._executor.shutdown(wait=True)


async def test_db_falls_back_to_sync_to_async_without_pool(monkeypatch):
    monkeypatch.setattr(bot_db, "_pool_size", lambda: 0)
    monkeypatch.setattr(bot_db, "close_old_connections", lambda: None)

    @bot_db.db
    def where():
        return threading.current_thread().name

    assert not (await where()).startswith("bot-db")
