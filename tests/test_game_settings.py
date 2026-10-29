"""تنظیمات بازی‌ها در پنل ادمین: تعداد شرکت‌کننده و فعال/غیرفعال کردن هر بازی."""

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from arcade import services as arcade_services
from arcade.services import ArcadeError
from bot import render
from bot.runner import MatchManager
from core.models import TelegramGroup, TelegramUser
from core.redis import reset_clients
from games import config
from games.catalog import arcade_enabled, catalog, defaults, get_info
from games.engine import services
from games.engine.services import MatchError
from games.models import GameSetting, Match

from .fake_telegram import FakeApplication

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client(client):
    get_user_model().objects.create_superuser("admin", "a@example.com", "pass12345")
    client.login(username="admin", password="pass12345")
    return client


def setting(key: str, **values) -> GameSetting:
    config.sync_rows()
    row = GameSetting.objects.get(game_key=key)
    for name, value in values.items():
        setattr(row, name, value)
    row.save()
    return row


def adjust(client, row, **data):
    return client.post(reverse("admin:games_gamesetting_adjust", args=[row.pk]), data)


# ====================================================================== کاتالوگ
def test_defaults_come_from_game_classes_without_any_row():
    games = catalog()
    assert (games["quick_math"].min_players, games["quick_math"].max_players) == (2, 20)
    assert (games["chess"].min_players, games["chess"].max_players) == (2, 2)
    assert games["chess"].fixed_players and not games["quick_math"].fixed_players
    assert (games["arcade_pins"].min_players, games["arcade_pins"].max_players) == (2, 30)
    assert all(info.floor <= info.default_min <= info.default_max <= info.ceiling for info in games.values())


def test_admin_values_override_catalog():
    setting("quick_math", min_players=3, max_players=7)
    info = catalog()["quick_math"]
    assert (info.min_players, info.max_players) == (3, 7)
    assert (info.default_min, info.default_max) == (2, 20)


def test_out_of_range_rows_are_clamped_to_the_game_bounds():
    # حتی اگر ردیفی مستقیم در دیتابیس عوض شود، شطرنج دونفره می‌ماند
    config.sync_rows()
    GameSetting.objects.filter(game_key="chess").update(min_players=2, max_players=9)
    GameSetting.objects.filter(game_key="dice_games").update(min_players=2, max_players=500)
    config.invalidate()
    games = catalog()
    assert (games["chess"].min_players, games["chess"].max_players) == (2, 2)
    assert games["dice_games"].max_players == games["dice_games"].ceiling == 12


def test_disabled_game_leaves_menus_but_is_still_known():
    setting("quiz", is_enabled=False)
    assert "quiz" not in catalog()
    assert "quiz" in catalog(include_disabled=True)
    assert get_info("quiz").enabled is False


def test_model_validation_rejects_bad_ranges():
    row = setting("quick_math")
    row.min_players, row.max_players = 8, 4
    with pytest.raises(ValidationError):
        row.full_clean()
    row.min_players, row.max_players = 2, 51
    with pytest.raises(ValidationError):
        row.full_clean()
    row.min_players, row.max_players = 4, 12
    row.full_clean()
    chess = setting("chess")
    chess.max_players = 4
    with pytest.raises(ValidationError):
        chess.full_clean()


# ====================================================================== پنل ادمین
def test_changelist_creates_a_row_per_game_and_shows_steppers(staff_client):
    response = staff_client.get(reverse("admin:games_gamesetting_changelist"))
    assert response.status_code == 200
    assert set(GameSetting.objects.values_list("game_key", flat=True)) == set(defaults())
    html = response.content.decode()
    assert "gs-stepper" in html and "gs-switch" in html and "حساب سریع" in html
    assert "🔒" in html  # شطرنج و دوز قفل‌اند
    row = GameSetting.objects.get(game_key="quick_math")
    assert staff_client.get(reverse("admin:games_gamesetting_change", args=[row.pk])).status_code == 200


def test_plus_and_minus_buttons_save_immediately(staff_client):
    row = setting("quick_math")
    data = adjust(staff_client, row, field="max", delta="1").json()
    assert data == {"ok": True, "enabled": True, "min": 2, "max": 21, "floor": 2, "ceiling": 50}
    assert adjust(staff_client, row, field="max", delta="-5").json()["max"] == 16
    assert adjust(staff_client, row, field="min", delta="1").json()["min"] == 3
    row.refresh_from_db()
    assert (row.min_players, row.max_players) == (3, 16)
    assert catalog()["quick_math"].max_players == 16


def test_buttons_never_leave_the_allowed_range(staff_client):
    row = setting("quick_math", min_players=2, max_players=3)
    assert adjust(staff_client, row, field="min", delta="-1").json()["min"] == 2  # کف
    assert adjust(staff_client, row, field="min", delta="5").json()["min"] == 3  # از حداکثر رد نمی‌شود
    assert adjust(staff_client, row, field="max", delta="-5").json()["max"] == 3  # از حداقل پایین‌تر نمی‌رود
    row = setting("dice_games", max_players=12)
    assert adjust(staff_client, row, field="max", delta="1").json()["max"] == 12  # سقف
    chess = setting("chess")
    assert adjust(staff_client, chess, field="max", delta="1").json()["max"] == 2
    assert adjust(staff_client, chess, field="oops").status_code == 400
    assert adjust(staff_client, chess, field="max", delta="x").status_code == 400


def test_switch_toggles_the_game(staff_client):
    row = setting("anagram")
    assert adjust(staff_client, row, field="enabled").json()["enabled"] is False
    assert "anagram" not in catalog()
    assert adjust(staff_client, row, field="enabled").json()["enabled"] is True
    assert "anagram" in catalog()


def test_adjust_needs_a_logged_in_staff_user_and_post(client, staff_client):
    row = setting("quick_math")
    assert staff_client.get(reverse("admin:games_gamesetting_adjust", args=[row.pk])).status_code == 405
    client.logout()
    response = adjust(client, row, field="max", delta="1")
    assert response.status_code == 302
    row.refresh_from_db()
    assert row.max_players == 20


def test_bulk_actions(staff_client):
    config.sync_rows()
    url = reverse("admin:games_gamesetting_changelist")
    ids = list(GameSetting.objects.filter(game_key__in=["quick_math", "chess"]).values_list("pk", flat=True))
    staff_client.post(url, {"action": "max_plus_5", "_selected_action": ids})
    assert GameSetting.objects.get(game_key="quick_math").max_players == 25
    assert GameSetting.objects.get(game_key="chess").max_players == 2
    staff_client.post(url, {"action": "max_minus_1", "_selected_action": ids})
    assert GameSetting.objects.get(game_key="quick_math").max_players == 24
    staff_client.post(url, {"action": "disable", "_selected_action": ids})
    assert not {"quick_math", "chess"} & set(catalog())
    staff_client.post(url, {"action": "enable", "_selected_action": ids})
    staff_client.post(url, {"action": "reset_defaults", "_selected_action": ids})
    assert GameSetting.objects.get(game_key="quick_math").max_players == 20
    assert {"quick_math", "chess"} <= set(catalog())


def test_rows_cannot_be_added_or_deleted(staff_client):
    row = setting("quick_math")
    assert staff_client.get(reverse("admin:games_gamesetting_add")).status_code == 403
    assert staff_client.post(reverse("admin:games_gamesetting_delete", args=[row.pk]), {"post": "yes"}).status_code == 403
    assert GameSetting.objects.filter(pk=row.pk).exists()


# ====================================================================== اثر روی مسابقه
def test_lobby_capacity_follows_the_setting(group, make_user):
    setting("quick_math", min_players=3, max_players=3)
    info = get_info("quick_math")
    users = [make_user(500) for _ in range(4)]
    match = services.create_match(
        group,
        users[0],
        "quick_math",
        entry_fee=0,
        prize_split=[100],
        join_seconds=60,
        min_players=info.min_players,
        max_players=info.max_players,
    )
    services.join_match(match.pk, users[0])
    services.join_match(match.pk, users[1])
    with pytest.raises(MatchError) as too_few:
        services.start_match(match.pk)
    assert too_few.value.code == "not_enough_players"
    services.join_match(match.pk, users[2])
    with pytest.raises(MatchError) as full:
        services.join_match(match.pk, users[3])
    assert full.value.code == "lobby_full"
    assert services.start_match(match.pk).status == "RUNNING"


def test_long_lobbies_and_boards_stay_inside_one_message(group, make_user):
    creator = make_user()
    match = services.create_match(
        group, creator, "arcade_pins", entry_fee=0, prize_split=[100], join_seconds=60, min_players=2, max_players=50
    )
    names = ["ن" * 128 for _ in range(50)]
    text = render.lobby_text(match, get_info("arcade_pins"), names, 30)
    assert len(text) < 4096 and "۲۰ نفر دیگر" in text
    standings = [arcade_services.Standing(i, "ن" * 128, 10, None, 1) for i in range(50)]
    board = render.arcade_text(match, get_info("arcade_pins"), standings, 60, 3)
    assert len(board) < 4096 and "۳۰ نفر دیگر" in board


def test_disabled_arcade_game_cannot_be_practised(make_user):
    user = make_user()
    session, _ = arcade_services.start_session(user, "pins", None)
    assert session.game_key == "pins"
    setting("arcade_pins", is_enabled=False)
    assert not arcade_enabled("pins") and arcade_enabled("stack")
    with pytest.raises(ArcadeError) as blocked:
        arcade_services.start_session(user, "pins", None)
    assert blocked.value.code == "unknown_game"


# ====================================================================== ربات (async)
@pytest.fixture
def _fresh_redis():
    reset_clients()
    yield
    reset_clients()


@sync_to_async
def bot_world():
    group = TelegramGroup.objects.create(chat_id=-100555, title="تست")
    users = [TelegramUser.objects.create(tg_id=7000 + i, first_name=f"بازیکن{i}", started_bot=True) for i in range(3)]
    return group, users


async def open_lobby(manager, group, creator, info):
    return await manager.create_lobby(group, creator, info, fee=0, split=[100], join_seconds=60, options={"rounds": 1})


@pytest.mark.django_db(transaction=True)
async def test_bot_reads_fresh_limits_when_a_match_is_created(_fresh_redis):
    group, users = await bot_world()
    stale = get_info("quick_math")  # منوی کاربر قبل از تغییر ادمین ساخته شده
    assert stale.max_players == 20
    await sync_to_async(setting)("quick_math", min_players=2, max_players=2)

    app = FakeApplication()
    manager = MatchManager(app)
    active = await open_lobby(manager, group, users[0], stale)
    match = await sync_to_async(Match.objects.get)(pk=active.match_id)
    assert (match.min_players, match.max_players) == (2, 2)
    assert active.info.max_players == 2

    await manager.join(active, users[0])
    await manager.join(active, users[1])
    with pytest.raises(MatchError) as full:
        await manager.join(active, users[2])
    assert full.value.code == "lobby_full"
    # ظرفیت پر شد: بدون انتظار برای پایان زمان عضوگیری شروع می‌شود
    await app.job_queue.fire("lobby_close")
    assert active.phase == "running"


@pytest.mark.django_db(transaction=True)
async def test_bot_refuses_to_create_a_disabled_game(_fresh_redis):
    group, users = await bot_world()
    info = get_info("quick_math")
    await sync_to_async(setting)("quick_math", is_enabled=False)
    manager = MatchManager(FakeApplication())
    with pytest.raises(MatchError) as blocked:
        await open_lobby(manager, group, users[0], info)
    assert blocked.value.code == "game_disabled"
    assert not manager.in_chat(group.chat_id)
