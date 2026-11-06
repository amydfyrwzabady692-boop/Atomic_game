"""انفجار (Crash) و حکم دونفره: قوانین موتور، پنهان ماندن نقطه‌ی انفجار، میز مینی‌اپ، ربات و سهم سرویس (سرویس هیچ‌وقت
بیشتر از pot پرداخت نمی‌کند)؛ و کنار رفتن موقت بازی‌های آرکید."""

import random
import time

import pytest

from games.chess.live import LiveError
from games.crash import live as crash
from games.hokm import live as hokm


# ====================================================================== انفجار: موتور
def table(n=3, rounds=3, seed="c"):
    return crash.new_state([300 + i for i in range(n)], 1000.0, seed=seed, rounds=rounds)


def test_crash_points_are_deterministic_bounded_and_spread():
    points = [crash.crash_point("seed", r) for r in range(1, 2001)]
    assert points == [crash.crash_point("seed", r) for r in range(1, 2001)]
    assert all(1.0 <= p <= crash.MAX_MULT for p in points)
    assert 0.01 < sum(p == 1.0 for p in points) / len(points) < 0.08  # چند درصد همان اول
    assert 0.35 < sum(p >= 2 for p in points) / len(points) < 0.6
    assert crash.multiplier(0) == 1.0 and crash.multiplier(6) == pytest.approx(2.0, abs=0.01)


def test_round_flow_cash_out_and_crash():
    s = table(seed="flow")
    s["point"] = 3.0  # برای آزمایش
    assert s["phase"] == "wait"
    with pytest.raises(LiveError) as err:
        crash.cash_out(s, 300, 1001.0)
    assert err.value.code == "not_flying"
    start = s["start_at"]
    mult = crash.cash_out(s, 300, start + 6.0)  # دو برابر بعد از ۶ ثانیه
    assert s["phase"] == "fly" and mult == pytest.approx(2.0, abs=0.01) and s["scores"][0] == round(mult * 100)
    with pytest.raises(LiveError) as err:
        crash.cash_out(s, 300, start + 7.0)
    assert err.value.code == "already_cashed"
    # بعد از نقطه‌ی انفجار دیر است؛ کسی که برنداشته صفر می‌گیرد
    late = start + crash.fly_seconds(3.0) + 0.01
    with pytest.raises(LiveError) as err:
        crash.cash_out(s, 301, late)
    assert err.value.code == "crashed"
    assert s["phase"] == "pause" and s["results"][-1]["point"] == 3.0 and s["results"][-1]["cashed"] == [mult, None, None]
    assert s["scores"][1] == 0
    crash.advance(s, late + crash.PAUSE_SECONDS + 0.1)
    assert s["round"] == 2 and s["phase"] == "wait" and s["cashed"] == [None, None, None]


def test_round_ends_early_when_everyone_cashed_and_game_finishes_after_last_round():
    s = table(n=2, rounds=1, seed="early")
    s["point"] = 20.0
    start = s["start_at"]
    crash.cash_out(s, 300, start + 3)
    crash.cash_out(s, 301, start + 9)
    assert s["over"] and s["over"]["reason"] == "rounds" and s["over"]["winner"] == 301
    assert dict(crash.standings(s)) == {300: s["scores"][0], 301: s["scores"][1]} and s["scores"][1] > s["scores"][0]


def test_view_never_reveals_the_crash_point_before_it_happens():
    s = table(seed="secret")
    point = s["point"]
    v = crash.view(s, 300, 1000.5)
    assert v["point"] is None and v["start_in_ms"] > 0 and "deadline" not in v and v["left_ms"] > 0
    crash.advance(s, s["start_at"] + 0.2)
    v = crash.view(s, 300, s["start_at"] + 0.2)
    assert v["phase"] == "fly" and v["point"] is None and v["left_ms"] == 0 and v["seconds_left"] == 0
    assert v["history"] == [] and str(point) not in str(v.get("results"))
    crash.advance(s, s["start_at"] + crash.fly_seconds(point) + 0.01)
    assert crash.view(s, 300)["point"] == point


def test_leaving_scores_zero_and_last_player_standing_ends_the_game():
    s = table(n=3, seed="left")
    s["scores"] = [500, 100, 0]
    crash.resign(s, 300)
    assert not s["over"] and dict(crash.standings(s))[300] == 0
    crash.resign(s, 301)
    assert s["over"]["reason"] == "left"


@pytest.mark.parametrize("seed", range(10))
def test_random_crash_games_finish(seed):
    rng = random.Random(seed)
    n = rng.randint(2, 6)
    s = crash.new_state(list(range(1, n + 1)), 0.0, seed=f"r{seed}", rounds=rng.choice(crash.ROUNDS))
    now = 0.0
    for _ in range(5000):
        if s["over"]:
            break
        now += rng.uniform(0.05, 0.8)
        crash.advance(s, now)
        if s["phase"] == "fly" and rng.random() < 0.3:
            uid = rng.randint(1, n)
            try:
                crash.cash_out(s, uid, now)
            except LiveError:
                pass
    assert s["over"] and len(s["results"]) == s["rounds"]
    for r in s["results"]:
        assert all(c is None or 1.0 <= c < r["point"] for c in r["cashed"])


# ====================================================================== حکم دونفره
def duo(seed="d", target=7):
    return hokm.new_state([71, 72], 0.0, seed=seed, target=target)


def test_two_player_hokm_draws_to_thirteen_cards_each():
    s = duo()
    assert s["game"] == "hokm2" and hokm.need(s) == 7 and s["points"] == [0, 0]
    assert all(len(h) == 5 for h in s["hands"])
    hakem = s["hakem"]
    hokm.choose_trump(s, s["seats"][hakem], "d", 1)
    assert s["phase"] == "draw" and s["turn"] == hakem and len(s["pending"]) == 42
    other = s["seats"][1 - hakem]
    with pytest.raises(LiveError):
        hokm.draw(s, other, True, 2)
    top, under = s["pending"][-1], s["pending"][-2]
    view = hokm.view(s, s["seats"][hakem], 2)
    assert view["draw_card"] == top and hokm.view(s, other, 2)["draw_card"] is None and view["deck"] == 42
    hokm.draw(s, s["seats"][hakem], False, 2)  # می‌سوزاند و زیری را می‌گیرد
    assert under in s["hands"][hakem] and top not in s["hands"][hakem] and s["turn"] == 1 - hakem
    with pytest.raises(LiveError):
        hokm.draw(s, other, "yes", 3)
    for i in range(15):
        seat = s["turn"]
        hokm.draw(s, s["seats"][seat], i % 2 == 0, 3 + i)
    assert s["phase"] == "play" and all(len(h) == 13 for h in s["hands"]) and s["turn"] == hakem
    cards = [c for h in s["hands"] for c in h]
    assert len(set(cards)) == 26


def test_two_player_timeouts_draw_and_play_automatically():
    s = duo(seed="t")
    hokm.check_timeout(s, 10**6)  # حکم خودکار
    assert s["phase"] == "draw"
    for _ in range(16):
        hokm.check_timeout(s, s["deadline"] + 1)
    assert s["phase"] == "play" and all(len(h) == 13 for h in s["hands"]) and all(s["away"])


@pytest.mark.parametrize("seed", range(10))
def test_random_two_player_games_finish(seed):
    rng = random.Random(seed)
    s = hokm.new_state([1, 2], 0, seed=f"duo{seed}", target=rng.choice(hokm.TARGETS))
    now = 0.0
    for _ in range(20000):
        if s["over"]:
            break
        now += 1
        if s["phase"] == "pause":
            now = s["deadline"] + 1
            hokm.check_timeout(s, now)
            continue
        uid = s["seats"][s["turn"]]
        if s["phase"] == "trump":
            hokm.choose_trump(s, uid, rng.choice("shdc"), now)
        elif s["phase"] == "draw":
            hokm.draw(s, uid, rng.random() < 0.5, now)
        else:
            hokm.play(s, uid, rng.choice(hokm.legal_cards(s, s["turn"])), now)
    assert s["over"] and max(s["points"]) >= s["target"]
    scores = dict(hokm.standings(s))
    win = s["seats"][s["over"]["winner_team"]]
    assert scores[win] > min(scores.values())


def test_two_player_leaver_loses():
    s = duo(seed="l")
    hokm.resign(s, 71)
    assert s["over"]["winner_team"] == 1


# ====================================================================== مینی‌اپ و ربات
@pytest.fixture
def fresh_redis():
    from core.redis import reset_clients

    reset_clients()
    yield
    reset_clients()


def _running(group, users, game, options, fee=0, pot=0):
    from django.utils import timezone

    from arcade import board
    from games.models import Match, MatchStatus

    match = Match.objects.create(
        group=group, creator=users[0], game_type=game, status=MatchStatus.RUNNING, entry_fee=fee, pot=pot,
        min_players=len(users), max_players=len(users), join_deadline=timezone.now(), options=options,
    )  # fmt: skip
    board.start(match.pk, board.new_state(game, [u.pk for u in users], time.time(), seed="api", options=options))
    return match


@pytest.mark.django_db
def test_crash_page_and_api_hide_the_crash_moment(client, group, make_user, fresh_redis):
    from arcade import board
    from games.models import Match

    from .test_live_chess import post

    users = [make_user(first_name=n) for n in ("آرش", "بهار")]
    match = _running(group, users, "crash", {"variant": "3", "house_percent": 5})
    page = client.get(f"/arcade/board/{match.token}/").content.decode()
    assert "crash.js" in page and 'id="cash-btn"' in page and 'id="chat-lock"' in page
    _, data = post(client, "board/state", users[0], match_token=match.token, chat_after=0)
    view = data["state"]
    assert view["game"] == "crash" and view["phase"] == "wait" and view["point"] is None and view["house_percent"] == 5
    assert post(client, "board/action", users[0], match_token=match.token, action="crash_cash")[1]["error"] == "not_flying"
    # پرواز را جلو می‌بریم: مهلت (لحظه‌ی انفجار) در جواب‌های «تغییری نیست» هم نمی‌آید
    board.update(match.pk, lambda s: s.update(start_at=time.time() - 0.5, deadline=time.time() - 0.5, point=30.0) or crash.advance(s, time.time()))
    state = Match.objects.get(pk=match.pk).state["board"]
    assert state["phase"] == "fly"
    _, data = post(client, "board/state", users[1], match_token=match.token, version=state["version"], chat_after=0)
    assert data["changed"] is False and data["left_ms"] == 0
    status, data = post(client, "board/action", users[1], match_token=match.token, action="crash_cash")
    assert status == 200 and data["state"]["seats"][1]["cashed"] >= 1.0
    assert post(client, "board/action", users[0], match_token=match.token, action="hokm_play", card="As")[1]["error"] == "bad_action"


@pytest.mark.django_db
def test_hokm2_page_and_draw_api(client, group, make_user, fresh_redis):
    from games.models import Match

    from .test_live_chess import post

    users = [make_user(first_name=n) for n in ("آرش", "بهار")]
    match = _running(group, users, "hokm2", {"variant": "3"})
    page = client.get(f"/arcade/board/{match.token}/").content.decode()
    assert "hokm.js" in page and 'id="draw-pick"' in page
    state = Match.objects.get(pk=match.pk).state["board"]
    hakem = users[state["hakem"]]
    post(client, "board/action", hakem, match_token=match.token, action="hokm_trump", suit="s")
    _, data = post(client, "board/state", hakem, match_token=match.token)
    assert data["state"]["phase"] == "draw" and data["state"]["draw_card"]
    assert post(client, "board/action", hakem, match_token=match.token, action="hokm_draw", keep="x")[1]["error"] == "illegal_move"
    status, data = post(client, "board/action", hakem, match_token=match.token, action="hokm_draw", keep=True)
    assert status == 200 and len(data["state"]["hand"]) == 6 and data["state"]["draw_card"] is None


def test_house_cut_is_small_and_never_more_than_the_pot():
    from types import SimpleNamespace

    from games.engine.services import house_cut

    assert house_cut(SimpleNamespace(options={"house_percent": 5}, entry_fee=100, pot=1000)) == 50
    assert house_cut(SimpleNamespace(options={"house_percent": 5}, entry_fee=10, pot=30)) == 1
    assert house_cut(SimpleNamespace(options={}, entry_fee=100, pot=1000)) == 0  # بقیه‌ی بازی‌ها بدون سهم
    assert house_cut(SimpleNamespace(options={"house_percent": 5}, entry_fee=0, pot=0)) == 0


def _world(n, chat_id):
    from core.models import TelegramGroup, TelegramUser
    from wallet.models import TxType
    from wallet.services import apply_transaction

    group = TelegramGroup.objects.create(chat_id=chat_id, title="انفجار")
    users = [TelegramUser.objects.create(tg_id=9500 + i + chat_id % 7 * 10, first_name=f"بازیکن{i}", started_bot=True) for i in range(n)]
    for u in users:
        apply_transaction(u, 500, TxType.ADMIN_GRANT, f"crash-test:{u.pk}")
    return group, users


@pytest.mark.django_db(transaction=True)
async def test_bot_runs_crash_and_keeps_the_house_cut(fresh_redis, settings):
    from asgiref.sync import sync_to_async

    from arcade import board
    from bot.runner import MatchManager
    from games.catalog import get_info
    from games.models import Match, MatchStatus
    from wallet.management.commands.audit_wallets import find_mismatches, match_problems
    from wallet.models import CoinTransaction, TxType

    from .fake_telegram import FakeApplication

    settings.MINIAPP_BASE_URL = "https://arcade.example"
    settings.CRASH_HOUSE_PERCENT = 5
    app = FakeApplication()
    group, users = await sync_to_async(_world)(3, -100900)
    manager = MatchManager(app)
    info = get_info("crash")
    assert info.miniapp_only and (info.min_players, info.max_players) == (2, 10)
    active = await manager.create_lobby(group, users[0], info, fee=100, split=[100], join_seconds=60, options={"variant": "1"})
    assert "۵٪ سهم سرویس" in app.bot.sent[-1]["text"]
    for user in users:
        await manager.join(active, user)
    await app.job_queue.fire("lobby_close")
    match = await sync_to_async(Match.objects.get)(pk=active.match_id)
    assert match.status == MatchStatus.RUNNING and match.state["board"]["game"] == "crash"
    assert match.options["house_percent"] == 5

    def fly_and_cash(s):
        now = time.time()
        s["point"], s["start_at"], s["deadline"] = 30.0, now - 6, now - 6
        crash.advance(s, now)
        for uid in s["seats"][:2]:
            crash.cash_out(s, uid, now)

    await sync_to_async(board.update)(active.match_id, fly_and_cash)

    def crash_now(s):
        s["deadline"] = time.time() - 1
        crash.advance(s, time.time())

    await sync_to_async(board.update)(active.match_id, crash_now)
    await manager.poll_live(active)
    assert active.phase == "done"
    prizes = await sync_to_async(lambda: sum(CoinTransaction.objects.filter(type=TxType.PRIZE).values_list("amount", flat=True)))()
    final = await sync_to_async(Match.objects.get)(pk=active.match_id)
    assert final.pot == 300 and final.options["house_cut"] == 15 and prizes == 285
    assert await sync_to_async(match_problems)() == [] and await sync_to_async(find_mismatches)() == []
    shown = " ".join((m.get("text") or m.get("caption") or "") for m in app.bot.sent)
    assert "سهم سرویس" in shown


@pytest.mark.django_db(transaction=True)
async def test_hokm2_lobby_with_one_player_is_cancelled(fresh_redis, settings):
    from asgiref.sync import sync_to_async

    from bot.runner import MatchManager
    from core import texts
    from games.catalog import get_info
    from games.models import Match, MatchStatus

    from .fake_telegram import FakeApplication

    settings.MINIAPP_BASE_URL = "https://arcade.example"
    app = FakeApplication()
    group, users = await sync_to_async(_world)(1, -100901)
    manager = MatchManager(app)
    active = await manager.create_lobby(group, users[0], get_info("hokm2"), fee=50, split=[100], join_seconds=60, options={})
    await manager.join(active, users[0])
    await app.job_queue.fire("lobby_close")
    match = await sync_to_async(Match.objects.get)(pk=active.match_id)
    assert match.status == MatchStatus.CANCELLED
    shown = " ".join((m.get("text") or "") for m in app.bot.sent) + " ".join((e.get("text") or "") for e in app.bot.edits)
    assert texts.CANCEL_REASONS["hokm_two"] in shown


def test_retired_arcade_games_are_hidden_but_their_code_stays():
    from arcade.sim import RETIRED, all_simulators, get_simulator
    from games.catalog import catalog, get_info

    assert RETIRED == {"colorswitch", "g2048", "helix", "stack", "jumper", "runner", "timing", "breakout", "snake"}
    assert not set(all_simulators()) & RETIRED and set(all_simulators(include_retired=True)) >= RETIRED
    assert all(get_simulator(k) is not None for k in RETIRED)  # برای برگرداندن کافی است از RETIRED حذف شوند
    assert "arcade_helix" not in catalog(include_disabled=True) and get_info("arcade_helix") is not None
