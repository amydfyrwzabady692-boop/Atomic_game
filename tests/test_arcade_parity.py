"""تطابق شبیه‌ساز پایتون با core.js هر بازی.

- پایتون: نتیجه‌ی شبیه‌سازی هر لاگ ثابت باید برابر مقدار ذخیره‌شده در fixture باشد.
- JS: همان fixtureها با Node روی core.js اجرا می‌شوند (``arcade/jstests/parity.js``).
  اگر Node نصب نباشد این بخش skip می‌شود (در CI همیشه اجرا می‌شود).
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from arcade.sim import all_simulators
from arcade.sim.autoplay import build_cases

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "arcade" / "fixtures" / "parity"
STATIC = ROOT / "arcade" / "static" / "arcade"
KEYS = sorted(all_simulators())


def load_cases(key: str) -> list[dict]:
    return json.loads((FIXTURES / f"{key}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("key", KEYS)
def test_every_game_has_core_js_renderer_and_fixtures(key):
    assert (STATIC / key / "core.js").is_file(), "core.js ندارد"
    assert (STATIC / key / "render.js").is_file(), "render.js ندارد"
    cases = load_cases(key)
    assert len(cases) >= 5
    # حداقل یک لاگ باید واقعاً در بازی پیش رفته باشد
    assert max(c["expected"]["score"] for c in cases) > 0
    assert any(len(c["inputs"]) >= 5 for c in cases)


@pytest.mark.parametrize("key", KEYS)
def test_renderer_follows_the_fast_drawing_rules(key):
    """رندر هر بازی پس‌زمینه‌ی خودش را از اسپرایت کش‌شده می‌کشد و سایه‌ی زنده‌ی بوم (که روی گوشی
    فریم می‌اندازد) در هیچ فریمی استفاده نمی‌شود."""
    source = (STATIC / key / "render.js").read_text(encoding="utf-8")
    assert f'registerRenderer("{key}"' in source
    assert "ownBackground: true" in source
    assert "env.scene(" in source or "env.sprite(" in source
    assert "env.glow(" not in source and "shadowBlur" not in source


def test_app_page_loads_the_art_kit_before_the_shell():
    template = (ROOT / "arcade" / "templates" / "arcade" / "app.html").read_text(encoding="utf-8")
    assert (STATIC / "common" / "art.js").is_file()
    assert template.index("common/art.js") < template.index("common/icons.js") < template.index("common/shell.js")


@pytest.mark.parametrize("key", KEYS)
def test_every_game_has_a_drawn_menu_icon(key):
    """منو و صفحه‌ی شروع برای هر بازی یک نماد تصویری دارند (نه فقط ایموجی)."""
    icons = (STATIC / "common" / "icons.js").read_text(encoding="utf-8")
    assert f"      {key}: function (c) {{" in icons


@pytest.mark.parametrize("key", KEYS)
def test_python_simulator_matches_fixtures(key):
    sim = all_simulators()[key]
    for i, case in enumerate(load_cases(key)):
        assert sim.validate_inputs(case["inputs"], case["duration_ms"]) is None, f"case {i}"
        result = sim.simulate(case["seed"], case["inputs"], case["duration_ms"], case["options"])
        assert result.as_dict() == case["expected"], f"{key} case {i} ({case['kind']})"


@pytest.mark.parametrize("key", KEYS)
def test_fixture_generation_is_deterministic(key):
    """همان ورودی‌ها باید همیشه همان fixture را بسازند (هیچ منبع تصادفیِ پنهانی در شبیه‌ساز نیست)."""
    assert build_cases(all_simulators()[key]) == load_cases(key)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js نصب نیست؛ تست JS در CI اجرا می‌شود")
def test_js_cores_match_python_fixtures():
    result = subprocess.run(
        ["node", str(ROOT / "arcade" / "jstests" / "parity.js")], capture_output=True, text=True, timeout=300
    )
    assert result.returncode == 0, result.stdout + result.stderr
