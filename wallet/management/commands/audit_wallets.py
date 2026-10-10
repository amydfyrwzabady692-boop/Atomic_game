from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.db.models.functions import Coalesce

from core.models import TelegramUser


def find_mismatches():
    """کاربرانی که جمع ledger آن‌ها با ``coins`` برابر نیست."""
    qs = TelegramUser.objects.annotate(ledger=Coalesce(Sum("transactions__amount"), 0))
    return [(u.pk, u.tg_id, u.coins, u.ledger) for u in qs.iterator() if u.coins != u.ledger]


class Command(BaseCommand):
    help = "بررسی می‌کند جمع تراکنش‌های ledger هر کاربر برابر موجودی سکه‌اش باشد."

    def handle(self, *args, **options):
        bad = find_mismatches()
        total = TelegramUser.objects.count()
        for pk, tg_id, coins, ledger in bad:
            self.stdout.write(
                self.style.ERROR(f"MISMATCH user={pk} tg_id={tg_id} coins={coins} ledger={ledger}")
            )
        if bad:
            self.stderr.write(self.style.ERROR(f"{len(bad)} mismatch(es) in {total} wallets"))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(f"OK - {total} wallets match the ledger"))
