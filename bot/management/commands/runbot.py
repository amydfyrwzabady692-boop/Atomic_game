from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "ربات تلگرام را اجرا می‌کند (polling اگر WEBHOOK_URL خالی باشد، وگرنه webhook)."

    def handle(self, *args, **options):
        from bot.app import run

        run()
