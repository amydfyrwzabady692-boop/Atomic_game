from django.db import migrations, models


def every_two_hours(apps, schema_editor):
    """پیام دعوت گروه‌ها از هر ۱۵ دقیقه به هر ۲ ساعت (درخواست مالک ربات)؛ از پنل باز هم قابل تغییر است."""
    apps.get_model("wallet", "EconomySettings").objects.update(promo_minutes=120)


class Migration(migrations.Migration):

    dependencies = [
        ("wallet", "0011_group_promo"),
    ]

    operations = [
        migrations.AlterField(
            model_name="economysettings",
            name="promo_enabled",
            field=models.BooleanField(
                default=True,
                help_text="هر چند ساعت یک پیام بی\u200cصدا با دکمه\u200cهای بازی در گروه\u200cها (پیام قبلی همان گروه پاک می\u200cشود).",
                verbose_name="دعوت به بازی در گروه\u200cها",
            ),
        ),
        migrations.AlterField(
            model_name="economysettings",
            name="promo_minutes",
            field=models.PositiveIntegerField(
                default=120,
                help_text="پیش\u200cفرض ۱۲۰ دقیقه، یعنی هر ۲ ساعت یک بار.",
                verbose_name="فاصله\u200cی پیام دعوت (دقیقه)",
            ),
        ),
        migrations.RunPython(every_two_hours, migrations.RunPython.noop),
    ]
