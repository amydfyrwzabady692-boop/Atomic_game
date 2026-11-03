"""حکم: قوانین موتور (تعیین حاکم، پخش ۵+۴+۴، پیروی از خال، برنده‌ی دست، کُت و حاکم‌کُت، چرخش حاکم، پایان بازی،
وقت تمام‌شدن و غایب، ترک بازی) و نمایشِ بدون لو رفتن کارت‌ها."""

import random

import pytest

from games.chess.live import LiveError
from games.hokm import live as hokm

SEATS = [11, 22, 33, 44]


def table(seed="t", target=7):
    return hokm.new_state(list(SEATS), 0.0, seed=seed, target=target)


def uid(state, seat):
    return state["seats"][seat]


def with_trump(state, trump="h"):
    """حاکم حکم را انتخاب می‌کند تا همه ۱۳ کارت داشته باشند."""
    hokm.choose_trump(state, uid(state, state["hakem"]), trump, 1.0)
    return state


def rig(state, hands, trump="h", leader=0):
    """صحنه‌ی دلخواه: دست‌ها، حکم و نفری که دست را باز می‌کند."""
    state["hands"] = [list(h) for h in hands]
    state["trump"] = trump
    state["phase"] = "play"
    state["hakem"] = leader
    state["turn"] = leader
    state["leader"] = leader
    state["trick"] = []
    state["tricks"] = [0, 0]
    state["deadline"] = 10**6
    return state


def test_first_hakem_is_the_first_ace_dealt_face_up():
    for seed in ("a", "b", "c", "d", "e"):
        seat, draw = hokm.first_hakem(seed)
        cards = [c for _, c in draw]
        assert cards[-1][0] == "A" and all(c[0] != "A" for c in cards[:-1])
        assert [s for s, _ in draw] == [i % 4 for i in range(len(draw))] and draw[-1][0] == seat
        assert hokm.new_state(list(SEATS), 0, seed=seed)["hakem"] == seat


def test_deal_five_then_trump_then_the_rest():
    s = table()
    hakem = s["hakem"]
    assert s["phase"] == "trump" and s["turn"] == hakem and all(len(h) == 5 for h in s["hands"])
    other = uid(s, (hakem + 1) % 4)
    with pytest.raises(LiveError) as err:
        hokm.choose_trump(s, other, "s", 1)
    assert err.value.code == "not_your_turn"
    with pytest.raises(LiveError):
        hokm.choose_trump(s, uid(s, hakem), "x", 1)
    with_trump(s, "s")
    cards = [c for h in s["hands"] for c in h]
    assert len(cards) == 52 and len(set(cards)) == 52 and all(len(h) == 13 for h in s["hands"])
    assert s["trump"] == "s" and s["phase"] == "play" and s["turn"] == hakem == s["leader"]


def test_players_must_follow_the_led_suit():
    s = rig(table(), [["As", "Kh", "2c"], ["3s", "Ah", "4d"], ["5c", "6d", "7h"], ["8s", "9s", "Tc"]], trump="h")
    hokm.play(s, 11, "As", 1)
    # صندلی ۱ پیک دارد پس نمی‌تواند حکم (دل) بزند
    assert hokm.legal_cards(s, 1) == ["3s"]
    with pytest.raises(LiveError) as err:
        hokm.play(s, 22, "Ah", 1)
    assert err.value.code == "illegal_move"
    hokm.play(s, 22, "3s", 1)
    # صندلی ۲ پیک ندارد: هر کارتی آزاد است (بُریدن با حکم یا دور ریختن)
    assert sorted(hokm.legal_cards(s, 2)) == sorted(["5c", "6d", "7h"])
    with pytest.raises(LiveError):
        hokm.play(s, 44, "8s", 1)  # نوبتش نیست


def test_trick_goes_to_the_highest_trump_or_the_highest_of_the_led_suit():
    assert hokm.trick_winner([[0, "Ts"], [1, "Ks"], [2, "As"], [3, "2s"]], "h") == 2
    assert hokm.trick_winner([[0, "Ts"], [1, "2h"], [2, "As"], [3, "Ah"]], "h") == 3
    assert hokm.trick_winner([[0, "Ts"], [1, "2h"], [2, "As"], [3, "Kc"]], "h") == 1
    # دور ریختن خالِ دیگر (نه حکم) هرگز نمی‌برد، حتی آس
    assert hokm.trick_winner([[0, "2s"], [1, "Ac"], [2, "Ad"], [3, "3s"]], "h") == 3
    # وقتی خال زمین خود حکم است، بزرگ‌ترین حکم می‌برد
    assert hokm.trick_winner([[0, "5h"], [1, "9h"], [2, "Ac"], [3, "2h"]], "h") == 1


def play_trick(s, cards_by_seat):
    """یک دست کامل از نفری که نوبتش است؛ ``cards_by_seat`` کارت هر صندلی."""
    for _ in range(4):
        seat = s["turn"]
        hokm.play(s, uid(s, seat), cards_by_seat[seat], 1)


def test_round_ends_at_seven_tricks_with_one_point_and_the_hakem_stays():
    s = table(seed="r")
    hakem = s["hakem"]
    team = hokm.team_of(hakem)
    with_trump(s, "s")
    s["tricks"] = [0, 0]
    s["tricks"][team] = 6
    s["tricks"][1 - team] = 3
    # حاکم با آس حکم دست را می‌برد و تیمش به ۷ می‌رسد
    hands = [[c] for c in ("2c", "3c", "4c", "5c")]
    hands[hakem] = ["As"]
    rig(s, hands, trump="s", leader=hakem)
    s["tricks"][team], s["tricks"][1 - team] = 6, 3
    cards = {seat: s["hands"][seat][0] for seat in range(4)}
    play_trick(s, cards)
    assert s["result"]["winner_team"] == team and s["result"]["points"] == 1 and s["result"]["kot"] == ""
    assert s["points"][team] == 1 and s["hakem"] == hakem and s["phase"] == "pause"
    assert hokm.check_timeout(s, 10**7) and s["round"] == 2 and s["phase"] == "trump" and s["turn"] == hakem


def finish_round(s, winner_team, loser_tricks):
    """دور را با بردن تیم ``winner_team`` (۷ دست) و ``loser_tricks`` دست برای حریف تمام می‌کند."""
    winner_seat = winner_team  # صندلی ۰ یا ۱ از همان تیم
    hands = [["2c"], ["3c"], ["4c"], ["5c"]]
    hands[winner_seat] = ["As"]
    hakem = s["hakem"]
    rig(s, hands, trump="s", leader=winner_seat)
    s["hakem"] = hakem
    s["tricks"] = [0, 0]
    s["tricks"][winner_team] = 6
    s["tricks"][1 - winner_team] = loser_tricks
    play_trick(s, {seat: s["hands"][seat][0] for seat in range(4)})


def test_kot_is_two_points_and_hakem_kot_is_three_and_the_hakem_moves_on():
    s = table(seed="k")
    s["hakem"] = 0
    finish_round(s, winner_team=0, loser_tricks=0)  # تیم حاکم ۷-۰ برد: کُت
    assert s["result"]["kot"] == "kot" and s["points"] == [2, 0] and s["hakem"] == 0
    hokm.check_timeout(s, 10**7)
    s["hakem"] = 0
    finish_round(s, winner_team=1, loser_tricks=0)  # تیم حاکم ۰ دست: حاکم‌کُت
    assert s["result"]["kot"] == "hakem_kot" and s["points"] == [2, 3]
    assert s["hakem"] == 1  # حکم به نفر بعدی (از تیم برنده) رسید
    hokm.check_timeout(s, 2 * 10**7)
    finish_round(s, winner_team=0, loser_tricks=4)  # تیم غیرحاکم ۷-۴ برد: یک امتیاز و حاکم عوض می‌شود
    assert s["result"]["points"] == 1 and s["points"] == [3, 3] and s["hakem"] == 2


def test_game_ends_at_the_target_and_both_partners_share_the_win():
    s = table(seed="g", target=3)
    s["hakem"] = 0
    finish_round(s, winner_team=1, loser_tricks=0)  # حاکم‌کُت: ۳ امتیاز و پایان
    assert s["over"] == {"reason": "points", "winner_team": 1, "winner": None} and s["phase"] == "over"
    scores = dict(hokm.standings(s))
    assert scores[uid(s, 1)] == scores[uid(s, 3)] == 3 and scores[uid(s, 0)] == scores[uid(s, 2)] == 0


def test_timeouts_play_a_legal_low_card_and_mark_the_player_away():
    s = table(seed="o")
    hakem = s["hakem"]
    five = list(s["hands"][hakem])
    # حاکم وقت انتخاب حکم را از دست داد: خالِ پرتعدادترِ همان ۵ کارت حکم می‌شود
    assert hokm.check_timeout(s, 10**6)
    assert s["trump"] == hokm.best_trump(five) and s["phase"] == "play" and s["misses"][hakem] == 1
    assert not s["away"][hakem]
    # دومین وقت‌تمام‌شدن پشت هم (اولین کارت): غایب
    legal = hokm.legal_cards(s, hakem)
    assert hokm.check_timeout(s, s["deadline"] + 1)
    assert s["last_action"] == {"kind": "play", "seat": hakem, "card": s["trick"][0][1], "timeout": True}
    assert s["trick"][0][1] in legal and s["misses"][hakem] == 2 and s["away"][hakem]
    nxt = s["turn"]
    assert hokm.check_timeout(s, s["deadline"] + 1)
    assert s["misses"][nxt] == 1 and not s["away"][nxt]
    # حرکت خود بازیکن «غایب» را برمی‌گرداند
    s2 = rig(table(), [["As", "Kd"], ["3s", "Ah"], ["5c", "6d"], ["8s", "9s"]], trump="h")
    s2["away"][0], s2["misses"][0] = True, 2
    hokm.play(s2, 11, "As", 5.0)
    assert s2["away"][0] is False and s2["misses"][0] == 0


def test_away_players_get_a_short_deadline():
    s = rig(table(), [["As", "Kd"], ["3s", "Ah"], ["5c", "6d"], ["8s", "9s"]], trump="h")
    s["away"][1] = True
    hokm.play(s, 11, "As", 100.0)
    assert s["turn"] == 1 and s["deadline"] == 100.0 + hokm.AWAY_SECONDS
    assert hokm.view(s, 11, 100.0)["move_seconds"] == hokm.AWAY_SECONDS


def test_auto_card_keeps_trumps_when_possible():
    s = rig(table(), [["As"], ["2h", "9c", "3d"], ["5c"], ["8s"]], trump="h")
    hokm.play(s, 11, "As", 1)
    # پیک ندارد: کوچک‌ترین کارت غیرحکم را می‌دهد، نه حکم
    assert hokm.auto_card(s, 1) == "3d"


def test_leaving_ends_the_game_and_the_team_loses():
    s = table(seed="l")
    hokm.resign(s, uid(s, 2), 1)
    assert s["over"]["reason"] == "left" and s["over"]["winner_team"] == 1 and s["left"][2]
    scores = dict(hokm.standings(s))
    assert scores[uid(s, 1)] == scores[uid(s, 3)] == s["target"] and scores[uid(s, 0)] == scores[uid(s, 2)] == 0
    with pytest.raises(LiveError):
        hokm.resign(s, uid(s, 0), 1)


def test_view_shows_only_your_own_cards():
    s = with_trump(table(seed="v"), "d")
    me = (s["hakem"] + 1) % 4
    view = hokm.view(s, uid(s, me), 1)
    assert sorted(view["hand"]) == sorted(s["hands"][me]) and view["you"] == me
    assert "hands" not in view and all(seat["count"] == 13 for seat in view["seats"])
    assert view["legal"] == [] and view["trump"] == "d"
    # کارت‌های من مرتب: حکم اول، هر خال از بزرگ به کوچک
    suits = [c[1] for c in view["hand"]]
    assert suits == sorted(suits, key=lambda x: (x != "d", "shcd".index(x) if x != "d" else -1))
    spectator = hokm.view(s, None, 1)
    assert spectator["hand"] == [] and spectator["you"] is None
    hakem_view = hokm.view(s, uid(s, s["hakem"]), 1)
    assert sorted(hakem_view["legal"]) == sorted(s["hands"][s["hakem"]])


@pytest.mark.parametrize("seed", range(25))
def test_random_games_always_finish_and_keep_every_card(seed):
    rng = random.Random(seed)
    s = hokm.new_state(list(SEATS), 0, seed=f"rand{seed}", target=rng.choice(hokm.TARGETS))
    now = 0.0
    for _ in range(5000):
        if s["over"]:
            break
        now += 1
        if s["phase"] == "pause" or rng.random() < 0.05:
            now = (s["deadline"] or now) + 1
            hokm.check_timeout(s, now)
            continue
        seat = s["turn"]
        if s["phase"] == "trump":
            hokm.choose_trump(s, uid(s, seat), rng.choice("shdc"), now)
            continue
        cards = [c for h in s["hands"] for c in h] + [c for _, c in s["trick"]] + [c for w in s["won"] for c in w]
        assert len(cards) == 52 and len(set(cards)) == 52
        assert sum(s["tricks"]) == s["trick_no"] and max(s["tricks"]) < hokm.TRICKS_TO_WIN
        hokm.play(s, uid(s, seat), rng.choice(hokm.legal_cards(s, seat)), now)
    assert s["over"] and max(s["points"]) >= s["target"]
    scores = dict(hokm.standings(s))
    win = s["over"]["winner_team"]
    assert scores[uid(s, win)] == scores[uid(s, win + 2)] > scores[uid(s, 1 - win)]


# ====================================================================== ربات و مینی‌اپ: لابی ۴نفره، میز، تقسیم جایزه
@pytest.fixture
def fresh_redis():
    from core.redis import reset_clients

    reset_clients()
    yield
    reset_clients()


def _world(n_players, fee=100, chat_id=-100880):
    from core.models import TelegramGroup, TelegramUser
    from wallet.models import TxType
    from wallet.services import apply_transaction

    group = TelegramGroup.objects.create(chat_id=chat_id, title="حکم")
    users = [TelegramUser.objects.create(tg_id=9300 + i, first_name=f"حکم‌باز{i}", started_bot=True) for i in range(n_players)]
    for u in users:
        apply_transaction(u, 500, TxType.ADMIN_GRANT, f"hokm-test:{u.pk}")
    return group, users


@pytest.mark.django_db(transaction=True)
async def test_bot_runs_hokm_with_four_players_and_the_winning_pair_splits_the_pot(fresh_redis, settings):
    import time

    from asgiref.sync import sync_to_async

    from arcade import board
    from bot.runner import MatchManager
    from core import texts
    from games.catalog import get_info
    from games.models import Match, MatchStatus
    from wallet.models import CoinTransaction, TxType

    from .fake_telegram import FakeApplication

    settings.MINIAPP_BASE_URL = "https://arcade.example"
    app = FakeApplication()
    group, users = await sync_to_async(_world)(4)
    manager = MatchManager(app)
    info = get_info("hokm")
    assert (info.min_players, info.max_players, info.miniapp_only) == (4, 4, True)
    active = await manager.create_lobby(group, users[0], info, fee=100, split=[100], join_seconds=60, options={"variant": "3"})
    assert texts.SPLIT_TEAM in app.bot.sent[-1]["text"]
    for user in users:
        await manager.join(active, user)
    # لابی با نفر چهارم پر شد و بازی بدون منتظر ماندن برای پایان زمان روی میز مینی‌اپ شروع می‌شود
    await app.job_queue.fire("lobby_close")
    match = await sync_to_async(Match.objects.get)(pk=active.match_id)
    state = match.state["board"]
    assert match.status == MatchStatus.RUNNING and state["game"] == "hokm" and state["target"] == 3
    opening = next(m for m in reversed(app.bot.sent) if "حکم" in (m.get("text") or "") and "حاکم" in (m.get("text") or ""))
    assert texts.HOKM_PLAY_BTN in str(opening["reply_markup"])
    # کارت هیچ‌کس در پیام گروه نیست
    for hand in state["hands"]:
        assert not any(card in opening["text"] for card in hand)

    rng = random.Random(4)

    def step(s):
        now = time.time()
        if s["phase"] == "pause":
            s["deadline"] = now - 1
            hokm.check_timeout(s, now)
        elif s["phase"] == "trump":
            hokm.choose_trump(s, s["seats"][s["turn"]], rng.choice("shdc"), now)
        elif s["phase"] == "play":
            seat = s["turn"]
            hokm.play(s, s["seats"][seat], rng.choice(hokm.legal_cards(s, seat)), now)

    for _ in range(4000):
        current = (await sync_to_async(Match.objects.get)(pk=active.match_id)).state["board"]
        if current["over"]:
            break
        await sync_to_async(board.update)(active.match_id, step)
    await manager.poll_live(active)
    assert active.phase == "done"
    final = (await sync_to_async(Match.objects.get)(pk=active.match_id)).state["board"]
    team = final["over"]["winner_team"]
    winners = {final["seats"][team], final["seats"][team + 2]}
    prizes = await sync_to_async(lambda: dict(CoinTransaction.objects.filter(type=TxType.PRIZE).values_list("user_id", "amount")))()
    assert prizes == {uid: 200 for uid in winners}
    texts_sent = " ".join(m.get("text") or "" for m in app.bot.sent) + " ".join(e.get("text") or "" for e in app.bot.edits)
    assert "بازی تمام شد" in texts_sent and "نصف‌نصف" in texts_sent


@pytest.mark.django_db(transaction=True)
async def test_hokm_lobby_without_four_players_is_cancelled_and_refunded(fresh_redis, settings):
    from asgiref.sync import sync_to_async

    from bot.runner import MatchManager
    from core import texts
    from core.models import TelegramUser
    from games.catalog import get_info
    from games.models import Match, MatchStatus

    from .fake_telegram import FakeApplication

    settings.MINIAPP_BASE_URL = "https://arcade.example"
    app = FakeApplication()
    group, users = await sync_to_async(_world)(3, chat_id=-100881)
    manager = MatchManager(app)
    active = await manager.create_lobby(group, users[0], get_info("hokm"), fee=50, split=[100], join_seconds=60, options={})
    for user in users:
        await manager.join(active, user)
    await app.job_queue.fire("lobby_close")
    match = await sync_to_async(Match.objects.get)(pk=active.match_id)
    assert match.status == MatchStatus.CANCELLED
    shown = " ".join((m.get("text") or "") for m in app.bot.sent) + " ".join((e.get("text") or "") for e in app.bot.edits)
    assert texts.CANCEL_REASONS["hokm_four"] in shown
    coins = await sync_to_async(lambda: sorted(TelegramUser.objects.filter(pk__in=[u.pk for u in users]).values_list("coins", flat=True)))()
    assert coins == [500, 500, 500]


@pytest.mark.django_db
def test_hokm_table_api_hides_hands_and_checks_every_move(client, group, make_user, fresh_redis):
    import time

    from django.utils import timezone

    from arcade import board
    from games.models import Match, MatchStatus

    from .test_live_chess import post

    users = [make_user(first_name=n) for n in ("آرش", "بهار", "پویا", "تینا")]
    match = Match.objects.create(
        group=group, creator=users[0], game_type="hokm", status=MatchStatus.RUNNING,
        min_players=4, max_players=4, join_deadline=timezone.now(), options={"variant": "7"},
    )  # fmt: skip
    board.start(match.pk, board.new_state("hokm", [u.pk for u in users], time.time(), seed="api", options=match.options))
    page = client.get(f"/arcade/board/{match.token}/").content.decode()
    assert "hokm.js" in page and 'id="hand"' in page and "board/cards.js" in page

    state = Match.objects.get(pk=match.pk).state["board"]
    hakem = users[state["hakem"]]
    other = users[(state["hakem"] + 1) % 4]
    _, data = post(client, "board/state", other, match_token=match.token, chat_after=0)
    view = data["state"]
    assert view["game"] == "hokm" and view["players"]["s0"] == "آرش" and len(view["hand"]) == 5
    assert "hands" not in view and data["can_chat"] is True
    assert post(client, "board/action", other, match_token=match.token, action="hokm_trump", suit="s")[1]["error"] == "not_your_turn"
    assert post(client, "board/action", hakem, match_token=match.token, action="hokm_trump", suit="")[1]["error"] == "illegal_move"
    status, data = post(client, "board/action", hakem, match_token=match.token, action="hokm_trump", suit="h")
    assert status == 200 and data["state"]["trump"] == "h" and len(data["state"]["hand"]) == 13
    assert sorted(data["state"]["legal"]) == sorted(data["state"]["hand"])  # حاکم دست اول را باز می‌کند
    first = data["state"]["hand"][0]
    assert post(client, "board/action", hakem, match_token=match.token, action="hokm_play", card="ZZ")[1]["error"] == "illegal_move"
    status, data = post(client, "board/action", hakem, match_token=match.token, action="hokm_play", card=first)
    assert status == 200 and data["state"]["trick"] == [[state["hakem"], first]]
    # حرکت حکم در بازی دیگر رد می‌شود و ترک بازی یعنی باخت تیم
    assert post(client, "board/action", other, match_token=match.token, action="fold")[1]["error"] == "bad_action"
    status, data = post(client, "board/action", other, match_token=match.token, action="resign")
    assert data["state"]["over"]["reason"] == "left" and data["state"]["over"]["winner_team"] == 1 - hokm.team_of(users.index(other))


def test_group_text_shows_teams_trump_and_round_results():
    from bot.render import hokm_text

    s = table(seed="txt", target=5)
    names = {11: "آرش", 22: "بهار", 33: "پویا", 44: "تینا"}
    text = hokm_text(s, names)
    assert "آرش" in text and "پویا" in text and "حاکم" in text and "انتخاب می‌کند" in text
    with_trump(s, "d")
    assert "خشت" in hokm_text(s, names)
    s["hakem"] = 1
    finish_round(s, winner_team=0, loser_tricks=0)  # تیم غیرحاکم ۷-۰: حاکم‌کُت
    text = hokm_text(s, names)
    assert "حاکم‌کُت" in text and "+۳" in text and "دور بعد" in text
    for hand in s["hands"]:
        assert not any(card in text for card in hand)
