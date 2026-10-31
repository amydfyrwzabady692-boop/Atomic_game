"""پست‌های آماده‌ی کانال را با تنظیمات فعلی (قیمت سکه، تعداد بازی‌ها و …) چاپ می‌کند تا دستی هم کپی شوند.

    python manage.py channel_posts                 # همه، با یوزرنیم BOT_USERNAME
    python manage.py channel_posts --bot my_bot    # با یوزرنیم دیگر
    python manage.py channel_posts --markdown      # برای docs/channel-posts.md

انتشار مستقیم با دکمه‌ها از پیوی ربات است: /admin ← «📣 تبلیغ و کانال» ← «📰 پست‌های آماده‌ی کانال».
"""

import re

from django.conf import settings
from django.core.management.base import BaseCommand

from core import texts
from wallet.models import EconomySettings


class Command(BaseCommand):
    help = "پست‌های آماده‌ی کانال را چاپ می‌کند (انتشار با دکمه: /admin ← تبلیغ و کانال)."

    def add_arguments(self, parser):
        parser.add_argument("--bot", default="", help="یوزرنیم ربات بدون @")
        parser.add_argument("--markdown", action="store_true", help="خروجی برای فایل markdown")

    def handle(self, *args, **options):
        from bot.handlers.promo import channel_post

        username = options["bot"] or settings.BOT_USERNAME or "<یوزرنیم_ربات>"
        eco = EconomySettings.load()
        for key, title, _ in texts.CHANNEL_POSTS:
            text, markup = channel_post(key, username, eco)
            buttons = [f"[{b.text}]({b.url})" for row in markup.inline_keyboard for b in row]
            if options["markdown"]:
                plain = re.sub(r"</?(b|i|code)>", lambda m: {"<b>": "**", "</b>": "**", "<code>": "`", "</code>": "`"}.get(m.group(0), ""), text)
                self.stdout.write(f"## {title}\n\n{plain}\n\nدکمه‌ها: {' · '.join(buttons)}\n\n---\n")
            else:
                self.stdout.write(f"===== {title} ({key}) =====\n{text}\n\nدکمه‌ها: {' | '.join(buttons)}\n")
