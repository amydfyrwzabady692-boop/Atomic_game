"""ادمین‌های اضافه‌ای که قبلاً فقط به‌صورت فهرست آیدی در تنظیمات اقتصاد بودند، با نقش «مدیر کامل» (همه‌ی
دسترسی‌ها به‌جز مدیریت مدیران و پشتیبان دیتابیس) به جدول مدیران منتقل می‌شوند."""

from django.db import migrations

FULL = ["payments", "coins", "users", "support", "games", "broadcast", "settings", "stats"]


def forwards(apps, schema_editor):
    EconomySettings = apps.get_model("wallet", "EconomySettings")
    BotAdmin = apps.get_model("core", "BotAdmin")
    eco = EconomySettings.objects.filter(pk=1).first()
    for value in (eco.extra_admin_ids if eco else None) or []:
        try:
            tg_id = int(value)
        except (TypeError, ValueError):
            continue
        if tg_id > 0:
            BotAdmin.objects.get_or_create(tg_id=tg_id, defaults={"permissions": FULL})


def backwards(apps, schema_editor):
    EconomySettings = apps.get_model("wallet", "EconomySettings")
    BotAdmin = apps.get_model("core", "BotAdmin")
    eco, _ = EconomySettings.objects.get_or_create(pk=1)
    eco.extra_admin_ids = list(BotAdmin.objects.values_list("tg_id", flat=True))
    eco.save(update_fields=["extra_admin_ids"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_bot_admins"),
        ("wallet", "0009_wider_toman_amounts"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
