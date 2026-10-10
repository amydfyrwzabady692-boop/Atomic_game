import json
from pathlib import Path

from django.core.management.base import BaseCommand

from arcade.sim import all_simulators
from arcade.sim.autoplay import build_cases

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "parity"


class Command(BaseCommand):
    help = (
        "fixtureهای تست تطابق JS/Python را از نو می‌سازد. فقط وقتی اجرا شود که منطق یک بازی "
        "عمداً عوض شده؛ بعدش باید تست Node (arcade/jstests/parity.js) هم سبز باشد."
    )

    def add_arguments(self, parser):
        parser.add_argument("games", nargs="*", help="کلید بازی‌ها (پیش‌فرض: همه)")
        parser.add_argument("--missing", action="store_true", help="فقط بازی‌هایی که fixture ندارند")

    def handle(self, *args, **options):
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        sims = all_simulators()
        for key in options["games"] or sorted(sims):
            path = FIXTURE_DIR / f"{key}.json"
            if options["missing"] and path.exists():
                continue
            cases = build_cases(sims[key])
            path.write_text(json.dumps(cases, separators=(",", ":")) + "\n", encoding="utf-8")
            summary = ", ".join(f"{c['kind']}={c['expected']['score']}" for c in cases)
            self.stdout.write(f"{key}: {summary}")
