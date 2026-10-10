"""صفحه‌های کمکی توسعه (فقط وقتی DEBUG=True): اجرای تست تطابق JS/Python داخل مرورگر."""

from django.http import FileResponse, Http404
from django.shortcuts import render

from .management.commands.arcade_fixtures import FIXTURE_DIR
from .sim import all_simulators


def parity(request):
    return render(request, "arcade/dev_parity.html", {"keys": sorted(all_simulators())})


def fixture(request, game_key: str):
    path = FIXTURE_DIR / f"{game_key}.json"
    if game_key not in all_simulators() or not path.is_file():
        raise Http404
    return FileResponse(path.open("rb"), content_type="application/json")
