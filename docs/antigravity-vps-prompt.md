# پرامپت استقرار روی VPS (برای Antigravity)

متن داخل کادر را کامل کپی کنید و به Antigravity بدهید (روی همان سروری که ربات اجرا می‌شود).

```text
تو روی یک سرور لینوکسی (VPS) کار می‌کنی که ربات تلگرام «وینزون بت» روی آن با Docker Compose اجرا می‌شود.
کد: https://github.com/amydfyrwzabady692-boop/Atomic_game
شاخه‌ی جدید: claude/serene-curie-4a9jx0  (اگر در main ادغام شده، به‌جایش main را بگیر)
سرویس‌ها: db (PostgreSQL 16)، redis، web (Django + gunicorn، داخل کانتینر پورت 8000، روی میزبان پورت WEB_PORT پیش‌فرض 8120)،
bot (ربات تلگرام). سرویس web موقع بالا آمدن خودش migrate می‌کند.

قوانین مهم (همیشه رعایت کن):
- هیچ volume، دیتابیس، پوشه‌ی backups یا فایل .env را پاک یا بازنویسی نکن. قبل از هر تغییر پشتیبان بگیر.
- مقدار رمزها و توکن‌ها (BOT_TOKEN، SECRET_KEY، POSTGRES_PASSWORD و …) را هرگز در خروجی چاپ نکن؛ فقط بودن یا نبودنشان را گزارش کن.
- هر مرحله را اجرا کن و خروجی‌اش را بخوان. اگر خطا دیدی همان‌جا بایست، علت را پیدا کن و گزارش بده؛ حدس نزن.
- اگر docker compose (نسخه‌ی ۲) نبود و فقط docker-compose بود، همان را به‌جایش استفاده کن.

مراحل:

۱) پیدا کردن پروژه و وضعیت فعلی
   - پوشه‌ی پروژه را پیدا کن (مثلاً: find / -name docker-compose.yml -path "*Atomic*" 2>/dev/null) و وارد آن شو.
   - اجرا کن: docker compose ps ، git status ، git log -1 --oneline
   - اگر تغییر محلیِ ثبت‌نشده در گیت هست، با git stash کنارش بگذار و در گزارش بنویس چه فایل‌هایی بود.

۲) پشتیبان (حتماً قبل از هر کاری)
   - mkdir -p backups
   - docker compose exec -T db pg_dump -U gamebot -d gamebot | gzip > backups/db-$(date +%Y%m%d-%H%M%S).sql.gz
   - ls -lh backups  ← فایل تازه نباید خالی باشد.
   - cp .env backups/env-$(date +%Y%m%d-%H%M%S).bak

۳) گرفتن کد تازه
   - git fetch origin && git checkout claude/serene-curie-4a9jx0 && git pull --ff-only origin claude/serene-curie-4a9jx0

۴) بررسی فایل .env (مقدارهای حساس را چاپ نکن)
   - حتماً باید درست باشند: BOT_TOKEN ، SUPERADMIN_IDS ، SECRET_KEY (رشته‌ی تصادفی بلند؛ اگر هنوز مقدار نمونه است، با
     python3 -c "import secrets;print(secrets.token_urlsafe(50))" یکی بساز و جایگزین کن) ، DEBUG=False ،
     ALLOWED_HOSTS (شامل دامنه) ، CSRF_TRUSTED_ORIGINS=https://<دامنه> ، MINIAPP_BASE_URL=https://<دامنه> (بدون / آخر) ،
     ARCADE_DEV_AUTH=False
   - کلیدهای تازه‌ی اختیاری (اگر نیستند لازم نیست اضافه کنی؛ مقدار پیش‌فرض دارند):
     OWNER_TG_ID ، TRANSFER_MIN_COINS=10 ، GROUP_MESSAGES_PER_MINUTE=20 ، GROUP_EDITS_PER_MINUTE=40 ،
     GUNICORN_WORKERS=3 ، GUNICORN_THREADS=8 ، TELEGRAM_PROXY
   - مقدار MINIAPP_SHORT_NAME را گزارش کن (پیش‌فرض arcade).

۵) دسترسی سرور به تلگرام
   - curl -sS -m 10 -o /dev/null -w "%{http_code}\n" https://api.telegram.org
   - اگر جواب نداد یا timeout شد (سرور داخل ایران است)، ربات بدون پروکسی کار نمی‌کند: یک پروکسی SOCKS5 یا HTTP که روی همین
     سرور در دسترس است لازم است و آدرسش را در .env بگذار، مثلاً TELEGRAM_PROXY=socks5://127.0.0.1:1080 . اگر پروکسی‌ای نیست،
     بایست و به من بگو.

۶) دامنه و HTTPS (برای مینی‌اپ و دکمه‌ی «ورود به بازی» در گروه ضروری است)
   - دامنه باید به IP همین سرور اشاره کند (dig +short <دامنه>).
   - اگر هنوز reverse proxy با گواهی معتبر نداری، Caddy را نصب کن و در /etc/caddy/Caddyfile این را بگذار
     (دامنه و پورت را با WEB_PORT خودت تطبیق بده)، بعد systemctl reload caddy :
         <دامنه> {
             encode gzip zstd
             reverse_proxy 127.0.0.1:8120
         }
   - اگر nginx یا Cloudflare داری، همان را نگه دار و فقط مطمئن شو https://<دامنه> به پورت WEB_PORT همین سرور می‌رسد
     و هدر X-Forwarded-Proto را می‌فرستد.

۷) اجرا
   - chmod +x scripts/deploy.sh && ./scripts/deploy.sh claude/serene-curie-4a9jx0
     (این اسکریپت پشتیبان می‌گیرد، کد را می‌گیرد، docker compose up -d --build می‌زند و سلامت web را بررسی می‌کند.)
   - بعد بررسی کن:
     docker compose ps                                  ← همه Up و web/db/redis در حالت healthy
     docker compose logs --tail=120 web bot             ← نباید Traceback باشد؛ در لاگ bot باید "bot ready" باشد
     docker compose exec web python manage.py migrate --check
     docker compose exec web python manage.py showmigrations core wallet   ← همه [X]؛ در این نسخه core 0004 و 0005 و
       wallet 0009 و 0010 تازه‌اند: جدول «مدیران ربات» (نقش و دسترسی هر مدیر) ساخته می‌شود، فهرست قدیمی «مدیران اضافه»
       با دسترسی کامل به آن منتقل می‌شود و ستون‌های مبلغ تومانی bigint می‌شوند. اگر هر کدام خطا داد، بایست و گزارش بده.
     docker compose exec web python manage.py audit_wallets   ← باید بدون مغایرت تمام شود (حالا موجودی هر کاربر، حساب
       هر مسابقه و هر رسید شارژ/درخواست فروش را با ledger می‌سنجد؛ اگر MISMATCH دید، خروجی را کامل گزارش کن و چیزی را دستی درست نکن)
     curl -sS https://<دامنه>/healthz                   ← باید ok بدهد
     curl -sS -o /dev/null -w "%{http_code}\n" https://<دامنه>/static/arcade/common/telegram-web-app.js  ← باید 200 باشد
   - فقط اگر دیتابیس تازه و خالی است: docker compose exec web python manage.py seed_content

۸) کارهایی که فقط خودم در تلگرام (BotFather) می‌توانم انجام بدهم — دقیق بگو چه کنم:
   - مینی‌اپ: یا با /newapp یک مینی‌اپ با نام کوتاه دقیقاً برابر MINIAPP_SHORT_NAME و آدرس https://<دامنه>/arcade/ بسازم،
     یا MINIAPP_SHORT_NAME را خالی کنیم و در Bot Settings ← Configure Mini App همان آدرس را ثبت کنم.
   - /setprivacy ← Disable  و  /setjoingroups ← Enable
   - ربات را در گروه‌ها ادمین کنم تا جواب‌های تایپی را ببیند.

۹) آزمایش نهایی (از من بخواه انجام بدهم و نتیجه را بپرس)
   - در گروه: /game ← یک بازی آرکید (مثلاً سیخ‌زن) یا شطرنج ← با دو اکانت «شرکت» ← بعد از شروع، دکمه‌ی «🎮 ورود به بازی»
     باید همان مسابقه را باز کند؛ هر بازیکن در پیوی ربات هم یک دکمه‌ی ورود مستقیم می‌گیرد.
   - با اکانتی که هنوز ربات را استارت نکرده «شرکت» را بزن ← باید پیوی ربات باز شود و بعد از Start خودکار عضو شود.
   - در همان گروه هم‌زمان دو یا سه بازی بساز (مثلاً شطرنج و حساب سریع)؛ هر لابی جدا عضو بگیرد و جدا شروع شود.
   - شطرنج: بعد از انتخاب بازی باید «کنترل زمان» (مثل برق‌آسا ۳+۲) پرسیده شود و در صفحه‌ی بازی ساعت هر نفر کم شود.
   - در پیوی: کیف پول ← انتقال ۱۰ سکه ← دکمه‌ی تأیید (دوبار زدن نباید دوبار کم کند).
   - شارژ آزمایشی با عکس رسید ← در پنل /admin مدیر تأیید یا رد کند.
   - پنل /admin ← «مدیران» ← یک اکانت دوم را با نقش «پشتیبانی» اضافه کن؛ آن اکانت در /admin فقط بخش‌های همان نقش را ببیند
     و مثلاً «دادن سکه» برایش نباشد. بعد حذفش کن یا نقشش را درست کن.
   - شطرنج در مینی‌اپ: وقتی نوبت حریف است یک حرکت بکش (فلش قرمز پیش‌حرکت) ← بعد از حرکت حریف خودکار زده شود.
   - پوکر در مینی‌اپ: وقتی نوبت دیگری است «چک/فولد» یا «کال هر مبلغ» را بزن ← با رسیدن نوبت خودکار انجام شود.

۱۰) اگر چیزی خراب شد
   - اگر کامیت قبلی (مرحله‌ی ۱) از قبل از این نسخه است، اول یک پشتیبان تازه بگیر (مرحله‌ی ۲) و مهاجرت‌های تازه را به همین
     ترتیب برگردان، وگرنه کد قدیمی با جدول‌های تازه بالا نمی‌آید:
         docker compose exec web python manage.py migrate core 0003
         docker compose exec web python manage.py migrate wallet 0008
     (مدیرانی که در پنل اضافه شده‌اند به فهرست قدیمی «مدیران اضافه» برمی‌گردند؛ با بالا آمدن دوباره‌ی این نسخه دسترسی
     کامل می‌گیرند و نقششان باید دوباره تنظیم شود.)
   - کد: git checkout <کامیت قبلی که در مرحله‌ی ۱ دیدی> && docker compose up -d --build
   - دیتابیس فقط در صورت لزوم و با هماهنگی من از پشتیبان مرحله‌ی ۲ برگردد
     (gunzip -c backups/db-....sql.gz | docker compose exec -T db psql -U gamebot -d gamebot روی دیتابیس خالی).

در پایان یک گزارش کوتاه بده: کامیتی که الان اجراست، وضعیت هر سرویس، نتیجه‌ی healthz و audit_wallets و showmigrations، هر خطایی که دیدی
و دقیقاً چه کارهایی را باید خودم در BotFather و تلگرام انجام بدهم.
```
