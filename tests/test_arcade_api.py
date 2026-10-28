"""API مینی‌اپ: اعتبارسنجی initData، صدور و مصرف session، ضدتقلب و جدول مسابقه."""

import json
import random
import time
from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from arcade import services as arcade_services
from arcade.auth import InitDataError, sign_init_data, validate_init_data
from arcade.models import ArcadeRecord, ArcadeSession
from arcade.sim import get_simulator
from arcade.sim.autoplay import autoplay
from core.redis import reset_clients
from games.engine import services
from games.models import Match

pytestmark = pytest.mark.django_db

TOKEN = settings.BOT_TOKEN


@pytest.fixture(autouse=True)
def _fresh_redis():
    reset_clients()
    yield
    reset_clients()


def init_data_for(user, token=TOKEN, age=0, **extra):
    fields = {
        "auth_date": int(time.time()) - age,
        "query_id": "AAE",
        "user": {"id": user.tg_id, "first_name": user.first_name},
        **extra,
    }
    return sign_init_data(fields, token)


def post(client, path, user, **body):
    body["initData"] = init_data_for(user)
    return client.post(f"/arcade/api/{path}", data=json.dumps(body), content_type="application/json")


def play(seed, skill=100, max_ms=20_000, key="pins"):
    sim = get_simulator(key)
    return autoplay(sim, seed, sim.demo_policy(random.Random(5), skill), max_ms)


def backdate(session_id, ms):
    """انگار session این‌قدر میلی‌ثانیه قبل شروع شده (به‌جای صبر کردن واقعی در تست)."""
    ArcadeSession.objects.filter(pk=session_id).update(started_at=timezone.now() - timedelta(milliseconds=ms))


# ====================================================================== initData
def test_site_root_redirects_to_the_arcade_menu(client):
    response = client.get("/")
    assert response.status_code == 302 and response["Location"] == "/arcade/"
    assert client.get("/arcade/").status_code == 200


def test_app_page_gives_every_game_its_rules(client):
    games = client.get("/arcade/").context["games"]
    assert len(games) == 14
    for game in games:
        assert len(game["rules"]) == 3 and all(isinstance(line, str) and line for line in game["rules"])
        assert game["howto"]
    page = client.get("/arcade/play/flappy/").content.decode()
    assert 'id="start-rules"' in page and "شروع بازی" in page


def test_valid_init_data_accepted(make_user):
    user = make_user()
    data = validate_init_data(init_data_for(user, start_param="abc"))
    assert data["user_id"] == user.tg_id and data["start_param"] == "abc"


def test_tampered_init_data_rejected(make_user):
    user = make_user()
    good = init_data_for(user)
    with pytest.raises(InitDataError, match="bad_signature"):
        validate_init_data(good.replace(str(user.tg_id), str(user.tg_id + 1)))
    with pytest.raises(InitDataError, match="bad_signature"):
        validate_init_data(init_data_for(user, token="999:OTHER-BOT"))
    with pytest.raises(InitDataError):
        validate_init_data("")
    with pytest.raises(InitDataError, match="no_hash"):
        validate_init_data("auth_date=1&user=%7B%7D")


def test_expired_init_data_rejected(make_user):
    user = make_user()
    old = init_data_for(user, age=settings.ARCADE_INITDATA_MAX_AGE + 60)
    with pytest.raises(InitDataError, match="expired"):
        validate_init_data(old)


def test_api_requires_valid_signature(client, make_user):
    user = make_user()
    response = client.post(
        "/arcade/api/session/start",
        data=json.dumps({"initData": "user=%7B%22id%22%3A1%7D&hash=deadbeef&auth_date=1", "game": "pins"}),
        content_type="application/json",
    )
    assert response.status_code == 401
    assert ArcadeSession.objects.count() == 0
    assert post(client, "session/start", user, game="pins").status_code == 200


def test_dev_auth_is_disabled_outside_debug(client):
    response = client.post(
        "/arcade/api/info", data=json.dumps({"initData": "dev:1", "game": "pins"}), content_type="application/json"
    )
    assert response.status_code == 401


def test_banned_user_blocked(client, make_user):
    user = make_user(is_banned=True)
    assert post(client, "info", user, game="pins").status_code == 403


# ====================================================================== تمرین آزاد
def test_practice_flow_verifies_score_on_server(client, make_user):
    user = make_user()
    info = post(client, "info", user, game="pins").json()
    assert info["mode"] == "practice" and info["game"]["title"] == "سیخ‌زن"

    started = post(client, "session/start", user, game="pins").json()
    assert started["ok"] and started["seed"] > 0
    inputs, duration = play(started["seed"])
    expected = get_simulator("pins").simulate(started["seed"], inputs, duration).score
    assert expected > 0
    backdate(started["session_id"], duration + 500)

    # کلاینت امتیاز دروغ می‌فرستد؛ سرور خودش حساب می‌کند
    result = post(
        client,
        "session/submit",
        user,
        session_id=started["session_id"],
        input_log=inputs,
        duration_ms=duration,
        claimed_score=999_999,
    ).json()
    assert result["ok"] and result["verified_score"] == expected
    session = ArcadeSession.objects.get(pk=started["session_id"])
    assert session.status == "VERIFIED" and session.flagged and session.reject_reason == "claim_mismatch"
    assert ArcadeRecord.objects.get(user=user, game_key="pins").best_score == expected
    assert post(client, "info", user, game="pins").json()["record"] == expected


def test_session_can_only_be_submitted_once(client, make_user):
    user = make_user()
    started = post(client, "session/start", user, game="pins").json()
    inputs, duration = play(started["seed"], max_ms=5000)
    backdate(started["session_id"], duration + 500)
    body = {"session_id": started["session_id"], "input_log": inputs, "duration_ms": duration}
    assert post(client, "session/submit", user, **body).status_code == 200
    again = post(client, "session/submit", user, **body)
    assert again.status_code == 409 and again.json()["error"] == "session_already_used"


def test_score_without_valid_session_is_rejected(client, make_user):
    user, other = make_user(), make_user()
    fake = post(client, "session/submit", user, session_id="not-a-uuid", input_log=[], duration_ms=0)
    assert fake.status_code == 404
    started = post(client, "session/start", other, game="pins").json()
    stolen = post(client, "session/submit", user, session_id=started["session_id"], input_log=[], duration_ms=0)
    assert stolen.status_code == 404
    assert ArcadeSession.objects.get(pk=started["session_id"]).status == "OPEN"


def test_game_longer_than_real_elapsed_time_is_rejected(client, make_user):
    """لاگی که از قبل (آفلاین) ساخته شده و بلافاصله فرستاده می‌شود قبول نیست."""
    user = make_user()
    started = post(client, "session/start", user, game="pins").json()
    inputs, duration = play(started["seed"], max_ms=60_000)
    assert duration > settings.ARCADE_SESSION_GRACE_MS + 10_000
    result = post(
        client, "session/submit", user, session_id=started["session_id"], input_log=inputs, duration_ms=duration
    ).json()
    assert not result["ok"] and result["status"] == "REJECTED"
    session = ArcadeSession.objects.get(pk=started["session_id"])
    assert session.reject_reason == "faster_than_real_time" and session.flagged
    assert session.verified_score is None
    assert not ArcadeRecord.objects.filter(user=user).exists()


def test_inhumanly_fast_taps_are_rejected(client, make_user):
    user = make_user()
    started = post(client, "session/start", user, game="pins").json()
    inputs = [[1000 + i * 16] for i in range(40)]
    backdate(started["session_id"], 5000)
    result = post(
        client, "session/submit", user, session_id=started["session_id"], input_log=inputs, duration_ms=3000
    ).json()
    assert result["status"] == "REJECTED"
    assert ArcadeSession.objects.get(pk=started["session_id"]).reject_reason == "inhuman_input"


@pytest.mark.parametrize(
    "log",
    [
        "not-a-list",
        [[10], [5]],  # زمان‌ها باید صعودی باشند
        [[10, 1]],  # تعداد عناصر اشتباه
        [["10"]],
        [[True]],
        [[999_999]],  # بعد از duration
        [[-5]],
    ],
)
def test_malformed_input_log_rejected(client, make_user, log):
    user = make_user()
    started = post(client, "session/start", user, game="pins").json()
    backdate(started["session_id"], 5000)
    result = post(
        client, "session/submit", user, session_id=started["session_id"], input_log=log, duration_ms=2000
    ).json()
    assert result["status"] == "REJECTED"


def test_slow_motion_play_is_flagged_but_counted(client, make_user):
    user = make_user()
    started = post(client, "session/start", user, game="pins").json()
    inputs, duration = play(started["seed"], max_ms=4000)
    backdate(started["session_id"], duration * 3 + 120_000)
    result = post(
        client, "session/submit", user, session_id=started["session_id"], input_log=inputs, duration_ms=duration
    ).json()
    assert result["ok"]
    session = ArcadeSession.objects.get(pk=started["session_id"])
    assert session.flagged and session.reject_reason == "slower_than_real_time"


def test_start_is_rate_limited(client, make_user):
    user = make_user()
    codes = [post(client, "session/start", user, game="pins").status_code for _ in range(16)]
    assert codes[0] == 200 and 429 in codes


def test_unknown_game(client, make_user):
    user = make_user()
    assert post(client, "session/start", user, game="nope").status_code == 404
    assert client.get("/arcade/play/nope/").status_code == 404
    assert client.get("/arcade/play/pins/").status_code == 200
    assert client.get("/arcade/").status_code == 200


# ====================================================================== مسابقه
def arcade_match(group, users, attempts=3, minutes=5):
    match = services.create_match(
        group,
        users[0],
        "arcade_pins",
        entry_fee=100,
        prize_split=[60, 30, 10],
        join_seconds=60,
        min_players=2,
        max_players=10,
        options={"attempts": attempts, "window_minutes": minutes},
    )
    for user in users:
        services.join_match(match.pk, user)
    return services.start_match(match.pk, minutes * 60)


def submit_run(client, user, match, skill=100, max_ms=8000):
    started = post(client, "session/start", user, match_token=match.token).json()
    assert started["ok"], started
    inputs, duration = play(started["seed"], skill=skill, max_ms=max_ms)
    backdate(started["session_id"], duration + 500)
    return post(
        client, "session/submit", user, session_id=started["session_id"], input_log=inputs, duration_ms=duration
    ).json()


def test_match_sessions_share_seed_and_respect_attempt_limit(client, group, make_user):
    a, b = make_user(500), make_user(500)
    match = arcade_match(group, [a, b], attempts=2)
    info = post(client, "info", a, match_token=match.token).json()
    assert info["mode"] == "match" and info["attempts_left"] == 2 and info["seconds_left"] > 200

    first = post(client, "session/start", a, match_token=match.token).json()
    other = post(client, "session/start", b, match_token=match.token).json()
    assert first["seed"] == other["seed"] == match.seed  # چیدمان یکسان برای همه
    second = post(client, "session/start", a, match_token=match.token).json()
    assert second["ok"]
    third = post(client, "session/start", a, match_token=match.token)
    assert third.status_code == 409 and third.json()["error"] == "no_attempts_left"
    assert post(client, "info", a, match_token=match.token).json()["attempts_left"] == 0


def test_only_match_players_can_start(client, group, make_user):
    a, b, outsider = make_user(500), make_user(500), make_user(500)
    match = arcade_match(group, [a, b])
    response = post(client, "session/start", outsider, match_token=match.token)
    assert response.status_code == 403 and response.json()["error"] == "not_a_player"
    assert post(client, "info", outsider, match_token=match.token).json()["is_player"] is False
    assert post(client, "session/start", a, match_token="missing").status_code == 404


def test_cannot_start_before_or_after_play_window(client, group, make_user):
    a, b = make_user(500), make_user(500)
    lobby = services.create_match(
        group, a, "arcade_pins", entry_fee=0, prize_split=[100], join_seconds=60, min_players=2, max_players=5
    )
    services.join_match(lobby.pk, a)
    services.join_match(lobby.pk, b)
    assert post(client, "session/start", a, match_token=lobby.token).json()["error"] == "match_not_running"
    services.start_match(lobby.pk, 300)
    Match.objects.filter(pk=lobby.pk).update(play_deadline=timezone.now() - timedelta(seconds=1))
    assert post(client, "session/start", a, match_token=lobby.token).json()["error"] == "match_over"


def test_best_verified_score_counts_and_leaderboard(client, group, make_user):
    a, b, c = make_user(500), make_user(500), make_user(500)
    match = arcade_match(group, [a, b, c])
    low = submit_run(client, a, match, max_ms=3000)
    high = submit_run(client, a, match, max_ms=9000)
    assert high["verified_score"] > low["verified_score"] > 0
    assert high["best"] == high["verified_score"] and high["attempts_left"] == 1 and high["rank"] == 1
    other = submit_run(client, b, match, max_ms=5000)
    assert other["rank"] == 2 and other["players"] == 3

    board = client.get(f"/arcade/api/match/{match.token}/leaderboard").json()
    assert [row["score"] for row in board["rows"]] == [high["verified_score"], other["verified_score"], 0]
    assert board["rows"][2]["attempts"] == 0 and board["status"] == "RUNNING"

    standings = arcade_services.match_standings(match)
    assert [s.user_id for s in standings] == [a.pk, b.pk, c.pk]
    assert standings[0].reached_at is not None and standings[2].reached_at is None


def test_rejected_runs_do_not_count_in_match(client, group, make_user):
    a, b = make_user(500), make_user(500)
    match = arcade_match(group, [a, b])
    started = post(client, "session/start", a, match_token=match.token).json()
    inputs, duration = play(started["seed"], max_ms=60_000)
    result = post(
        client, "session/submit", a, session_id=started["session_id"], input_log=inputs, duration_ms=duration
    ).json()
    assert result["status"] == "REJECTED"
    assert arcade_services.match_standings(match)[0].score == 0
    # تلاش ردشده هم از سهمیه‌ی تلاش‌ها کم می‌کند
    assert result["attempts_left"] == 2


def test_all_attempts_done_detection(client, group, make_user):
    a, b = make_user(500), make_user(500)
    match = arcade_match(group, [a, b], attempts=1)
    assert not arcade_services.all_attempts_done(match)
    submit_run(client, a, match, max_ms=2000)
    assert not arcade_services.all_attempts_done(match)
    submit_run(client, b, match, max_ms=2000)
    assert arcade_services.all_attempts_done(match)


def test_font_is_served_from_our_server(client, monkeypatch, tmp_path):
    from arcade import views

    page = client.get("/arcade/").content.decode()
    assert "jsdelivr" not in page and "/arcade/font/regular.ttf" in page
    font = tmp_path / "Vazirmatn-Regular.ttf"
    font.write_bytes(b"\x00\x01\x00\x00fake-font")
    monkeypatch.setattr(views, "_font_cache", {"regular": str(font), "bold": None})
    response = client.get("/arcade/font/regular.ttf")
    assert response.status_code == 200 and b"".join(response.streaming_content).startswith(b"\x00\x01")
    assert "immutable" in response["Cache-Control"]
    assert client.get("/arcade/font/bold.ttf").status_code == 404
    assert client.get("/arcade/font/other.ttf").status_code == 404


def test_group_match_link_preloads_the_game_files(client, group, make_user):
    """لینک مسابقه‌ی گروه: فایل‌های بازی همان اول (موازی با /info) دانلود می‌شوند."""
    match = arcade_match(group, [make_user(500), make_user(500)])
    page = client.get(f"/arcade/?tgWebAppStartParam={match.token}").content.decode()
    assert 'rel="preload"' in page and "/pins/core.js?v=" in page and "/pins/render.js?v=" in page
    assert 'preloadKey: "pins"' in page
    # توکن ناشناخته (یا پاک‌شده) به‌جای صفحه‌ی خطا صفحه‌ی اصلی مینی‌اپ را باز می‌کند
    unknown = client.get("/arcade/?tgWebAppStartParam=nope").content.decode()
    assert "core.js?v=" not in unknown and "hub.js" in unknown
    # همان لینک از آدرس اصلی دامنه (اگر در BotFather دامنه‌ی خالی ثبت شده باشد) هم به مسابقه می‌رسد
    root = client.get(f"/?tgWebAppStartParam={match.token}")
    assert root.status_code == 302 and root["Location"].endswith(f"/arcade/?tgWebAppStartParam={match.token}")
    assert "/pins/core.js?v=" in client.get(f"/arcade/?startapp={match.token}").content.decode()
