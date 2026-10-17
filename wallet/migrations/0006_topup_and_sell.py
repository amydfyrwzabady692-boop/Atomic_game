# Generated for TopUp and Sell models & EconomySettings additions (1000 Toman / 100 coin min sell)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
        ('wallet', '0005_remove_topup_and_sell'),
    ]

    operations = [
        migrations.AddField(
            model_name='economysettings',
            name='coin_price_toman',
            field=models.PositiveIntegerField(default=1000, help_text='قیمت پایه برای شارژ کیف پول (۱۰۰۰ تومان)', verbose_name='قیمت هر سکه (تومان)'),
        ),
        migrations.AddField(
            model_name='economysettings',
            name='topup_fee_percent',
            field=models.PositiveIntegerField(default=10, help_text='کارمزد شارژ کیف پول (مثلاً ۱۰ برای ۱۰٪)', verbose_name='درصد کارمزد شارژ'),
        ),
        migrations.AddField(
            model_name='economysettings',
            name='card_number',
            field=models.CharField(blank=True, default='', help_text='شماره کارت مقصد جهت واریز وجه شارژ', max_length=32, verbose_name='شماره کارت واریز'),
        ),
        migrations.AddField(
            model_name='economysettings',
            name='card_holder',
            field=models.CharField(blank=True, default='', help_text='نام دارنده کارت مقصد', max_length=128, verbose_name='نام صاحب کارت'),
        ),
        migrations.AddField(
            model_name='economysettings',
            name='min_sell_coins',
            field=models.PositiveIntegerField(default=100, help_text='حداقل تعداد سکه برای درخواست تسویه و فروش (۱۰۰ سکه)', verbose_name='حداقل سکه برای فروش'),
        ),
        migrations.AddField(
            model_name='economysettings',
            name='coin_sell_price_toman',
            field=models.PositiveIntegerField(default=1000, help_text='مبلغ پرداختی به کاربر به ازای هر سکه در فروش (۱۰۰۰ تومان)', verbose_name='قیمت فروش هر سکه (تومان)'),
        ),
        migrations.AlterField(
            model_name='cointransaction',
            name='type',
            field=models.CharField(
                choices=[
                    ('DAILY', 'جایزه‌ی روزانه'),
                    ('REFERRAL', 'دعوت دوست'),
                    ('ENTRY_FEE', 'ورودی بازی'),
                    ('PRIZE', 'جایزه‌ی بازی'),
                    ('REFUND', 'برگشت ورودی'),
                    ('ADMIN_GRANT', 'هدیه‌ی ادمین'),
                    ('SHOP', 'خرید فروشگاه'),
                    ('ACHIEVEMENT', 'دستاورد'),
                    ('SIGNUP_BONUS', 'هدیه‌ی ثبت‌نام'),
                    ('RESCUE', 'سکه‌ی نجات'),
                    ('TOPUP', 'شارژ کیف پول'),
                    ('SELL', 'فروش سکه'),
                    ('TRANSFER_OUT', 'انتقال به کاربر'),
                    ('TRANSFER_IN', 'دریافت از کاربر'),
                ],
                max_length=16,
                verbose_name='نوع',
            ),
        ),
        migrations.CreateModel(
            name='TopUpRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('coins', models.PositiveIntegerField(verbose_name='تعداد سکه')),
                ('amount_toman', models.PositiveIntegerField(verbose_name='مبلغ خام (تومان)')),
                ('fee_toman', models.PositiveIntegerField(verbose_name='کارمزد (تومان)')),
                ('total_toman', models.PositiveIntegerField(verbose_name='مبلغ کل پرداختی (تومان)')),
                ('receipt_photo_id', models.CharField(blank=True, max_length=255, verbose_name='شناسه عکس رسید تلگرام')),
                ('status', models.CharField(choices=[('PENDING', 'در انتظار بررسی'), ('APPROVED', 'تایید شده'), ('REJECTED', 'رد شده')], default='PENDING', max_length=16, verbose_name='وضعیت')),
                ('admin_note', models.CharField(blank=True, max_length=255, verbose_name='توضیح ادمین')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')),
                ('reviewed_at', models.DateTimeField(blank=True, null=True, verbose_name='تاریخ بررسی')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='topup_requests', to='core.telegramuser', verbose_name='کاربر')),
            ],
            options={
                'verbose_name': 'درخواست شارژ کیف پول',
                'verbose_name_plural': 'درخواست‌های شارژ کیف پول',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='SellRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('coins', models.PositiveIntegerField(verbose_name='تعداد سکه')),
                ('amount_toman', models.PositiveIntegerField(verbose_name='مبلغ واریزی (تومان)')),
                ('card_number', models.CharField(max_length=32, verbose_name='شماره کارت')),
                ('card_holder', models.CharField(blank=True, max_length=128, verbose_name='نام دارنده کارت')),
                ('status', models.CharField(choices=[('PENDING', 'در انتظار واریز'), ('PAID', 'واریز شد'), ('REJECTED', 'رد شده')], default='PENDING', max_length=16, verbose_name='وضعیت')),
                ('admin_note', models.CharField(blank=True, max_length=255, verbose_name='توضیح ادمین')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')),
                ('reviewed_at', models.DateTimeField(blank=True, null=True, verbose_name='تاریخ بررسی')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sell_requests', to='core.telegramuser', verbose_name='کاربر')),
            ],
            options={
                'verbose_name': 'درخواست فروش سکه',
                'verbose_name_plural': 'درخواست‌های فروش سکه',
                'ordering': ['-created_at'],
            },
        ),
    ]
