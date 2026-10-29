from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.db.models.functions import Coalesce

from core.models import TelegramUser
from wallet.models import CoinTransaction, SellRequest, TopUpRequest, TxType


def find_mismatches():
    """کاربرانی که جمع ledger آن‌ها با ``coins`` برابر نیست."""
    qs = TelegramUser.objects.annotate(ledger=Coalesce(Sum("transactions__amount"), 0))
    return [(u.pk, u.tg_id, u.coins, u.ledger) for u in qs.iterator() if u.coins != u.ledger]


def _sums_by(queryset, key: str) -> dict:
    return {row[key]: row["total"] for row in queryset.values(key).annotate(total=Sum("amount"))}


def match_problems() -> list[str]:
    """هر مسابقه دقیقاً همان سکه‌ای را پس داده یا پرداخته که گرفته است:

    - تمام‌شده: جمع جایزه‌ها برابر pot و جمع ورودی‌ها برابر pot
    - لغوشده: هر ورودی کامل برگشته (جمع ورودی و برگشت صفر)
    - لابی یا در حال اجرا: جمع ورودی‌ها برابر pot و هنوز جایزه‌ای پرداخت نشده
    """
    from games.models import Match, MatchStatus

    txs = CoinTransaction.objects.filter(ref_match__isnull=False)
    fees = _sums_by(txs.filter(type=TxType.ENTRY_FEE), "ref_match")
    prizes = _sums_by(txs.filter(type=TxType.PRIZE), "ref_match")
    refunds = _sums_by(txs.filter(type=TxType.REFUND), "ref_match")
    problems = []
    touched = set(fees) | set(prizes) | set(refunds)
    for match in Match.objects.filter(pk__in=touched).only("pk", "status", "pot"):
        taken, paid, back = -(fees.get(match.pk) or 0), prizes.get(match.pk) or 0, refunds.get(match.pk) or 0
        if match.status == MatchStatus.FINISHED and (paid != match.pot or taken != match.pot or back):
            problems.append(f"match {match.pk} finished: pot={match.pot} fees={taken} prizes={paid} refunds={back}")
        elif match.status == MatchStatus.CANCELLED and (taken != back or paid):
            problems.append(f"match {match.pk} cancelled: fees={taken} refunds={back} prizes={paid}")
        elif match.status in (MatchStatus.LOBBY, MatchStatus.RUNNING) and (taken != match.pot or paid or back):
            problems.append(f"match {match.pk} {match.status.lower()}: pot={match.pot} fees={taken} prizes={paid} refunds={back}")
    return problems


def request_problems() -> list[str]:
    """رسیدهای شارژ و درخواست‌های فروش دقیقاً همان تراکنش‌هایی را دارند که وضعیتشان می‌گوید."""
    by_key = defaultdict(int)
    keys = CoinTransaction.objects.filter(idempotency_key__regex=r"^(topup|sell|sell_refund):\d+$")
    for key, amount in keys.values_list("idempotency_key", "amount"):
        by_key[key] += amount
    problems = []
    for req in TopUpRequest.objects.only("pk", "status", "coins"):
        credited = by_key.get(f"topup:{req.pk}", 0)
        expected = req.coins if req.status == TopUpRequest.Status.APPROVED else 0
        if credited != expected:
            problems.append(f"topup {req.pk} {req.status.lower()}: credited={credited} expected={expected}")
    for req in SellRequest.objects.only("pk", "status", "coins"):
        taken = -by_key.get(f"sell:{req.pk}", 0)
        back = by_key.get(f"sell_refund:{req.pk}", 0)
        expected_back = req.coins if req.status == SellRequest.Status.REJECTED else 0
        if taken != req.coins or back != expected_back:
            problems.append(f"sell {req.pk} {req.status.lower()}: taken={taken} refunded={back} expected_refund={expected_back}")
    return problems


def full_audit() -> dict:
    """همه‌ی بررسی‌ها: موجودی هر کاربر با ledger، حساب هر مسابقه و هر درخواست شارژ/فروش."""
    return {
        "wallets": find_mismatches(),
        "matches": match_problems(),
        "requests": request_problems(),
        "users": TelegramUser.objects.count(),
        "transactions": CoinTransaction.objects.count(),
    }


class Command(BaseCommand):
    help = "بررسی می‌کند جمع ledger هر کاربر برابر موجودی‌اش باشد و هر مسابقه و درخواست شارژ/فروش دقیق تسویه شده باشد."

    def handle(self, *args, **options):
        report = full_audit()
        for pk, tg_id, coins, ledger in report["wallets"]:
            self.stdout.write(self.style.ERROR(f"MISMATCH user={pk} tg_id={tg_id} coins={coins} ledger={ledger}"))
        for line in report["matches"] + report["requests"]:
            self.stdout.write(self.style.ERROR(f"MISMATCH {line}"))
        bad = len(report["wallets"]) + len(report["matches"]) + len(report["requests"])
        if bad:
            self.stderr.write(self.style.ERROR(f"{bad} mismatch(es) in {report['users']} wallets"))
            raise SystemExit(1)
        self.stdout.write(
            self.style.SUCCESS(
                f"OK - {report['users']} wallets, {report['transactions']} transactions, matches and requests all match the ledger"
            )
        )
