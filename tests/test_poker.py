import random

import pytest

from games.chess.live import LiveError
from games.poker import live as poker
from games.poker.cards import best_hand, hand_name, rank5


# ====================================================================== ارزیابی دست
@pytest.mark.parametrize(
    ("cards", "name"),
    [
        (["As", "Ks", "Qs", "Js", "Ts"], "استریت فلاش"),
        (["9c", "9d", "9h", "9s", "2c"], "چهارتایی"),
        (["Kc", "Kd", "Kh", "2s", "2c"], "فول هاوس"),
        (["Ah", "9h", "7h", "4h", "2h"], "فلاش"),
        (["5c", "4d", "3h", "2s", "Ac"], "استریت"),
        (["Qc", "Qd", "Qh", "7s", "2c"], "سه‌تایی"),
        (["Jc", "Jd", "4h", "4s", "2c"], "دو جفت"),
        (["Tc", "Td", "8h", "4s", "2c"], "یک جفت"),
        (["Ac", "Jd", "8h", "4s", "2c"], "کارت بالا"),
    ],
)
def test_hand_categories(cards, name):
    assert hand_name(rank5(cards)) == name


def test_hand_ordering_and_kickers():
    assert rank5(["Ac", "Ad", "Kh", "4s", "2c"]) > rank5(["Ac", "Ad", "Qh", "Js", "Tc"])
    assert rank5(["6c", "5d", "4h", "3s", "2c"]) > rank5(["5c", "4d", "3h", "2s", "Ac"])  # استریت ۶ از چرخ بالاتر
    assert rank5(["Kc", "Kd", "Kh", "2s", "2c"]) > rank5(["Qc", "Qd", "Qh", "As", "Ac"])
    score, five = best_hand(["As", "Ks", "2d", "Qs", "Js", "Ts", "3c"])
    assert hand_name(score) == "استریت فلاش" and sorted(five) == sorted(["As", "Ks", "Qs", "Js", "Ts"])


# ====================================================================== میز
def table(n=2, chips=None, now=0.0, hand_limit=poker.HAND_LIMIT):
    state = poker.new_state(list(range(1, n + 1)), now, seed="t", hand_limit=hand_limit)
    if chips:
        # ژتون دلخواه برای سناریوها: دست را از نو با این موجودی‌ها شروع می‌کنیم
        state["chips"] = list(chips)
        state["hand"] = 0
        state["dealer"] = -1
        poker._start_hand(state, now)
    return state


def uid(state, seat):
    return state["seats"][seat]


def total(state):
    return sum(state["chips"]) + sum(state["contrib"])


def test_heads_up_blinds_and_order():
    s = table(2)
    dealer = s["dealer"]
    other = 1 - dealer
    # در دونفره دیلر بلایند کوچک است و قبل از فلاپ اول حرف می‌زند
    assert s["bet"][dealer] == poker.SMALL_BLIND and s["bet"][other] == poker.SMALL_BLIND * 2
    assert s["to_act"] == dealer and s["street"] == "preflop"
    assert all(len(h) == 2 for h in s["hole"])
    poker.act(s, uid(s, dealer), "call", 0, 1)
    # بلایند بزرگ حق چک دارد
    assert s["to_act"] == other and poker.legal_actions(s, other)["check"]
    poker.act(s, uid(s, other), "check", 0, 2)
    assert s["street"] == "flop" and len(s["board"]) == 3
    # بعد از فلاپ اول نفر بعد از دیلر (بلایند بزرگ) حرف می‌زند
    assert s["to_act"] == other


def test_three_handed_blinds_and_first_to_act():
    s = table(3)
    d = s["dealer"]
    sb, bb = (d + 1) % 3, (d + 2) % 3
    assert s["bet"][sb] == 10 and s["bet"][bb] == 20 and s["to_act"] == d


def test_fold_gives_pot_to_last_player_and_pauses():
    s = table(2)
    d = s["dealer"]
    poker.act(s, uid(s, d), "fold", 0, 1)
    assert s["phase"] == "pause" and s["chips"][1 - d] == poker.START_CHIPS + 10
    assert s["result"]["winners"] == [{"seat": 1 - d, "amount": 30, "hand": ""}]
    assert total(s) == 2 * poker.START_CHIPS
    # بعد از وقفه دست بعد خودکار شروع می‌شود و دیلر عوض می‌شود
    assert poker.check_timeout(s, 1 + poker.PAUSE_SECONDS + 1)
    assert s["hand"] == 2 and s["dealer"] == 1 - d and s["phase"] == "betting"


def test_wrong_turn_and_illegal_actions_are_rejected():
    s = table(2)
    d = s["dealer"]
    with pytest.raises(LiveError):
        poker.act(s, uid(s, 1 - d), "call", 0, 1)
    with pytest.raises(LiveError):
        poker.act(s, uid(s, d), "check", 0, 1)  # باید call کند
    with pytest.raises(LiveError):
        poker.act(s, uid(s, d), "raise", 25, 1)  # کمتر از حداقل رِیز
    with pytest.raises(LiveError):
        poker.act(s, 999, "fold", 0, 1)
    poker.act(s, uid(s, d), "raise", 60, 1)
    assert s["current_bet"] == 60 and s["min_raise"] == 40
    assert poker.legal_actions(s, 1 - d)["raise_min"] == 100


def test_timeout_checks_or_folds():
    s = table(2, now=0)
    d = s["dealer"]
    assert not poker.check_timeout(s, 10)
    assert poker.check_timeout(s, poker.MOVE_SECONDS + 1)  # دیلر باید call می‌کرد: فولد
    assert s["phase"] == "pause" and s["last_action"]["timeout"] and s["folded"][d]


def test_all_in_runs_out_the_board_and_side_pot():
    # صندلی ۰ کوتاه است؛ دو نفر دیگر پات جانبی می‌سازند
    s = table(3, chips=[100, 1000, 1000])
    while s["phase"] == "betting" and s["street"] == "preflop":
        seat = s["to_act"]
        if s["chips"][seat] <= 100 and not s["allin"][seat]:
            poker.act(s, uid(s, seat), "allin", 0, 1)
        else:
            legal = poker.legal_actions(s, seat)
            if s["current_bet"] < 300 and legal["raise_min"]:
                poker.act(s, uid(s, seat), "raise", 300, 1)
            elif legal["call"]:
                poker.act(s, uid(s, seat), "call", 0, 1)
            else:
                poker.act(s, uid(s, seat), "check", 0, 1)
    pots = poker.side_pots(s) if s["phase"] == "betting" else None
    if pots:
        assert pots[0][1] == [0, 1, 2] and pots[0][0] == 300
    # بقیه‌ی دست را با چک تمام می‌کنیم
    while s["phase"] == "betting":
        seat = s["to_act"]
        legal = poker.legal_actions(s, seat)
        poker.act(s, uid(s, seat), "check" if legal["check"] else "call", 0, 2)
    assert s["phase"] == "pause" and total(s) == 2100
    assert sum(w["amount"] for w in s["result"]["winners"]) > 0


def test_all_in_runout_is_staged_and_the_last_hand_is_kept():
    s = table(2)
    d = s["dealer"]
    poker.act(s, uid(s, d), "allin", 0, 1)
    poker.act(s, uid(s, 1 - d), "call", 0, 2)
    # همه آل‌این: فلاپ، ترن و ریور بدون شرط‌بندی باز شدند و وقفه برای سه خیابان بلندتر است
    assert s["phase"] == "pause" and len(s["board"]) == 5 and s["result"]["runout"] == 0
    assert s["deadline"] == 2 + poker.PAUSE_SECONDS + 3 * poker.RUNOUT_SECONDS
    assert set(poker.view(s, uid(s, d), 3)["result"]["reveal"]) == {"0", "1"}
    board, winners = list(s["board"]), s["result"]["winners"]
    poker.check_timeout(s, s["deadline"] + 1)
    assert s["last_hand"]["hand"] == 1 and s["last_hand"]["board"] == board and s["last_hand"]["winners"] == winners
    assert poker.view(s, None, s["deadline"] or 0)["last_hand"]["runout"] == 0

    # آل‌این روی فلاپ: فقط ترن و ریور خودکار می‌آیند
    s = table(2)
    d = s["dealer"]
    poker.act(s, uid(s, d), "call", 0, 1)
    poker.act(s, uid(s, 1 - d), "check", 0, 2)
    assert s["street"] == "flop" and s["runout"] is None
    first = s["to_act"]
    poker.act(s, uid(s, first), "allin", 0, 3)
    poker.act(s, uid(s, 1 - first), "call", 0, 4)
    assert s["result"]["runout"] == 3 and s["deadline"] == 4 + poker.PAUSE_SECONDS + 2 * poker.RUNOUT_SECONDS

    # دستی که با فولد تمام شود وقفه‌ی معمولی دارد
    s = table(2)
    poker.act(s, uid(s, s["dealer"]), "fold", 0, 1)
    assert s["deadline"] == 1 + poker.PAUSE_SECONDS and "runout" not in s["result"]


def test_side_pots_are_shown_while_an_all_in_player_waits():
    s = table(3, chips=[100, 1000, 1000])
    assert s["dealer"] == 0 and s["to_act"] == 0
    poker.act(s, uid(s, 0), "allin", 0, 1)
    poker.act(s, uid(s, 1), "call", 0, 2)
    poker.act(s, uid(s, 2), "call", 0, 3)
    assert s["street"] == "flop" and poker.view(s, None, 3)["pots"] == []  # همه به یک اندازه گذاشته‌اند
    poker.act(s, uid(s, 1), "raise", 200, 4)
    assert poker.view(s, None, 4)["pots"] == []  # شرطی که هنوز کال نشده پات جانبی نیست
    poker.act(s, uid(s, 2), "call", 0, 5)
    view = poker.view(s, None, 5)
    assert s["street"] == "turn" and view["pots"] == [300, 400] and view["pot"] == 700
    assert [e["kind"] for e in view["log"]] == ["sb", "bb", "allin", "call", "call", "raise", "call"]


def test_short_all_in_does_not_reopen_the_betting():
    """قاعده‌ی رِیز ناقص (TDA): آل‌اینِ کمتر از یک رِیز کامل، به کسی که قبلاً حرکت کرده فقط حق کال/فولد می‌دهد."""
    s = table(3, chips=[1000, 1000, 150])
    assert s["dealer"] == 0 and s["to_act"] == 0  # سه‌نفره: دیلر اول حرف می‌زند؛ ۱ بلایند کوچک، ۲ بلایند بزرگ
    poker.act(s, uid(s, 0), "raise", 100, 1)
    poker.act(s, uid(s, 1), "call", 0, 2)
    legal = poker.legal_actions(s, 2)
    assert legal["raise_min"] == 0 and legal["allin"] == 130  # کمتر از حداقل رِیز (۱۸۰)، ولی آل‌این مجاز
    poker.act(s, uid(s, 2), "allin", 0, 3)
    assert s["current_bet"] == 150 and s["min_raise"] == 80  # رِیز ناقص حداقل رِیز را عوض نمی‌کند
    legal = poker.legal_actions(s, 0)
    assert legal == {"fold": True, "check": False, "call": 50, "raise_min": 0, "raise_max": 0, "allin": 0}
    for kind, amount in (("raise", 400), ("allin", 0)):
        with pytest.raises(LiveError, match="illegal_move"):
            poker.act(s, uid(s, 0), kind, amount, 4)
    poker.act(s, uid(s, 0), "call", 0, 4)
    assert poker.legal_actions(s, 1)["raise_min"] == 0
    poker.act(s, uid(s, 1), "call", 0, 5)
    assert s["street"] == "flop" and s["log"][-1]["kind"] == "call"
    assert [e["kind"] for e in s["log"]] == ["sb", "bb", "raise", "call", "allin", "call", "call"]


def test_short_all_ins_that_add_up_to_a_full_raise_reopen_the_betting():
    s = table(4, chips=[1000, 150, 210, 1000])
    assert s["to_act"] == 3  # چهارنفره: نفر بعد از بلایند بزرگ
    poker.act(s, uid(s, 3), "raise", 100, 1)  # رِیز کامل ۸۰ تایی
    poker.act(s, uid(s, 0), "call", 0, 2)
    poker.act(s, uid(s, 1), "allin", 0, 3)  # تا ۱۵۰: +۵۰ ناقص
    poker.act(s, uid(s, 2), "allin", 0, 4)  # تا ۲۱۰: +۶۰ ناقص، ولی روی هم ۱۱۰ ≥ ۸۰
    assert s["current_bet"] == 210 and s["to_act"] == 3
    assert poker.legal_actions(s, 3)["raise_min"] == 290
    poker.act(s, uid(s, 3), "raise", 400, 5)
    assert poker.legal_actions(s, 0)["raise_min"] == 590  # رِیز کامل تازه برای همه باز است


def test_hand_descriptions_like_a_real_table():
    from games.poker.cards import describe, describe_cards

    assert describe(rank5(["Ah", "Ad", "Kc", "7s", "2d"])) == "جفت آس"
    assert describe(rank5(["Kh", "Kd", "7c", "7s", "2d"])) == "دو جفت شاه و ۷"
    assert describe(rank5(["8h", "8d", "8c", "Ks", "Kd"])) == "فول هاوس: سه ۸ و دو شاه"
    assert describe(rank5(["As", "Ks", "Qs", "Js", "Ts"])) == "رویال فلاش"
    assert describe(rank5(["5c", "4d", "3h", "2s", "Ac"])) == "استریت تا ۵"
    assert describe_cards(["Qs", "Qd"]) == "جفت بی‌بی" and describe_cards(["Ks", "As"]) == "آس و شاه هم‌خال"
    assert describe_cards(["Jc", "Td"]) == "سرباز و ۱۰" and describe_cards([]) == ""
    s = table(2)
    me = poker.view(s, uid(s, 0), 1)
    assert me["my_hand"] == describe_cards(s["hole"][0]) and me["current_bet"] == 20 and me["left_ms"] > 0
    assert [e["kind"] for e in me["log"]] == ["sb", "bb"] and poker.view(s, None, 1)["my_hand"] == ""


def test_side_pots_math():
    s = table(3)
    s["in_hand"] = [True, True, True]
    s["folded"] = [False, False, True]
    s["contrib"] = [50, 200, 120]
    assert poker.side_pots(s) == [(150, [0, 1]), (220, [1])]


def test_game_ends_after_hand_limit_and_ranks_by_chips():
    s = table(2, hand_limit=2)
    for _ in range(2):
        d = s["dealer"]
        poker.act(s, uid(s, d), "fold", 0, 1)
        poker.check_timeout(s, 10**6 * s["hand"])
    assert s["over"]["reason"] == "limit"
    assert sorted(score for _, score in poker.standings(s)) == sorted(s["chips"])


def test_leaving_a_cash_table_keeps_the_chips_and_ends_heads_up():
    s = table(2)
    d = s["dealer"]
    # دونفره: دیلر بلایند کوچک است؛ نفر دیگر با بلایند بزرگ (۲۰) بلند می‌شود و فقط همان را می‌بازد
    poker.resign(s, uid(s, 1 - d), 1)
    assert s["over"] is not None and s["over"]["winner"] == uid(s, d)
    final = dict(poker.standings(s))
    assert final == {uid(s, 1 - d): poker.START_CHIPS - 20, uid(s, d): poker.START_CHIPS + 20}
    assert sum(final.values()) == 2 * poker.START_CHIPS


def test_leaving_a_tournament_table_scores_zero():
    s = poker.new_state([1, 2], 0, seed="t", cash=False)
    d = s["dealer"]
    poker.resign(s, uid(s, 1 - d), 1)
    assert s["over"]["winner"] == uid(s, d) and dict(poker.standings(s))[uid(s, 1 - d)] == 0


def test_cash_table_keeps_the_blinds_and_a_tournament_raises_them():
    cash = poker.new_state([1, 2, 3], 0, seed="b")
    tour = poker.new_state([1, 2, 3], 0, seed="b", cash=False)
    assert cash["cash"] and cash["hand_limit"] == poker.CASH_HAND_LIMIT and tour["hand_limit"] == poker.HAND_LIMIT
    for s in (cash, tour):
        for _ in range(poker.BLIND_UP_HANDS):
            s["phase"], s["deadline"] = "pause", 0
            poker.check_timeout(s, 1)
    assert (cash["sb"], cash["bb"]) == (poker.SMALL_BLIND, poker.SMALL_BLIND * 2)
    assert (tour["sb"], tour["bb"]) == (poker.SMALL_BLIND * 2, poker.SMALL_BLIND * 4)
    view = poker.view(cash, 1, 1)
    assert view["cash"] is True and view["start_chips"] == poker.START_CHIPS


def test_view_hides_other_players_cards():
    s = table(3)
    view = poker.view(s, uid(s, 0), 1)
    assert view["seats"][0]["cards"] == s["hole"][0]
    assert view["seats"][1]["cards"] == ["", ""] and view["you"] == 0
    spectator = poker.view(s, None, 1)
    assert all(seat["cards"] in (["", ""], []) for seat in spectator["seats"])


@pytest.mark.parametrize("seed", range(40))
def test_random_play_never_breaks_chip_accounting(seed):
    rng = random.Random(seed)
    n = rng.randint(2, 6)
    s = poker.new_state(list(range(1, n + 1)), 0, seed=f"r{seed}", hand_limit=6)
    now = 0.0
    for _ in range(2000):
        if s["over"]:
            break
        now += 1
        assert total(s) == n * poker.START_CHIPS
        assert all(c >= 0 for c in s["chips"])
        if s["phase"] == "pause" or rng.random() < 0.03:
            poker.check_timeout(s, now + 10**4)
            now += 10**4
            continue
        seat = s["to_act"]
        legal = poker.legal_actions(s, seat)
        options = ["fold"] + (["allin"] if legal["allin"] else [])
        if legal["check"]:
            options += ["check"] * 3
        if legal["call"]:
            options += ["call"] * 3
        if legal["raise_min"]:
            options += ["raise"] * 2
        kind = rng.choice(options)
        amount = rng.randint(legal["raise_min"], legal["raise_max"]) if kind == "raise" else 0
        poker.act(s, uid(s, seat), kind, amount, now)
    assert s["over"] is not None
    assert sum(score for _, score in poker.standings(s)) == n * poker.START_CHIPS


# ====================================================================== پوکر داخل گروه (پلاگین)
async def test_group_poker_plays_hands_and_ranks_by_chips():
    from games.plugins.poker import PokerGame

    from .fakes import FakeContext

    ctx = FakeContext(n_players=3)
    game = PokerGame(ctx)
    await game.start()
    assert "پوکر" in ctx.last_text and "▶️" in ctx.last_text
    # کارت‌ها فقط برای خود بازیکن و در پنجره‌ی هشدار
    cb = ctx.cb(0, "c")
    await game.on_callback(cb)
    (text, alert), = cb.answers
    assert alert and "کارت‌های تو" in text
    for card in game.state["hole"][poker.seat_of(game.state, ctx.players[0].user_id)]:
        assert card not in ctx.all_text()
    # کسی که نوبتش نیست نمی‌تواند حرکت کند
    by_uid = {p.user_id: i for i, p in enumerate(ctx.players)}
    to_act = by_uid[game.state["seats"][game.state["to_act"]]]
    wrong = ctx.cb((to_act + 1) % 3, "a:fold")
    await game.on_callback(wrong)
    assert wrong.answers[0][0] == "الان نوبت تو نیست."
    # چند دست با کال/چک تا پایان بازی (یا تایمرها)
    for _ in range(400):
        if ctx.ended:
            break
        s = game.state
        if s["phase"] != "betting":
            await ctx.advance(poker.PAUSE_SECONDS + 1)
            continue
        idx = by_uid[s["seats"][s["to_act"]]]
        legal = poker.legal_actions(s, s["to_act"])
        await game.on_callback(ctx.cb(idx, "a:check" if legal["check"] else "a:call"))
    # یک نفر همه‌ی ژتون‌ها را با آل‌این می‌برد یا سقف دست‌ها تمام می‌شود؛ در هر دو حالت بازی تمام می‌شود
    while not ctx.ended:
        await ctx.advance(poker.MOVE_SECONDS + 1)
    standings = await game.finish()
    assert sum(s.score for s in standings) == 3 * poker.START_CHIPS
    assert "بازی تمام شد" in ctx.edits[-1]["text"]


async def test_group_poker_timeout_folds_idle_player():
    from games.plugins.poker import PokerGame

    from .fakes import FakeContext

    ctx = FakeContext(n_players=2)
    game = PokerGame(ctx)
    await game.start()
    await ctx.advance(poker.MOVE_SECONDS + 1)
    assert game.state["last_action"] is None or game.state["phase"] in ("pause", "betting")
    assert "وقتش تمام شد" in ctx.all_text() or game.state["hand"] >= 2


# ====================================================================== مینی‌اپ و ربات (پوکر زنده)
@pytest.fixture
def fresh_redis():
    from core.redis import reset_clients

    reset_clients()
    yield
    reset_clients()


@pytest.mark.django_db
def test_poker_page_and_api_hide_other_cards(client, group, make_user):
    import time

    from django.utils import timezone

    from arcade import board
    from games.models import Match, MatchStatus

    from .test_live_chess import post

    a, b, c = make_user(first_name="آ"), make_user(first_name="ب"), make_user(first_name="پ")
    match = Match.objects.create(
        group=group, creator=a, game_type="poker", status=MatchStatus.RUNNING,
        min_players=2, max_players=6, join_deadline=timezone.now(),
    )  # fmt: skip
    board.start(match.pk, board.new_state("poker", [a.pk, b.pk, c.pk], time.time(), seed="api"))
    page = client.get(f"/arcade/board/{match.token}/").content.decode()
    assert "poker.js" in page and 'id="felt"' in page

    _, data = post(client, "board/state", a, match_token=match.token)
    view = data["state"]
    assert view["game"] == "poker" and view["players"] == {"s0": "آ", "s1": "ب", "s2": "پ"}
    me = view["seats"][view["you"]]
    assert len(me["cards"]) == 2 and all(me["cards"])
    assert all(s["cards"] in (["", ""], []) for s in view["seats"] if s["seat"] != view["you"])

    state = Match.objects.get(pk=match.pk).state["board"]
    actor = [a, b, c][state["to_act"]]
    other = [a, b, c][(state["to_act"] + 1) % 3]
    assert post(client, "board/action", other, match_token=match.token, action="fold")[1]["error"] == "not_your_turn"
    assert post(client, "board/action", actor, match_token=match.token, action="raise", amount=5)[1]["error"] == "illegal_move"
    status, data = post(client, "board/action", actor, match_token=match.token, action="raise", amount=60)
    assert status == 200 and data["state"]["last_action"]["kind"] == "raise"
    # حرکت پوکر در بازی دیگر و حرکت خانه‌ای در پوکر رد می‌شود
    assert post(client, "board/move", other, match_token=match.token, src=1)[0] == 409


@pytest.mark.django_db(transaction=True)
async def test_bot_runs_group_poker_through_the_mini_app_and_pays_by_chips(fresh_redis):
    import time

    from asgiref.sync import sync_to_async

    from arcade import board
    from bot.runner import MatchManager
    from core.models import TelegramGroup, TelegramUser
    from games.catalog import get_info
    from games.models import Match, MatchStatus
    from wallet.models import TxType
    from wallet.services import apply_transaction

    from .fake_telegram import FakeApplication

    @sync_to_async
    def world():
        group = TelegramGroup.objects.create(chat_id=-100777, title="پوکر")
        users = [TelegramUser.objects.create(tg_id=9100 + i, first_name=f"پوکرباز{i}", started_bot=True) for i in range(3)]
        for u in users:
            apply_transaction(u, 500, TxType.ADMIN_GRANT, f"poker-test:{u.pk}")
        return group, users

    app = FakeApplication()
    group, users = await world()
    manager = MatchManager(app)
    active = await manager.create_lobby(group, users[0], get_info("poker"), fee=100, split=[60, 30, 10], join_seconds=60, options={})
    for user in users:
        await manager.join(active, user)
    await app.job_queue.fire("lobby_close")
    opening = app.bot.sent[-1]
    assert active.game is None and "پوکر" in opening["text"] and "▶️" in opening["text"]
    # کارت هیچ‌کس در پیام گروه نیست
    state = (await sync_to_async(Match.objects.get)(pk=active.match_id)).state["board"]
    from games.poker.cards import label

    for hole in state["hole"]:
        assert not any(label(c) in opening["text"] for c in hole)

    # همه به‌جز یک نفر فولد می‌کنند تا دست‌ها سریع تمام شود؛ بعد ترک میز تا بازی تمام شود
    def fold_round(s):
        from games.poker import live as poker

        if s["phase"] == "betting":
            poker.act(s, s["seats"][s["to_act"]], "fold", 0, time.time())

    for _ in range(3):
        await sync_to_async(board.update)(active.match_id, fold_round)
    await manager.poll_live(active)
    from games.poker import live as poker

    s = (await sync_to_async(Match.objects.get)(pk=active.match_id)).state["board"]
    leavers = [uid for uid in s["seats"] if uid != s["seats"][0]]
    for uid in leavers:
        await sync_to_async(board.update)(active.match_id, lambda st, uid=uid: poker.resign(st, uid, time.time()))
    await manager.poll_live(active)
    assert active.phase == "done"
    match = await sync_to_async(Match.objects.get)(pk=active.match_id)
    assert match.status == MatchStatus.FINISHED
    # میز نقدی: کسی که بلند شده ژتون‌هایش را نگه داشته و هر کس به اندازه‌ی ژتونش از ۳۰۰ سکه می‌برد
    from games.engine.payout import proportional_payouts
    from wallet.models import CoinTransaction

    final = (await sync_to_async(Match.objects.get)(pk=active.match_id)).state["board"]
    chips = dict(poker.standings(final))
    assert sum(chips.values()) == 3 * poker.START_CHIPS and all(chips.values())
    prizes = await sync_to_async(lambda: dict(CoinTransaction.objects.filter(type=TxType.PRIZE).values_list("user_id", "amount")))()
    assert prizes == {uid: amount for uid, amount in proportional_payouts(300, chips).items() if amount}
    assert sum(prizes.values()) == 300
    assert "پایان پوکر" in app.bot.sent[-1]["text"]


# ====================================================================== میز نقدی در مینی‌اپ: ارزش سکه، گفت‌وگو، شرط
@pytest.fixture
def cash_table(db, group, make_user, fresh_redis):
    import time

    from django.utils import timezone

    from arcade import board
    from games.engine import services
    from games.models import Match, MatchPlayer, MatchStatus

    a, b, c = make_user(first_name="آرش"), make_user(first_name="بهار"), make_user(first_name="پویا")
    match = Match.objects.create(
        group=group, creator=a, game_type="poker", status=MatchStatus.RUNNING, entry_fee=100, pot=300,
        min_players=2, max_players=6, join_deadline=timezone.now(), options=services.match_options("poker"),
    )  # fmt: skip
    for user in (a, b, c):
        MatchPlayer.objects.create(match=match, user=user, paid_fee=100)
    board.start(match.pk, board.new_state("poker", [a.pk, b.pk, c.pk], time.time(), seed="cash"))
    return match, (a, b, c)


@pytest.mark.django_db
def test_cash_table_reports_the_coin_value_of_the_chips(client, cash_table):
    from .test_live_chess import post

    match, (a, b, c) = cash_table
    _, data = post(client, "board/state", a, match_token=match.token)
    view = data["state"]
    assert view["cash"] is True and view["payout"] == "chips" and view["pot_coins"] == 300
    assert view["start_chips"] == poker.START_CHIPS and "prizes" not in view
    # ارزش هر ژتون = ۳۰۰ سکه ÷ ۳۰۰۰ ژتون؛ کلاینت ارزش هر پشته را با همین حساب می‌کند
    assert view["pot_coins"] / (len(view["seats"]) * view["start_chips"]) == 0.1


@pytest.mark.django_db
def test_board_chat_reaches_the_table_through_the_state_poll(client, cash_table, make_user):
    from .test_live_chess import post

    match, (a, b, c) = cash_table
    watcher = make_user(first_name="تماشاچی")
    _, first = post(client, "board/state", b, match_token=match.token, chat_after=0)
    assert first["chat"] == [] and first["can_chat"] is True and first["quick"]
    version = first["state"]["version"]

    status, sent = post(client, "board/chat", a, match_token=match.token, text="  سلام   بچه‌ها  ", chat_after=0)
    assert status == 200 and sent["chat"][-1]["text"] == "سلام بچه‌ها" and sent["chat"][-1]["mine"] is True
    message_id = sent["chat"][-1]["id"]
    seat = seat_index(match, a)
    assert sent["chat"][-1]["side"] == f"s{seat}" and "uid" not in sent["chat"][-1]

    # پرسش سریع «چیزی عوض شده؟» (بدون تغییر بازی) پیام تازه را هم می‌آورد، فقط یک بار
    _, poll = post(client, "board/state", b, match_token=match.token, version=version, chat_after=0)
    assert poll["changed"] is False and [m["text"] for m in poll["chat"]] == ["سلام بچه‌ها"] and poll["chat"][0]["mine"] is False
    _, again = post(client, "board/state", b, match_token=match.token, version=version, chat_after=message_id)
    assert again["changed"] is False and "chat" not in again
    # صفحه‌ای که گفت‌وگو نمی‌خواهد (شطرنج قدیمی) همان جواب کوتاه قبلی را می‌گیرد
    _, plain = post(client, "board/state", b, match_token=match.token, version=version)
    assert "chat" not in plain

    # تماشاچی می‌خواند ولی نمی‌نویسد؛ لینک و آیدی رد می‌شود
    _, seen = post(client, "board/state", watcher, match_token=match.token, chat_after=0)
    assert seen["can_chat"] is False and [m["text"] for m in seen["chat"]] == ["سلام بچه‌ها"]
    assert post(client, "board/chat", watcher, match_token=match.token, text="سلام")[1]["error"] == "not_a_player"
    assert post(client, "board/chat", b, match_token=match.token, text="بیا @spam_channel")[1]["error"] == "chat_no_links"
    assert post(client, "board/chat", b, match_token=match.token, text="   ")[1]["error"] == "chat_empty"


def seat_index(match, user):
    from games.models import Match

    return Match.objects.get(pk=match.pk).state["board"]["seats"].index(user.pk)


@pytest.mark.django_db
def test_leaving_keeps_the_chips_and_the_finished_table_reports_real_prizes(client, cash_table):
    from arcade import board
    from games.engine import services
    from games.engine.payout import Standing, proportional_payouts
    from games.models import Match

    from .test_live_chess import post

    match, (a, b, c) = cash_table
    assert post(client, "board/action", c, match_token=match.token, action="resign")[0] == 200
    assert post(client, "board/action", b, match_token=match.token, action="resign")[0] == 200
    state = Match.objects.get(pk=match.pk).state["board"]
    assert state["over"] is not None
    chips = dict(poker.standings(state))
    assert chips[c.pk] > 0 and chips[b.pk] > 0 and sum(chips.values()) == 3 * poker.START_CHIPS
    services.finish_match(match.pk, [Standing(uid, score, None) for uid, score in board.standings(state)])
    _, data = post(client, "board/state", b, match_token=match.token)
    prizes = data["state"]["prizes"]
    by_side = {f"s{i}": uid for i, uid in enumerate(state["seats"])}
    assert sum(prizes.values()) == 300
    assert {by_side[side]: coins for side, coins in prizes.items()} == proportional_payouts(300, chips)


def test_first_bet_after_the_flop_is_a_bet_not_a_raise():
    from bot.render import poker_text

    s = table(2)
    # قبل از فلاپ: کال و چک
    d = s["dealer"]
    poker.act(s, uid(s, d), "call", 0, 1)
    poker.act(s, uid(s, 1 - d), "check", 0, 1)
    assert s["street"] == "flop" and s["current_bet"] == 0
    first = s["to_act"]
    poker.act(s, uid(s, first), "raise", 40, 1)
    assert s["last_action"]["open"] is True and s["last_action"]["to"] == 40
    names = {uid(s, 0): "آرش", uid(s, 1): "بهار"}
    assert "شرط ۴۰" in poker_text(s, names)
    poker.act(s, uid(s, 1 - first), "raise", 120, 1)
    assert "open" not in s["last_action"] and "رِیز ۱۲۰" in poker_text(s, names)


def test_cash_table_end_text_says_coins_follow_the_chips():
    from bot.render import poker_text

    s = table(2)
    poker.resign(s, uid(s, 0), 1)
    assert s["over"] and "هر کس به اندازه‌ی ژتون‌هایش سکه می‌برد" in poker_text(s, {1: "آ", 2: "ب"})
    tour = poker.new_state([1, 2], 0, seed="t", cash=False)
    poker.resign(tour, 1, 1)
    assert "رتبه‌ها بر اساس ژتون نهایی است" in poker_text(tour, {1: "آ", 2: "ب"})
