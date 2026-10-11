"""کارت تصویری نتیجه‌ی مسابقه: ساخت تصویر، پاک‌سازی نام‌ها و ارسال آن در پایان مسابقه."""

import io
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone
from PIL import Image

from bot import cards
from bot.runner import MatchManager
from core.models import TelegramGroup, TelegramUser
from core.redis import reset_clients
from games.catalog import get_info

from .fake_telegram import FakeApplication

JPEG = b"\xff\xd8\xff"
CHAT_ID = -100888


def size_of(data: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(data)).size


# ------------------------------------------------------------------ ساخت تصویر
def test_card_is_a_jpeg_with_the_expected_size():
    data = cards.render_result_card("برج‌ساز", [(1, "علی", 1240, 150), (2, "Sara", 980, 60), (3, "مهدی", 720, 0)], 210)
    assert data[:3] == JPEG
    assert size_of(data) == (cards.WIDTH, cards.HEIGHT)
    assert len(data) < 200_000


@pytest.mark.parametrize(
    "players",
    [
        [(1, "تنها", 5, 0)],
        [(1, "الف", 1, 0), (1, "ب", 1, 0)],  # مساوی دونفره
        [(1, "الف", 9, 50), (2, "ب", 7, 0)],
        [(1, "الف", 9, 0), (1, "ب", 9, 0), (1, "ج", 9, 0), (1, "د", 9, 0)],  # بیشتر از سه نفرِ هم‌رتبه
        [(1, "الف", 9, 0), (2, "ب", 5, 0), (2, "ج", 5, 0), (4, "د", 1, 0)],
        [(1, "🔥🔥", 3, 0), (2, "𝓐𝓵𝓲", 2, 0), (3, "x" * 80, 1, 0)],
        [(1, "الف", 10**9, 10**9)],
    ],
)
def test_card_handles_ties_missing_places_and_odd_names(players):
    data = cards.render_result_card("شطرنج", players, pot=0, seed=3)
    assert data[:3] == JPEG


def test_card_is_deterministic_for_a_match():
    players = [(1, "الف", 9, 50), (2, "ب", 7, 0)]
    assert cards.render_result_card("دوز", players, 50, seed=11) == cards.render_result_card("دوز", players, 50, seed=11)


def test_long_title_is_shrunk_to_fit():
    data = cards.render_result_card("یک عنوان خیلی خیلی طولانی برای آزمایش جا شدن در کارت نتیجه", [(1, "الف", 1, 0)], 0)
    assert data[:3] == JPEG


def test_clean_name_drops_emoji_and_undrawable_characters():
    assert cards.clean_name("علی 🔥") == "علی"
    assert cards.clean_name("🔥🔥") == "بازیکن"
    assert cards.clean_name("") == "بازیکن"
    assert cards.clean_name("  Sara   K  ") == "Sara K"
    assert cards.clean_name("علی‌رضا") == "علی‌رضا"  # نیم‌فاصله می‌ماند
    assert cards.clean_name("‮evil") == "evil"  # نویسه‌های کنترل جهت حذف می‌شوند
    assert cards.clean_name("𝓐𝓵𝓲 Ali") == "Ali"
    long = cards.clean_name("ب" * 60)
    assert len(long) == cards.NAME_CHARS and long.endswith("…")


def test_visible_length_ignores_tags_and_counts_utf16_units():
    assert cards.visible_length("<b>سلام</b>") == 4
    assert cards.visible_length('<a href="tg://user?id=1">x</a> 🥇') == 4  # ایموجی دو واحد است


def test_result_card_returns_none_instead_of_raising(monkeypatch):
    result = SimpleNamespace(
        match=SimpleNamespace(pot=0, pk=1),
        players=[SimpleNamespace(rank=1, user=SimpleNamespace(display_name="الف"), score=1, prize=0)],
    )
    info = SimpleNamespace(title_fa="دوز")
    assert cards.result_card(result, info)[:3] == JPEG

    def broken(*args, **kwargs):
        raise RuntimeError("no font")

    monkeypatch.setattr(cards, "render_result_card", broken)
    assert cards.result_card(result, info) is None
    assert cards.result_card(SimpleNamespace(match=result.match, players=[]), info) is None


# ------------------------------------------------------------------ ارسال در پایان مسابقه
@pytest.fixture
def _fresh_redis():
    reset_clients()
    yield
    reset_clients()


@sync_to_async
def setup_world(n_users=2):
    group = TelegramGroup.objects.create(chat_id=CHAT_ID, title="تست")
    users = [
        TelegramUser.objects.create(tg_id=7000 + i, first_name=f"بازیکن{i}", started_bot=True) for i in range(n_users)
    ]
    return group, users


async def play_to_the_end(app):
    group, users = await setup_world()
    manager = MatchManager(app)
    active = await manager.create_lobby(
        group, users[0], get_info("quick_math"), fee=0, split=[100], join_seconds=60, options={"rounds": 1}
    )
    for user in users:
        assert await manager.join(active, user)
    await app.job_queue.fire("lobby_close")
    await manager.on_message(active, active.players_by_tg[7000], str(active.game.answer), 1, timezone.now().timestamp())
    await app.job_queue.fire("game:gap")
    assert active.phase == "done"


@pytest.mark.django_db(transaction=True)
async def test_match_end_sends_the_card_with_the_result_as_caption(_fresh_redis):
    app = FakeApplication()
    await play_to_the_end(app)
    last = app.bot.sent[-1]
    assert last["photo"][:3] == JPEG
    assert "پایان حساب سریع" in last["text"] and "🥇" in last["text"]
    # نتیجه فقط یک بار اعلام می‌شود
    assert sum("پایان حساب سریع" in m["text"] for m in app.bot.sent) == 1


@pytest.mark.django_db(transaction=True)
async def test_match_end_falls_back_to_text_when_the_card_cannot_be_built(_fresh_redis, monkeypatch):
    monkeypatch.setattr(cards, "result_card", lambda result, info: None)
    app = FakeApplication()
    await play_to_the_end(app)
    last = app.bot.sent[-1]
    assert "photo" not in last and "پایان حساب سریع" in last["text"]


@pytest.mark.django_db(transaction=True)
async def test_match_end_falls_back_to_text_when_the_photo_is_rejected(_fresh_redis):
    app = FakeApplication()

    async def rejected(chat_id, photo, **kwargs):
        return None

    app.bot.send_photo = rejected
    await play_to_the_end(app)
    last = app.bot.sent[-1]
    assert "photo" not in last and "پایان حساب سریع" in last["text"]


@pytest.mark.django_db(transaction=True)
async def test_long_result_is_sent_as_card_then_full_text(_fresh_redis, monkeypatch):
    monkeypatch.setattr(cards, "CAPTION_LIMIT", 10)
    app = FakeApplication()
    await play_to_the_end(app)
    card, text = app.bot.sent[-2], app.bot.sent[-1]
    assert card["photo"][:3] == JPEG and card["text"] == ""
    assert "photo" not in text and "پایان حساب سریع" in text["text"]
