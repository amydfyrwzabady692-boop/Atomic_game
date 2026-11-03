"""روی کارت‌های پوکر و حکم مثل کارت واقعی است (``arcade/static/arcade/board/cards.js``): هر کارت عددی دقیقاً به تعداد
عددش نقش خال دارد (هفت خشت هفت خشت)، آس یک نقش بزرگ، و شاه و بی‌بی و سرباز تصویر خودشان را. کد JS با Node اجرا
می‌شود؛ اگر Node نصب نباشد این تست‌ها skip می‌شوند (در CI همیشه Node هست)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CARDS_JS = ROOT / "arcade" / "static" / "arcade" / "board" / "cards.js"
SUIT_PATH_START = {"h": "M50 92C50 92", "d": "M50 2C61 21", "s": "M50 3C50 3", "c": "M50 6A20 20"}

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node نصب نیست")


@pytest.fixture(scope="module")
def faces() -> dict:
    script = (
        "global.window = {};"
        f"require({json.dumps(str(CARDS_JS))});"
        "const out = {};"
        "for (const s of 'shdc') for (const r of 'A23456789TJQK') out[r + s] = window.CardFaces.svg(r + s);"
        "out.url = window.CardFaces.face('7d');"
        "out.label = window.CardFaces.label('Qh');"
        "console.log(JSON.stringify(out));"
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60, check=True)
    return json.loads(result.stdout)


def pips(svg: str, suit: str) -> int:
    """تعداد نقش‌های خال در بدنه‌ی کارت (بدون دو نقش کوچک گوشه‌ها)."""
    return svg.count(SUIT_PATH_START[suit]) - 2


@pytest.mark.parametrize("suit", "shdc")
def test_number_cards_have_as_many_pips_as_their_rank(faces, suit):
    for rank, count in (("A", 1), ("2", 2), ("3", 3), ("4", 4), ("5", 5), ("6", 6), ("7", 7), ("8", 8), ("9", 9), ("T", 10)):
        assert pips(faces[rank + suit], suit) == count, rank + suit


def test_seven_of_diamonds_really_has_seven_diamonds(faces):
    assert pips(faces["7d"], "d") == 7 and faces["url"].startswith("data:image/svg+xml")


@pytest.mark.parametrize("suit", "shdc")
def test_court_cards_show_king_queen_and_jack(faces, suit):
    king, queen, jack = faces["K" + suit], faces["Q" + suit], faces["J" + suit]
    # همه دوسرند (نیمه‌ی پایین همان تصویر برعکس) و برچسب گوشه‌ی درست دارند
    for svg, letter in ((king, "K"), (queen, "Q"), (jack, "J")):
        assert 'rotate(180 50 70)' in svg and f">{letter}</text>" in svg
    # شاه: تاج و ریش و شمشیر؛ بی‌بی: گل و گردنبند؛ سرباز: کلاه پردار و نیزه
    assert "#c7ced9" in king and "M42.5 35.5" in king  # تیغه‌ی شمشیر و ریش
    assert "#e8486a" in queen and "stroke-dasharray" in queen  # گل و گردنبند
    assert "#f7f7f7" in jack and "#8a5a2b" in jack  # پر کلاه و دسته‌ی نیزه
    assert len({king, queen, jack}) == 3


def test_labels_are_persian(faces):
    assert faces["label"] == "بی‌بی دل"
