# Generated for extra_admin_ids on EconomySettings

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wallet', '0006_topup_and_sell'),
    ]

    operations = [
        migrations.AddField(
            model_name='economysettings',
            name='extra_admin_ids',
            field=models.JSONField(blank=True, default=list, help_text='لیست آیدی‌های عددی تلگرام ادمین‌های افزوده شده از پنل ربات', verbose_name='ادمین‌های اضافه'),
        ),
    ]
