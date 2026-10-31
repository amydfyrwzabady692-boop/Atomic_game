# پرامپت استقرار روی VPS (برای Antigravity)

متن داخل کادر را کامل کپی کنید و به Antigravity بدهید (روی همان سروری که ربات اجرا می‌شود).

```text
تو روی یک سرور لینوکسی (VPS) کار می‌کنی که ربات تلگرام «وینزون بت» روی آن با Docker Compose اجرا می‌شود.
کد: https://github.com/amydfyrwzabady692-boop/Atomic_game
شاخه: claude/serene-curie-4a9jx0  (اگر در main ادغام شده، به‌جایش main را بگیر)
سرویس‌ها: db (PostgreSQL 16)، redis، web (Django + gunicorn، داخل کانتینر پورت 8000، روی میزبان پورت WEB_PORT پیش‌فرض 8120)،
bot (ربات تلگرام). سرویس web موقع بالا آمدن خودش migrate می‌کند.

این نسخه «جوین اجباری» (کانال‌هایی که کاربر باید عضوشان شود) و «API برای ربات‌های دیگر» دارد: ربات‌های دیگر با کلید
می‌پرسند کاربر این ربات را استارت کرده یا عضو کانالی شده (https://<دامنه>/api/v1/...) و رویدادها را با وب‌هوک می‌گیرند.
راهنمای کامل API در docs/forced-join-api.md همین مخزن است.

قوانین مهم (همیشه رعایت کن):
- هیچ volume، دیتابیس، پوشه‌ی backups یا فایل .env را پاک یا بازنویسی نکن. قبل از هر تغییر پشتیبان بگیر.
- مقدار رمزها و توکن‌ها (BOT_TOKEN، SECRET_KEY، POSTGRES_PASSWORD، کلیدهای API که با wz_ شروع می‌شوند و …) را هرگز در
  خروجی چاپ نکن؛ فقط بودن یا نبودنشان را گزارش کن.
- هر مرحله را اجرا کن و خروجی‌اش را بخوان. اگر خطا دیدی همان‌جا بایست، علت را پیدا کن و گزارش بده؛ حدس نزن.
- اگر docker compose (نسخه‌ی ۲) نبود و فقط docker-compose بود، همان را به‌جایش استفاده کن.

مراحل:

۱) پیدا کردن پروژه و وضعیت فعلی
   - پوشه‌ی پروژه را پیدا کن (مثلاً: find / -name docker-compose.yml -path "*Atomic*" 2>/dev/null) و وارد آن شو.
   - اجرا کن: docker compose ps ، git status ، git log -1 --oneline  (کامیت فعلی را برای برگشت یادداشت کن)
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
     ALLOWED_HOSTS (شامل دامنه) ، CSRF_TRUSTED_ORIGINS=https://<دامنه> ، MINIAPP_BASE_URL=https://<دامنه> (بدون / آخر؛
     آدرس API هم از همین ساخته می‌شود) ، ARCADE_DEV_AUTH=False
   - کلیدهای اختیاری (اگر نیستند لازم نیست اضافه کنی؛ مقدار پیش‌فرض دارند):
     OWNER_TG_ID ، TRANSFER_MIN_COINS=10 ، GROUP_MESSAGES_PER_MINUTE=20 ، GROUP_EDITS_PER_MINUTE=40 ،
     GUNICORN_WORKERS=3 ، GUNICORN_THREADS=8 ، TELEGRAM_PROXY ، PARTNER_HTTP_PROXY (تازه: فقط اگر سرور به آدرس وب‌هوک
     ربات‌های دیگر دسترسی ندارد)
   - مقدار MINIAPP_SHORT_NAME را گزارش کن (پیش‌فرض arcade).

۵) دسترسی سرور به تلگرام
   - curl -sS -m 10 -o /dev/null -w "%{http_code}\n" https://api.telegram.org
   - اگر جواب نداد یا timeout شد (سرور داخل ایران است)، ربات بدون پروکسی کار نمی‌کند: یک پروکسی SOCKS5 یا HTTP که روی همین
     سرور در دسترس است لازم است و آدرسش را در .env بگذار، مثلاً TELEGRAM_PROXY=socks5://127.0.0.1:1080 . اگر پروکسی روی
     خود میزبان است، از داخل کانتینر با 127.0.0.1 دیده نمی‌شود: آدرس IP داخلی میزبان (مثلاً 172.17.0.1) را بگذار و مطمئن شو
     پروکسی روی آن گوش می‌دهد. اگر پروکسی‌ای نیست، بایست و به من بگو.
   - در این نسخه سرویس web هم (برای API و جوین اجباری مینی‌اپ) با همان TELEGRAM_PROXY از تلگرام عضویت کانال را می‌پرسد.

۶) دامنه و HTTPS (برای مینی‌اپ، دکمه‌ی «ورود به بازی» در گروه و API ضروری است)
   - دامنه باید به IP همین سرور اشاره کند (dig +short <دامنه>).
   - اگر هنوز reverse proxy با گواهی معتبر نداری، Caddy را نصب کن و در /etc/caddy/Caddyfile این را بگذار
     (دامنه و پورت را با WEB_PORT خودت تطبیق بده)، بعد systemctl reload caddy :
         <دامنه> {
             encode gzip zstd
             reverse_proxy 127.0.0.1:8120
         }
   - اگر nginx یا Cloudflare داری، همان را نگه دار و فقط مطمئن شو https://<دامنه> (هم /arcade/ و هم /api/v1/) به پورت
     WEB_PORT همین سرور می‌رسد و هدرهای Authorization و X-Api-Key را حذف نمی‌کند و X-Forwarded-Proto را می‌فرستد.

۷) اجرا
   - chmod +x scripts/deploy.sh && ./scripts/deploy.sh claude/serene-curie-4a9jx0
     (این اسکریپت پشتیبان می‌گیرد، کد را می‌گیرد، docker compose up -d --build می‌زند و سلامت web را بررسی می‌کند.)
   - بعد بررسی کن:
     docker compose ps                                  ← همه Up و web/db/redis در حالت healthy
     docker compose logs --tail=120 web bot             ← نباید Traceback باشد؛ در لاگ bot باید "bot ready" باشد
     docker compose exec web python manage.py migrate --check
     docker compose exec web python manage.py showmigrations core wallet membership   ← همه [X]. در این نسخه core 0006
       (زمان استارت و بلاک ربات؛ برای کاربرهای قدیمی زمان ثبت‌نام گذاشته می‌شود) و membership 0001 (کانال‌های جوین اجباری و
       کلیدهای API) تازه‌اند. اگر سرور هنوز روی نسخه‌ی قبل از نقش‌های مدیران بود، core 0004/0005 و wallet 0009/0010 هم تازه‌اند.
       اگر هر کدام خطا داد، بایست و گزارش بده.
     docker compose exec web python manage.py audit_wallets   ← باید بدون مغایرت تمام شود؛ اگر MISMATCH دید، خروجی را کامل
       گزارش کن و چیزی را دستی درست نکن
     curl -sS https://<دامنه>/healthz                   ← باید ok بدهد
     curl -sS -o /dev/null -w "%{http_code}\n" https://<دامنه>/static/arcade/common/telegram-web-app.js  ← باید 200 باشد
     curl -sS -w " [%{http_code}]\n" https://<دامنه>/api/v1/me   ← باید {"ok": false, "error": "bad_key"} [401] بدهد
       (یعنی API بالا است و فقط کلید ندارد؛ اگر 404 یا صفحه‌ی HTML آمد، reverse proxy آدرس /api/ را نمی‌رساند)
     docker compose exec web python manage.py shell -c "from membership.checks import telegram; print('telegram from web:', (telegram('getMe') or {}).get('ok'))"
       ← باید True چاپ کند؛ None یعنی کانتینر web به تلگرام دسترسی ندارد (TELEGRAM_PROXY را ببین) و False یعنی BOT_TOKEN را قبول نکرد. در این حالت جوین
       اجباری فقط در خود ربات کار می‌کند و API عضویت کانال را «نامعلوم» برمی‌گرداند؛ گزارش بده.
   - فقط اگر دیتابیس تازه و خالی است: docker compose exec web python manage.py seed_content

۸) کارهایی که فقط خودم در تلگرام می‌توانم انجام بدهم — دقیق و قدم‌به‌قدم بگو چه کنم:
   - (اگر قبلاً نکرده‌ام) مینی‌اپ: یا با /newapp در BotFather یک مینی‌اپ با نام کوتاه دقیقاً برابر MINIAPP_SHORT_NAME و آدرس
     https://<دامنه>/arcade/ بسازم، یا MINIAPP_SHORT_NAME را خالی کنیم و در Bot Settings ← Configure Mini App همان آدرس را ثبت کنم.
     /setprivacy ← Disable  و  /setjoingroups ← Enable ، و ربات را در گروه‌ها ادمین کنم.
   - جوین اجباری: ربات را در هر کانال ادمین کنم (برای کانال خصوصی دسترسی «دعوت کاربران با لینک» هم بدهم)، بعد در پیوی ربات:
     /admin ← «📢 جوین اجباری» ← «➕ افزودن کانال» و یوزرنیم، لینک، آیدی عددی یا یک پیام فورواردشده از کانال را بفرستم.
     در جزئیات هر کانال باید «ربات در کانال: ✅ ادمین است» ببینم.
   - API برای ربات دیگر: /admin ← «🔑 API ربات‌ها» ← «➕ کلید تازه» ← یک نام؛ کلید (wz_...) را فقط به ربات طرف مقابل بدهم.
     اگر آن ربات آدرس وب‌هوک دارد، همان‌جا «🔗 تنظیم وب‌هوک» و بعد «🧪 تست وب‌هوک» (باید 200 بدهد).

۹) آزمایش نهایی (از من بخواه انجام بدهم و نتیجه را بپرس)
   - با یک اکانت معمولی (نه مدیر) که عضو کانال نیست: /start ← باید پیام «🔒 برای استفاده از ربات اول عضو …» با دکمه‌ی کانال و
     «✅ عضو شدم» بیاید. بدون عضویت «✅ عضو شدم» ← هشدار «هنوز عضو … نشده‌ای». بعد از عضویت ← «✅ عضویتت تأیید شد» و منوی ربات.
   - همان اکانت بعد از ترک کانال: در گروه «شرکت» در یک لابی ← باید پیوی ربات باز شود، پیام عضویت بیاید و بعد از عضویت و
     «✅ عضو شدم» خودکار عضو همان مسابقه شود. مینی‌اپ هم تا عضویت صفحه‌ی «🔒 اول عضو کانال‌های ربات شو» نشان دهد.
   - اکانت مدیر بدون عضویت هم باید همه‌چیز را باز ببیند.
   - API با کلیدی که ساختم (کلید را چاپ نکن؛ از متغیر محیطی بخوان):
       read -s KEY   (کلید را بی‌صدا وارد کن)
       curl -sS "https://<دامنه>/api/v1/user?user_id=<آیدی عددی من>" -H "Authorization: Bearer $KEY"
         ← برای اکانتی که ربات را استارت کرده "started": true
       curl -sS "https://<دامنه>/api/v1/check?user_id=<آیدی عددی من>&channels=@<کانال>" -H "X-Api-Key: $KEY"
         ← "joined" باید با عضویت واقعی من جور باشد (ربات باید در آن کانال ادمین باشد)
   - اگر وب‌هوک گذاشتم: یک اکانت تازه ربات را استارت کند ← ربات طرف مقابل باید رویداد start بگیرد؛ نتیجه‌ی آخرین ارسال در
     جزئیات کلید در پنل دیده می‌شود.

۱۰) اگر چیزی خراب شد
   - اگر کامیت قبلی (مرحله‌ی ۱) از قبل از این نسخه است، اول یک پشتیبان تازه بگیر (مرحله‌ی ۲) و مهاجرت‌های تازه را به همین
     ترتیب برگردان، وگرنه کد قدیمی با جدول‌های تازه بالا نمی‌آید:
         docker compose exec web python manage.py migrate membership zero
         docker compose exec web python manage.py migrate core 0005
     (کانال‌های جوین اجباری و کلیدهای API پاک می‌شوند و بعد از برگشت به این نسخه باید دوباره اضافه شوند.)
     اگر کامیت قبلی حتی از قبل از نسخه‌ی «نقش‌های مدیران» است، بعد از آن این دو را هم بزن:
         docker compose exec web python manage.py migrate core 0003
         docker compose exec web python manage.py migrate wallet 0008
   - کد: git checkout <کامیت قبلی که در مرحله‌ی ۱ دیدی> && docker compose up -d --build
   - دیتابیس فقط در صورت لزوم و با هماهنگی من از پشتیبان مرحله‌ی ۲ برگردد
     (gunzip -c backups/db-....sql.gz | docker compose exec -T db psql -U gamebot -d gamebot روی دیتابیس خالی).

در پایان یک گزارش کوتاه بده: کامیتی که الان اجراست، وضعیت هر سرویس، نتیجه‌ی healthz و audit_wallets و showmigrations،
جواب /api/v1/me (بدون کلید) و «telegram from web»، هر خطایی که دیدی و دقیقاً چه کارهایی را باید خودم در تلگرام انجام بدهم.
```
