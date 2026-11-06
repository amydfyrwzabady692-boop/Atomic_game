"""حریف تصادفی برای همه‌ی بازی‌ها: میزهای چندنفره (حکم چهارنفره و سه‌نفره) با پر شدن میز شروع می‌شوند، صندلی‌ها
تصادفی‌اند، بازی‌های دونفره‌ی تازه (حکم دونفره، چهاربرگ، انفجار) مثل دوئل کار می‌کنند و زمان ثبت‌نام لابی ۱:۳۰ است."""

import random
import time

import pytest

from games import duels
from games.hokm import live as hokm
from games.models import DuelTicket, Match, MatchStatus


@pytest.fixture
def fresh_redis():
    from core.redis import reset_clients

    reset_clients()
    yield
    reset_clients()


def test_every_board_and_card_game_is_offered():
    assert duels.duel_games()[:9] == list(duels.BOARD_GAMES)
    assert {"hokm", "hokm3", "hokm2", "chaharbarg", "crash"} <= set(duels.duel_games())


def test_lobby_join_time_is_ninety_seconds(settings):
    from bot.handlers.flow import steps_for
    from games.catalog import get_info

    assert settings.LOBBY_JOIN_SECONDS == 90
    assert "join" not in steps_for(get_info("quiz"))


@pytest.mark.django_db
def test_four_player_hokm_table_fills_and_starts_without_negotiation(make_user, fresh_redis):
    from wallet.management.commands.audit_wallets import find_mismatches, match_problems

    users = [make_user(500) for _ in range(4)]
    first = duels.search(users[0], "hokm", 100)
    assert isinstance(first, DuelTicket) and first.status == DuelTicket.Status.SEARCHING
    duels.search(users[1], "hokm", None)  # «فرقی نمی‌کند» به میز ۱۰۰ سکه‌ای می‌پیوندد
    duels.search(users[2], "hokm", 100)
    assert Match.objects.filter(game_type="hokm").count() == 0  # هنوز سه نفر
    last = duels.search(users[3], "hokm", 100)
    assert last.status == DuelTicket.Status.MATCHED and last.match is not None
    match = last.match
    assert match.status == MatchStatus.RUNNING and match.group is None and match.options["table"] is True
    assert match.pot == 400 and match.options["variant"] == "3"
    state = Match.objects.get(pk=match.pk).state["board"]
    assert sorted(state["seats"]) == sorted(u.pk for u in users) and state["target"] == 3
    assert set(DuelTicket.objects.filter(match=match).values_list("status", flat=True)) == {DuelTicket.Status.MATCHED}
    # کسی که سر میز است نمی‌تواند هم‌زمان جستجوی تازه بزند
    with pytest.raises(duels.DuelError) as err:
        duels.search(users[0], "chess", 0)
    assert err.value.code == "already_in_duel"
    assert duels.finish_table(match) is None  # هنوز تمام نشده

    rng = random.Random(1)
    from arcade import board

    def step(s):
        now = time.time()
        if s["phase"] == "pause":
            s["deadline"] = now - 1
            hokm.check_timeout(s, now)
        elif s["phase"] == "trump":
            hokm.choose_trump(s, s["seats"][s["turn"]], rng.choice("shdc"), now)
        else:
            hokm.play(s, s["seats"][s["turn"]], rng.choice(hokm.legal_cards(s, s["turn"])), now)

    for _ in range(4000):
        if Match.objects.get(pk=match.pk).state["board"]["over"]:
            break
        board.update(match.pk, step)
    result = duels.finish_table(Match.objects.get(pk=match.pk))
    assert result is not None and sorted(r.prize for r in result.players) == [0, 0, 200, 200]
    assert match_problems() == [] and find_mismatches() == []
    assert not duels.in_table(users[0].pk)


@pytest.mark.django_db
def test_table_needs_matching_stakes_and_enough_coins(make_user, fresh_redis):
    rich = [make_user(500) for _ in range(2)]
    poor = make_user(10)
    duels.search(rich[0], "hokm3", 100)
    duels.search(poor, "hokm3", None)  # سکه‌ی کافی برای میز ۱۰۰ ندارد؛ منتظر می‌ماند
    ticket = duels.search(rich[1], "hokm3", 50)  # مقدار دیگر: میز جدا
    assert ticket.status == DuelTicket.Status.SEARCHING and not Match.objects.filter(game_type="hokm3").exists()
    third = make_user(500)
    ticket = duels.search(third, "hokm3", 50)
    assert ticket.status == DuelTicket.Status.SEARCHING  # فقط دو نفر با ۵۰ (نفر بی‌پول جزو میز ۵۰ هم نمی‌شود)
    fourth = make_user(500)
    ticket = duels.search(fourth, "hokm3", 50)
    assert ticket.match is not None and ticket.match.pot == 150 and ticket.match.max_players == 3


@pytest.mark.django_db
def test_new_two_player_games_run_as_duels(make_user, fresh_redis):
    for game in ("hokm2", "chaharbarg", "crash"):
        a, b = make_user(500), make_user(500)
        duels.search(a, game, 0)
        duel = duels.search(b, game, 0)
        duel.refresh_from_db()
        assert duel.status == duel.Status.PLAYING, game
        state = Match.objects.get(pk=duel.match_id).state["board"]
        assert state["game"] == game
        if game == "hokm2":
            assert state["target"] == 3
        if game == "crash":
            assert Match.objects.get(pk=duel.match_id).options["house_percent"] >= 0


@pytest.mark.django_db
def test_hub_shows_the_table_to_every_player(client, make_user, fresh_redis):
    from .test_hub_api import post

    users = [make_user(500) for _ in range(3)]
    for u in users:
        duels.search(u, "hokm3", 0)
    _, data = post(client, "duel/state", users[0])
    state = data["state"]
    assert state["mode"] == "playing" and state["table"] is True and state["players"] == 3
    assert state["url"].startswith("/arcade/board/") and state["game"]["key"] == "hokm3"
    games = {g["key"]: g for g in data["games"]}
    assert games["hokm"]["table"] == 4 and games["hokm3"]["table"] == 3


@pytest.mark.django_db(transaction=True)
async def test_bot_announces_the_table_and_the_result(make_user, fresh_redis, settings):
    from asgiref.sync import sync_to_async

    from bot.duels import DuelRunner

    from .fake_telegram import FakeApplication

    settings.MINIAPP_BASE_URL = "https://arcade.example"
    users = [await sync_to_async(make_user)(500) for _ in range(3)]
    for u in users:
        await sync_to_async(duels.search)(u, "hokm3", 0)
    app = FakeApplication()
    runner = DuelRunner(app)
    await runner.tick()
    started = [m for m in app.bot.sent if "میز تصادفی پیدا شد" in m["text"]]
    assert {m["chat_id"] for m in started} == {u.tg_id for u in users}
    await runner.tick()
    assert len([m for m in app.bot.sent if "میز تصادفی پیدا شد" in m["text"]]) == 3  # فقط یک بار
    match = await sync_to_async(Match.objects.get)(game_type="hokm3")
    from arcade import board

    def leave(s):
        hokm.resign(s, s["seats"][0])

    await sync_to_async(board.update)(match.pk, leave)
    await runner.tick()
    ends = [m for m in app.bot.sent if "میز تصادفی)" in m["text"]]
    assert {m["chat_id"] for m in ends} == {u.tg_id for u in users}
