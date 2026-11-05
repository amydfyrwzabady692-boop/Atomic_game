"""حکم سه‌نفره و چهاربرگ (پاسور): قوانین موتور، نمایش بدون لو رفتن کارت‌ها، میز مینی‌اپ و ربات؛ و بستن گفت‌وگوی میز با
رأی بازیکن‌ها (شک به تقلب) و چیدن تصادفی صندلی‌ها و یارها."""

import random
import time

import pytest

from games.chaharbarg import live as cb
from games.chess.live import LiveError
from games.hokm import live as hokm

SEATS3 = [11, 22, 33]


# ====================================================================== حکم سه‌نفره
def solo(seed="s", target=7):
    return hokm.new_state(list(SEATS3), 0.0, seed=seed, target=target)


def test_three_player_hokm_deals_seventeen_each_without_the_two_of_clubs():
    s = solo()
    assert s["game"] == "hokm3" and hokm.size(s) == 3 and hokm.need(s) == hokm.SOLO_TRICKS_TO_WIN == 6
    assert s["points"] == [0, 0, 0] and s["tricks"] == [0, 0, 0]
    assert s["phase"] == "trump" and all(len(h) == 5 for h in s["hands"])
    hokm.choose_trump(s, s["seats"][s["hakem"]], "s", 1.0)
    cards = [c for h in s["hands"] for c in h]
    assert all(len(h) == 17 for h in s["hands"]) and len(set(cards)) == 51 and hokm.SOLO_REMOVED not in cards
    assert [hokm.team(s, i) for i in range(3)] == [0, 1, 2] and hokm.teams(s) == [[0], [1], [2]]
    view = hokm.view(s, 22, 1.0)
    assert view["solo"] is True and view["need"] == 6 and len(view["seats"]) == 3 and len(view["hand"]) == 17
    assert "hands" not in view and all("hand" not in seat for seat in view["seats"])


def test_three_player_round_goes_to_whoever_reaches_six_tricks_and_kot_needs_zero_for_both_others():
    s = solo(seed="k")
    hokm.choose_trump(s, s["seats"][s["hakem"]], "h", 1.0)
    hakem = s["hakem"]
    s["tricks"] = [0, 0, 0]
    s["tricks"][hakem] = 6
    hokm._end_round(s, 2.0)
    assert s["result"]["kot"] == "kot" and s["points"][hakem] == 2 and s["hakem"] == hakem
    s2 = solo(seed="k2")
    hokm.choose_trump(s2, s2["seats"][s2["hakem"]], "h", 1.0)
    other = (s2["hakem"] + 1) % 3
    hakem2 = s2["hakem"]
    s2["tricks"] = [1, 1, 1]
    s2["tricks"][other] = 6
    hokm._end_round(s2, 2.0)
    assert s2["result"]["kot"] == "" and s2["points"][other] == 1 and s2["hakem"] == (hakem2 + 1) % 3


@pytest.mark.parametrize("seed", range(12))
def test_random_three_player_games_always_finish_and_keep_every_card(seed):
    rng = random.Random(seed)
    s = hokm.new_state(list(SEATS3), 0, seed=f"solo{seed}", target=rng.choice(hokm.TARGETS))
    now = 0.0
    for _ in range(6000):
        if s["over"]:
            break
        now += 1
        if s["phase"] == "pause" or rng.random() < 0.05:
            now = (s["deadline"] or now) + 1
            hokm.check_timeout(s, now)
            continue
        seat = s["turn"]
        if s["phase"] == "trump":
            hokm.choose_trump(s, s["seats"][seat], rng.choice("shdc"), now)
            continue
        cards = [c for h in s["hands"] for c in h] + [c for _, c in s["trick"]] + [c for w in s["won"] for c in w]
        assert len(cards) == 51 and len(set(cards)) == 51
        assert sum(s["tricks"]) == s["trick_no"] and max(s["tricks"]) < 6
        hokm.play(s, s["seats"][seat], rng.choice(hokm.legal_cards(s, seat)), now)
    assert s["over"] and max(s["points"]) >= s["target"]
    scores = dict(hokm.standings(s))
    win = s["over"]["winner_team"]
    assert scores[s["seats"][win]] > max(v for k, v in scores.items() if k != s["seats"][win])


def test_three_player_leaver_scores_zero_and_the_best_of_the_rest_wins():
    s = solo(seed="left")
    s["points"] = [2, 1, 0]
    hokm.resign(s, 11)
    assert s["over"]["reason"] == "left" and s["over"]["winner_team"] == 1
    scores = dict(hokm.standings(s))
    assert scores[11] == 0 and scores[22] > scores[33]


def test_hokm3_group_text_lists_three_players():
    from bot.render import hokm_text

    s = solo(seed="txt")
    text = hokm_text(s, {11: "آرش", 22: "بهار", 33: "پویا"})
    assert "آرش" in text and "بهار" in text and "پویا" in text and "حاکم" in text
    for hand in s["hands"]:
        assert not any(card in text for card in hand)


# ====================================================================== چهاربرگ: برداشتن
def test_numeric_cards_take_cards_that_make_eleven():
    table = ["5h", "6c", "3d", "2s", "Kd"]
    assert cb.options(table, "5c") == [["6c"]]
    assert cb.options(table, "4c") == [["5h", "2s"]]
    assert cb.options(table, "Ac") == [["5h", "3d", "2s"]]  # آس = ۱
    assert cb.options(["5h", "Kd"], "Ac") == []
    assert cb.options(["Td"], "Ac") == [["Td"]]


def test_faces_and_jacks():
    assert cb.options(["Kd", "Kc", "Qh"], "Ks") == [["Kd"], ["Kc"]]
    assert cb.options(["Kd", "Qh"], "Qs") == [["Qh"]]
    assert cb.options(["Kd", "Qh", "5s", "Jc"], "Jd") == [["5s", "Jc"]]  # سرباز همه جز شاه و بی‌بی
    assert cb.options(["Kd", "Qh"], "Jd") == []


def cb_table(n=2, seed="cb", target=0):
    return cb.new_state([100 + i for i in range(n)], 0.0, seed=seed, target=target)


def rig(s, table, hands, turn=0):
    s["table"] = list(table)
    s["hands"] = [list(h) for h in hands]
    s["turn"] = turn
    s["phase"] = "play"
    s["deadline"] = 10**6
    return s


def test_play_checks_the_choice_and_sur_scores_five():
    s = rig(cb_table(), ["5h", "6c"], [["5c", "9d", "2d", "Ah"], ["3c", "4c", "7c", "8c"]])
    with pytest.raises(LiveError) as err:
        cb.play(s, 101, "3c", None, 1)
    assert err.value.code == "not_your_turn"
    with pytest.raises(LiveError):
        cb.play(s, 100, "5c", ["5h"], 1)  # ۵ + ۵ ≠ ۱۱
    cb.play(s, 100, "5c", ["6c"], 1)
    assert s["table"] == ["5h"] and sorted(s["captured"][0]) == ["5c", "6c"] and s["surs"][0] == 0
    cb.play(s, 101, "3c", [], 2)  # زمین گذاشتن
    assert sorted(s["table"]) == ["3c", "5h"] and s["turn"] == 0
    cb.play(s, 100, "2d", None, 3)  # «بهترین برداشت» وقتی چیزی جمع ۱۱ نمی‌شود یعنی زمین گذاشتن
    assert "2d" in s["table"]
    s = rig(cb_table(seed="sur"), ["5h", "6c"], [["Kc", "9d", "2d", "Ah"], ["3c", "4c", "7c", "8c"]])
    s["table"] = ["4h", "3s"]
    s["hands"][0] = ["4d", "9d", "2d", "Ah"]
    cb.play(s, 100, "4d", ["4h", "3s"], 1)
    assert s["table"] == [] and s["surs"][0] == 1 and s["last_action"]["sur"] is True


def test_a_jack_that_can_capture_cannot_be_laid_down_and_no_jack_on_the_opening_table():
    for seed in range(30):
        s = cb_table(n=random.Random(seed).choice([2, 3, 4]), seed=f"open{seed}")
        assert not any(c[0] == "J" for c in s["table"]) and len(s["table"]) == 4
        assert all(len(h) == 4 for h in s["hands"])
    s = rig(cb_table(), ["5h"], [["Jd", "9d", "2d", "Ah"], ["3c", "4c", "7c", "8c"]])
    with pytest.raises(LiveError):
        cb.play(s, 100, "Jd", [], 1)
    cb.play(s, 100, "Jd", None, 1)
    assert s["table"] == [] and s["surs"][0] == 0  # با سرباز سور حساب نمی‌شود


def test_round_scoring():
    s = cb_table(n=3)
    s["captured"] = [["2c", "3c", "4c", "Ac", "Jd"], ["Td", "As", "5c"], ["Kh"]]
    s["surs"] = [0, 1, 0]
    rows = cb.score_round(s)
    assert rows[0]["clubs_bonus"] == 7 and rows[0]["two_clubs"] == 2 and rows[0]["aces"] == 1 and rows[0]["jacks"] == 1
    assert rows[0]["total"] == 11
    assert rows[1]["ten_diamonds"] == 3 and rows[1]["surs"] == 5 and rows[1]["total"] == 9
    assert rows[2]["total"] == 0
    s["captured"] = [["2c", "3c"], ["4c", "5c"], []]
    s["surs"] = [0, 0, 0]
    assert [r["clubs_bonus"] for r in cb.score_round(s)] == [0, 0, 0]  # تساوی گشنیز: کسی ۷ نمی‌گیرد


@pytest.mark.parametrize("seed", range(20))
def test_random_pasur_games_finish_and_keep_all_52_cards(seed):
    rng = random.Random(seed)
    n = rng.choice([2, 3, 4])
    s = cb.new_state([200 + i for i in range(n)], 0, seed=f"r{seed}", target=rng.choice(cb.TARGETS))
    now = 0.0
    for _ in range(20000):
        if s["over"]:
            break
        now += 1
        if s["phase"] == "pause" or rng.random() < 0.05:
            now = (s["deadline"] or now) + 1
            cb.check_timeout(s, now)
            continue
        cards = [c for h in s["hands"] for c in h] + s["table"] + s["deck"] + [c for w in s["captured"] for c in w]
        assert len(cards) == 52 and len(set(cards)) == 52
        seat = s["turn"]
        card = rng.choice(s["hands"][seat])
        found = cb.options(s["table"], card)
        take = rng.choice(found) if found and (card[0] == "J" or rng.random() < 0.8) else []
        cb.play(s, s["seats"][seat], card, take, now)
    assert s["over"]
    if s["target"]:
        assert max(s["points"]) >= s["target"]
    view = cb.view(s, s["seats"][0], now)
    assert view["game"] == "chaharbarg" and "hands" not in view and len(view["seats"]) == n


def test_view_shows_only_your_cards_and_options_on_your_turn():
    s = rig(cb_table(), ["5h", "6c"], [["5c", "9d", "2d", "Ah"], ["3c", "4c", "7c", "8c"]])
    mine = cb.view(s, 100, 1)
    assert mine["hand"] == ["5c", "9d", "2d", "Ah"] and mine["options"]["5c"] == [["6c"]] and mine["options"]["9d"] == []
    other = cb.view(s, 101, 1)
    assert other["hand"] == ["3c", "4c", "7c", "8c"] and other["options"] == {}
    assert cb.view(s, None, 1)["hand"] == [] and all(seat["count"] == 4 for seat in mine["seats"])


def test_leaving_scores_zero_and_last_one_standing_wins():
    s = cb_table(n=3)
    s["points"] = [10, 5, 3]
    cb.resign(s, 100)
    assert not s["over"] and s["left"][0]
    scores = dict(cb.standings(s))
    assert scores[100] == 0
    cb.resign(s, 101)
    assert s["over"]["reason"] == "left" and s["over"]["winner"] == 102
    assert cb.view(s, 102, 1)["winner_seat"] == 2


def test_chaharbarg_group_text():
    from bot.render import chaharbarg_text

    s = cb_table(n=3, target=31)
    text = chaharbarg_text(s, {100: "آرش", 101: "بهار", 102: "پویا"})
    assert "آرش" in text and "پویا" in text
    for hand in s["hands"]:
        assert not any(card in text for card in hand)


# ====================================================================== میز مینی‌اپ و بستن گفت‌وگو
@pytest.fixture
def fresh_redis():
    from core.redis import reset_clients

    reset_clients()
    yield
    reset_clients()


def _running(group, users, game, options):
    from django.utils import timezone

    from arcade import board
    from games.models import Match, MatchStatus

    match = Match.objects.create(
        group=group, creator=users[0], game_type=game, status=MatchStatus.RUNNING,
        min_players=len(users), max_players=len(users), join_deadline=timezone.now(), options=options,
    )  # fmt: skip
    board.start(match.pk, board.new_state(game, [u.pk for u in users], time.time(), seed="api", options=options))
    return match


@pytest.mark.django_db
def test_chaharbarg_table_api(client, group, make_user, fresh_redis):
    from games.models import Match

    from .test_live_chess import post

    users = [make_user(first_name=n) for n in ("آرش", "بهار", "پویا")]
    match = _running(group, users, "chaharbarg", {"variant": "31"})
    page = client.get(f"/arcade/board/{match.token}/").content.decode()
    assert "chaharbarg.js" in page and "cardroom.css" in page and 'id="pile"' in page and 'id="chat-lock"' in page
    state = Match.objects.get(pk=match.pk).state["board"]
    assert state["target"] == 31
    turn = users[state["turn"]]
    waiting = users[(state["turn"] + 1) % 3]
    _, data = post(client, "board/state", turn, match_token=match.token, chat_after=0)
    view = data["state"]
    assert view["game"] == "chaharbarg" and len(view["hand"]) == 4 and len(view["table"]) == 4 and "hands" not in view
    assert set(view["options"]) == set(view["hand"]) and "pot_coins" in view
    card = view["hand"][0]
    assert post(client, "board/action", waiting, match_token=match.token, action="cb_play", card=card, take=[])[1]["error"] == "not_your_turn"
    assert post(client, "board/action", turn, match_token=match.token, action="hokm_play", card=card)[1]["error"] == "bad_action"
    status, data = post(client, "board/action", turn, match_token=match.token, action="cb_play", card=card, take=None)
    assert status == 200 and card not in data["state"]["hand"] and data["state"]["turn"] == (state["turn"] + 1) % 3


@pytest.mark.django_db
def test_hokm3_page_and_three_player_api(client, group, make_user, fresh_redis):
    from .test_live_chess import post

    users = [make_user(first_name=n) for n in ("آرش", "بهار", "پویا")]
    match = _running(group, users, "hokm3", {"variant": "3"})
    page = client.get(f"/arcade/board/{match.token}/").content.decode()
    assert "hokm.js" in page and 'id="team-2"' in page and "cardroom.css" in page and "suit-deco" in page
    _, data = post(client, "board/state", users[0], match_token=match.token, chat_after=0)
    assert data["state"]["game"] == "hokm3" and data["state"]["solo"] is True and len(data["state"]["seats"]) == 3
    assert data["chat_locked"] is False


@pytest.mark.django_db
def test_both_players_of_one_team_close_the_hokm_chat_for_the_whole_game(client, group, make_user, fresh_redis):
    from games.models import Match

    from .test_live_chess import post

    users = [make_user(first_name=n) for n in ("آرش", "بهار", "پویا", "تینا", "تماشا")]
    players, watcher = users[:4], users[4]
    match = _running(group, players, "hokm", {"variant": "7"})
    seats = Match.objects.get(pk=match.pk).state["board"]["seats"]
    by_seat = {seat: next(u for u in players if u.pk == uid) for seat, uid in enumerate(seats)}
    assert post(client, "board/chat", by_seat[0], match_token=match.token, text="سلام", chat_after=0)[0] == 200
    assert post(client, "board/chat_lock", watcher, match_token=match.token)[1]["error"] == "not_a_player"
    # یک نفر از هر تیم: هنوز بسته نمی‌شود
    _, data = post(client, "board/chat_lock", by_seat[0], match_token=match.token)
    assert data == {"ok": True, "chat_locked": False, "votes": 1, "need": 2}
    _, data = post(client, "board/chat_lock", by_seat[1], match_token=match.token)
    assert data["chat_locked"] is False and data["votes"] == 1
    assert post(client, "board/chat", by_seat[3], match_token=match.token, text="هنوز باز است", chat_after=0)[0] == 200
    # یار نفر اول هم زد: گفت‌وگو برای همه بسته است
    _, data = post(client, "board/chat_lock", by_seat[2], match_token=match.token)
    assert data["chat_locked"] is True and data["votes"] == 2
    _, data = post(client, "board/chat", by_seat[1], match_token=match.token, text="سلام", chat_after=0)
    assert data["error"] == "chat_locked"
    _, data = post(client, "board/state", by_seat[3], match_token=match.token, chat_after=0)
    assert data["chat_locked"] is True
    _, data = post(client, "board/state", by_seat[3], match_token=match.token, version=data["state"]["version"], chat_after=5)
    assert data["chat_locked"] is True


@pytest.mark.django_db
def test_chat_closes_by_majority_in_free_for_all_tables(client, group, make_user, fresh_redis):
    from .test_live_chess import post

    users = [make_user(first_name=n) for n in ("آرش", "بهار", "پویا")]
    match = _running(group, users, "chaharbarg", {"variant": "0"})
    assert post(client, "board/chat_lock", users[0], match_token=match.token)[1] == {"ok": True, "chat_locked": False, "votes": 1, "need": 2}
    assert post(client, "board/chat_lock", users[0], match_token=match.token)[1]["votes"] == 1  # رأی تکراری حساب نمی‌شود
    assert post(client, "board/chat_lock", users[2], match_token=match.token)[1]["chat_locked"] is True
    assert post(client, "board/chat", users[1], match_token=match.token, text="سلام", chat_after=0)[1]["error"] == "chat_locked"


# ====================================================================== ربات: لابی، شروع، جایزه
def _world(n_players, fee=100, chat_id=-100890):
    from core.models import TelegramGroup, TelegramUser
    from wallet.models import TxType
    from wallet.services import apply_transaction

    group = TelegramGroup.objects.create(chat_id=chat_id, title="کارت")
    users = [TelegramUser.objects.create(tg_id=9400 + i, first_name=f"کارت‌باز{i}", started_bot=True) for i in range(n_players)]
    for u in users:
        apply_transaction(u, 500, TxType.ADMIN_GRANT, f"cards-test:{u.pk}")
    return group, users


@pytest.mark.django_db(transaction=True)
async def test_bot_runs_hokm3_and_the_winner_takes_the_pot(fresh_redis, settings):
    from asgiref.sync import sync_to_async

    from arcade import board
    from bot.runner import MatchManager
    from games.catalog import get_info
    from games.models import Match, MatchStatus
    from wallet.models import CoinTransaction, TxType

    from .fake_telegram import FakeApplication

    settings.MINIAPP_BASE_URL = "https://arcade.example"
    app = FakeApplication()
    group, users = await sync_to_async(_world)(3)
    manager = MatchManager(app)
    info = get_info("hokm3")
    assert (info.min_players, info.max_players, info.miniapp_only) == (3, 3, True)
    active = await manager.create_lobby(group, users[0], info, fee=100, split=[100], join_seconds=60, options={"variant": "3"})
    for user in users:
        await manager.join(active, user)
    await app.job_queue.fire("lobby_close")
    match = await sync_to_async(Match.objects.get)(pk=active.match_id)
    assert match.status == MatchStatus.RUNNING and match.state["board"]["game"] == "hokm3"
    rng = random.Random(3)

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

    for _ in range(5000):
        current = (await sync_to_async(Match.objects.get)(pk=active.match_id)).state["board"]
        if current["over"]:
            break
        await sync_to_async(board.update)(active.match_id, step)
    await manager.poll_live(active)
    assert active.phase == "done"
    final = (await sync_to_async(Match.objects.get)(pk=active.match_id)).state["board"]
    winner = final["seats"][final["over"]["winner_team"]]
    prizes = await sync_to_async(lambda: dict(CoinTransaction.objects.filter(type=TxType.PRIZE).values_list("user_id", "amount")))()
    assert prizes == {winner: 300}


@pytest.mark.django_db(transaction=True)
async def test_bot_runs_chaharbarg_for_two(fresh_redis, settings):
    from asgiref.sync import sync_to_async

    from arcade import board
    from bot.runner import MatchManager
    from games.catalog import get_info
    from games.models import Match, MatchStatus
    from wallet.models import CoinTransaction, TxType

    from .fake_telegram import FakeApplication

    settings.MINIAPP_BASE_URL = "https://arcade.example"
    app = FakeApplication()
    group, users = await sync_to_async(_world)(2, chat_id=-100891)
    manager = MatchManager(app)
    info = get_info("chaharbarg")
    assert (info.min_players, info.max_players, info.miniapp_only) == (2, 4, True)
    active = await manager.create_lobby(group, users[0], info, fee=100, split=[100], join_seconds=60, options={"variant": "0"})
    for user in users:
        await manager.join(active, user)
    await app.job_queue.fire("lobby_close")
    match = await sync_to_async(Match.objects.get)(pk=active.match_id)
    assert match.status == MatchStatus.RUNNING and match.state["board"]["game"] == "chaharbarg"
    assert any("چهاربرگ" in (m.get("text") or "") for m in app.bot.sent)

    def step(s):
        now = time.time()
        if s["phase"] == "pause":
            s["deadline"] = now - 1
            cb.check_timeout(s, now)
        elif s["phase"] == "play":
            seat = s["turn"]
            card, take = cb.auto_move(s, seat)
            cb.play(s, s["seats"][seat], card, take, now)

    for _ in range(200):
        current = (await sync_to_async(Match.objects.get)(pk=active.match_id)).state["board"]
        if current["over"]:
            break
        await sync_to_async(board.update)(active.match_id, step)
    await manager.poll_live(active)
    assert active.phase == "done"
    final = (await sync_to_async(Match.objects.get)(pk=active.match_id)).state["board"]
    prizes = await sync_to_async(lambda: dict(CoinTransaction.objects.filter(type=TxType.PRIZE).values_list("user_id", "amount")))()
    if final["over"]["winner"] is not None:
        assert prizes == {final["over"]["winner"]: 200}
    else:
        assert sum(prizes.values()) == 200


def test_seats_and_partners_are_shuffled_not_join_order():
    import inspect

    from bot import runner

    source = inspect.getsource(runner.MatchManager._start_live)
    assert "SystemRandom().shuffle" in source
