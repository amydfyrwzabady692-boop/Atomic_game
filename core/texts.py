"""همه‌ی متن‌های ربات یک‌جا، تا ویرایش لحن و جمله‌ها راحت باشد.

قالب پیام‌ها HTML است. لحن: خطاب دوستانه‌ی «تو» با فعل‌های نوشتاری («می‌شود»، نه «می‌شه») تا متن‌ها
یک‌دست و واضح بمانند. سکه فقط ارز مجازی تفریحی است و هیچ متنی نباید خلاف این را القا کند.
"""

from core.textutils import fa_digits, fa_num  # noqa: F401  (برای استفاده‌ی راحت در بقیه‌ی ماژول‌ها)

COIN = "🪙"
DIVIDER = "━━━━━━━━━━━━━━"
COINS_NOTE = "ℹ️ سکه فقط امتیاز مجازی داخل ربات است؛ خرید، فروش، برداشت یا انتقال آن ممکن نیست."

# ------------------------------------------------------------------ عمومی
START_NEW = (
    "سلام {name}! 👋\n"
    "به ربات بازی‌های گروهی خوش آمدی.\n\n"
    "🎁 <b>{bonus} سکه</b> هدیه‌ی شروع گرفتی.\n\n"
    "<b>چطور شروع کنم؟</b>\n"
    "۱. ربات را به گروهت اضافه کن.\n"
    "۲. در گروه /game را بفرست و مسابقه بساز.\n"
    "۳. هر روز با /daily سکه‌ی رایگان بگیر.\n\n" + COINS_NOTE
)
START_BACK = "خوش برگشتی {name}! 👋\n" + COIN + " موجودی: <b>{coins}</b>\n\nاز دکمه‌های زیر یکی را انتخاب کن."
START_JOIN_HINT = "✅ آماده‌ای! حالا به گروه برگرد و دکمه‌ی «شرکت» را بزن."
REFERRED_BY = "🤝 با دعوت {name} وارد شدی."
MENU_ADD_BTN = "➕ افزودن ربات به گروه"
MENU_DAILY_BTN = "🎁 جایزه‌ی روزانه"
MENU_PROFILE_BTN = "👤 پروفایل"
MENU_INVITE_BTN = "🤝 دعوت دوستان"
MENU_SHOP_BTN = "🛍 فروشگاه"
MENU_ARCADE_BTN = "🕹 تمرین آرکید"
MENU_RULES_BTN = "📜 قوانین"
MENU_HELP_BTN = "📖 راهنما"
HELP_PRIVATE = (
    "📖 <b>راهنما</b>\n" + DIVIDER + "\n"
    "<b>در پیوی ربات</b>\n"
    "/me — پروفایل و آمار\n"
    "/daily — جایزه‌ی روزانه\n"
    "/invite — دعوت دوستان\n"
    "/shop — فروشگاه آیتم‌های ظاهری\n"
    "/history — ۲۰ تراکنش آخر سکه\n"
    "/arcade — تمرین آزاد بازی‌های آرکید\n"
    "/gtop — برترین‌های کل ربات\n\n"
    "<b>در گروه</b>\n"
    "/game — ساخت مسابقه\n"
    "/top — رتبه‌بندی گروه\n"
    "/rules — قوانین و راهنمای هر بازی\n"
    "/cancel — لغو مسابقه (سازنده یا ادمین)\n"
    "/settings — تنظیمات گروه (ادمین)\n\n" + COINS_NOTE
)
RULES = (
    "📜 <b>قوانین کلی</b>\n" + DIVIDER + "\n"
    "۱. با /game مسابقه بساز؛ بقیه با دکمه‌ی «شرکت» وارد می‌شوند.\n"
    "۲. ورودی هر نفر به جایزه‌ی کل اضافه و بین برنده‌ها تقسیم می‌شود.\n"
    "۳. اگر بازیکن کافی نیاید یا مسابقه لغو شود، ورودی همه کامل برمی‌گردد.\n"
    "۴. فقط جواب بازیکن‌های عضو مسابقه حساب می‌شود؛ پیام ویرایش‌شده و فورواردی قبول نیست.\n"
    "۵. در تساوی، کسی که زودتر به آن امتیاز رسیده جلوتر است.\n"
    "۶. در بازی‌های آرکید، بهترین امتیاز هر نفر در مهلت مسابقه حساب می‌شود.\n\n"
    + COINS_NOTE
    + "\n\n<i>برای دیدن قوانین هر بازی، یکی از دسته‌های زیر را انتخاب کن.</i>"
)
RULES_TEXT_GAMES_BTN = "🎮 بازی‌های گروهی"
RULES_ARCADE_BTN = "🕹 بازی‌های آرکید"
RULES_LIST_TEXT = "🎮 <b>بازی‌های گروهی</b>\nقوانین کدام بازی را می‌خواهی؟"
RULES_LIST_ARCADE = "🕹 <b>بازی‌های آرکید</b>\nقوانین کدام بازی را می‌خواهی؟"
RULES_GAME = "{emoji} <b>قوانین {title}</b>\n" + DIVIDER + "\n{lines}\n\n👥 {players}"
RULES_LINE = "• {line}"
RULES_PLAYERS_RANGE = "{min} تا {max} بازیکن"
RULES_PLAYERS_FIXED = "{n} بازیکن"
RULES_ARCADE_NOTE = "\n🕹 بازی داخل تلگرام باز می‌شود و بهترین امتیازت حساب می‌شود."
RULES_BTN = "📖 قوانین بازی"
BANNED = "⛔️ حساب تو مسدود شده است."
ONLY_GROUP = "این دستور فقط در گروه کار می‌کند."
ONLY_PRIVATE = "این دستور را در پیوی ربات بفرست 🙂"
ONLY_PRIVATE_BTN = "🤖 رفتن به پیوی ربات"
ONLY_ADMIN = "این کار فقط برای ادمین‌های گروه است."
TOO_FAST = "کمی آهسته‌تر 🙂"
ERROR_GENERIC = "مشکلی پیش آمد. دوباره امتحان کن."
GAME_OVER = "این بازی تمام شده است."
GROUP_WELCOME = (
    "سلام به همه! 🎮\n"
    "من ربات بازی‌های گروهی هستم.\n\n"
    "▫️ با /game مسابقه بسازید.\n"
    "▫️ با /rules قوانین هر بازی را ببینید.\n"
    "▫️ هر نفر بار اول باید در پیوی من /start بزند.\n\n"
    "⚠️ برای دیدن جواب‌ها باید ادمین گروه باشم یا Privacy Mode ربات خاموش باشد."
)

# ------------------------------------------------------------------ پروفایل و اقتصاد
PROFILE = (
    "{frame}👤 <b>{name}</b>{title}{frame}\n" + DIVIDER + "\n"
    + COIN
    + " سکه: <b>{coins}</b>\n"
    "⭐ سطح {level}  ({xp} از {next_xp} XP)\n"
    "🎮 بازی‌ها: {games}   🏆 برد: {wins}  ({win_rate}٪)\n"
    "💪 بهترین بازی: {best_game}\n"
    "🔥 روزهای پیاپی: {streak}\n"
    "🏅 نشان‌ها: {badges}"
)
PROFILE_ARCADE = "\n👾 رکوردهای آرکید: {records}"
NO_BADGES = "هنوز نشانی نگرفته‌ای"
NO_BEST_GAME = "—"
DAILY_OK = (
    "🎁 <b>جایزه‌ی روزانه</b>\n" + DIVIDER + "\n"
    "<b>+{amount}</b> " + COIN + "\n"
    "🔥 روزهای پیاپی: <b>{streak}</b>\n\n"
    "<i>هر روز پیاپی جایزه‌ی بیشتری دارد؛ فردا هم سر بزن.</i>"
)
DAILY_ALREADY = "جایزه‌ی امروز را گرفته‌ای ✅\n⏳ جایزه‌ی بعدی: {hours} ساعت و {minutes} دقیقه‌ی دیگر"
RESCUE_OK = "\n\n🛟 موجودی‌ات صفر بود؛ <b>{amount}</b> " + COIN + " سکه‌ی کمکی گرفتی تا از بازی جا نمانی."
INVITE = (
    "🤝 <b>دعوت دوستان</b>\n" + DIVIDER + "\n"
    "لینک اختصاصی تو:\n{link}\n\n"
    "وقتی دوستت با این لینک وارد شود و اولین بازی‌اش را انجام دهد، "
    "<b>{reward}</b> " + COIN + " می‌گیری.\n"
    "<i>جایزه {hours} ساعت بعد از عضویت دوستت فعال می‌شود.</i>\n\n"
    "👥 دعوت‌شده‌ها: {count} نفر  ·  جایزه‌گرفته: {rewarded}"
)
REFERRAL_REWARDED = "🎉 {name} با دعوت تو اولین بازی‌اش را انجام داد.\n<b>+{amount}</b> " + COIN + " گرفتی."
HISTORY_HEADER = "🧾 <b>۲۰ تراکنش آخر</b>\n" + DIVIDER + "\n"
HISTORY_LINE = "{sign} <b>{amount}</b>  {type}  <i>{date}</i>\n"
HISTORY_EMPTY = "هنوز تراکنشی نداری."
ACHIEVEMENT_UNLOCKED = "{emoji} <b>دستاورد جدید:</b> {title}  (+{reward} " + COIN + ")"
LEVEL_UP = "⭐ {name} به سطح {level} رسید!"

# ------------------------------------------------------------------ ساخت بازی و لابی
GAME_MENU = "🎮 <b>چه بازی‌ای بسازیم؟</b>\n{counts}\n<i>یک بازی را انتخاب کن.</i>"
GAME_MENU_TEXT_COUNT = "🔵 {n} بازی گروهی"
GAME_MENU_ARCADE_COUNT = "🟢 {n} بازی آرکید"
GAME_MENU_ARCADE_OFF = "\n\n<i>🕹 بازی‌های آرکید بعد از راه‌اندازی مینی‌اپ روی این ربات فعال می‌شوند.</i>"
GAME_MENU_CANNOT_READ = (
    "\n\n⚠️ <b>ربات ادمین این گروه نیست</b> و پیام‌ها را نمی‌بیند؛ بازی‌هایی که جوابشان را تایپ می‌کنید "
    "(حساب سریع، حروف درهم، حدس کلمه و …) کار نمی‌کنند. ربات را ادمین گروه کنید."
)
ARCADE_HEADER_BTN = "🕹 بازی‌های آرکید ({n} بازی) 👇"
ARCADE_HEADER_NOTE = (
    "بازی‌های آرکید داخل تلگرام باز می‌شوند و بهترین امتیاز هر نفر در مهلت مسابقه حساب می‌شود. "
    "یکی از بازی‌های زیر این دکمه را انتخاب کن."
)
BACK_BTN = "‹ برگشت"
CLOSE_BTN = "✖️ بستن"
CHOOSE_VARIANT = "{emoji} <b>{title}</b>\n<blockquote>{description}</blockquote>\n{variant_title} را انتخاب کن:"
CHOOSE_FEE = "{emoji} <b>{title}</b>\n<blockquote>{description}</blockquote>\n" + COIN + " ورودی هر نفر چقدر باشد؟"
CHOOSE_SPLIT = "{emoji} <b>{title}</b>\n\n🏆 جایزه چطور تقسیم شود؟"
CHOOSE_WINDOW = "{emoji} <b>{title}</b>\n\n⏱ مدت مسابقه چقدر باشد؟\n<i>پیشنهاد: {suggested} دقیقه</i>"
CHOOSE_JOIN_TIME = "{emoji} <b>{title}</b>\n\n⏳ زمان عضوگیری چقدر باشد؟"
FEE_FREE = "رایگان"
FEE_BTN = "{amount} " + COIN
SPLIT_LABELS = {
    "100": "🥇 همه برای نفر اول",
    "70-30": "۷۰ - ۳۰",
    "60-30-10": "۶۰ - ۳۰ - ۱۰",
    "50-30-20": "۵۰ - ۳۰ - ۲۰",
}
SECONDS_BTN = "{n} ثانیه"
MINUTES_BTN = "{n} دقیقه"
NOT_YOUR_MENU = "این منو را شخص دیگری باز کرده است. خودت /game را بفرست 🙂"
MENU_EXPIRED = "این منو منقضی شده است. دوباره /game را بفرست."
ACTIVE_MATCH_EXISTS = "یک مسابقه در این گروه در جریان است. صبر کن تا تمام شود."
USERS_CANNOT_CREATE = "در این گروه فقط ادمین‌ها می‌توانند مسابقه بسازند."
NO_GAMES_ENABLED = "هیچ بازی‌ای در این گروه فعال نیست."
GAME_DISABLED = "این بازی فعلاً غیرفعال است. بازی دیگری انتخاب کن."
CREATOR_NEEDS_START = "برای ساخت مسابقه اول در پیوی ربات /start بزن."

LOBBY = (
    "{emoji} <b>{title}</b>{variant}\n"
    "<blockquote>{description}</blockquote>\n"
    + COIN
    + " ورودی:  <b>{fee}</b>\n"
    "🏆 جایزه‌ی کل:  <b>{pot}</b> " + COIN + "\n"
    "🎯 تقسیم جایزه:  {split}\n"
    + DIVIDER
    + "\n👥 <b>بازیکن‌ها</b>  {count} از {max}\n{players}\n"
    + DIVIDER
    + "\n⏳ {bar}  <b>{remaining}</b> ثانیه تا شروع\n"
    "<i>برای شروع حداقل {min} نفر لازم است.</i>"
)
LOBBY_PRIZE_NOTE = "\n🎁 <b>جایزه‌ی ویژه:</b> {note}"
LOBBY_NO_PLAYERS = "<i>هنوز کسی نیامده؛ اولین نفر باش!</i>"
LOBBY_CREATED_BY = "سازنده: {name}"
JOIN_BTN = "✅ شرکت"
CANCEL_BTN = "❌ لغو"
START_BOT_BTN = "🤖 بار اول است؟ اول این‌جا استارت بزن"
JOINED_OK = "وارد شدی! موفق باشی 🍀"
ALREADY_JOINED = "قبلاً وارد شده‌ای ✅"
LOBBY_CLOSED = "عضوگیری تمام شده است."
LOBBY_FULL = "ظرفیت پر است!"
NEED_START = "اول باید در پیوی ربات /start بزنی (دکمه‌ی پایین لابی)، بعد دوباره «شرکت» را بزن."
NOT_ENOUGH_COINS = (
    "سکه‌ات کم است! 😅\nموجودی: {balance}  ·  لازم: {needed}\nدر پیوی ربات /daily بزن و سکه‌ی رایگان بگیر."
)
FEE_NOT_ALLOWED = "این مبلغ ورودی در این گروه مجاز نیست."
CANCEL_NOT_ALLOWED = "فقط سازنده‌ی مسابقه یا ادمین گروه می‌تواند لغو کند."
NOTHING_TO_CANCEL = "مسابقه‌ی فعالی وجود ندارد."
MATCH_CANCELLED = "❌ <b>مسابقه لغو شد</b>\n" + DIVIDER + "\n{reason}"
REFUND_NOTE = "↩️ ورودی همه‌ی بازیکن‌ها برگشت."
CANCEL_REASONS = {
    "not_enough_players": "بازیکن کافی نیامد.",
    "manual": "سازنده یا ادمین مسابقه را لغو کرد.",
    "restart": "ربات ری‌استارت شد.",
    "error": "یک خطای فنی پیش آمد.",
    "admin": "توسط مدیریت لغو شد.",
    "no_content": "محتوای کافی برای این بازی موجود نیست.",
}
MATCH_STARTING = (
    "🚀 <b>{title}</b> شروع شد!\n" + DIVIDER + "\n"
    "👥 {players}\n"
    "🏆 جایزه‌ی کل:  <b>{pot}</b> " + COIN + "\n\n"
    "<i>موفق باشید!</i> 🍀"
)

# ------------------------------------------------------------------ نتیجه
RESULT_HEADER = "🏁 <b>پایان {title}</b>\n" + DIVIDER + "\n"
RESULT_LINE = "{medal} <b>{name}</b> — {score} امتیاز{prize}  <i>✨{xp} XP</i>\n"
RESULT_PRIZE = "  ·  <b>+{prize}</b> " + COIN
RESULT_FOOTER = DIVIDER + "\n🏆 جایزه‌ی کل: <b>{pot}</b> " + COIN
RESULT_PRIZE_NOTE = "\n🎁 جایزه‌ی ویژه‌ی این مسابقه: <b>{note}</b> — برگزارکننده آن را به نفر اول می‌دهد."
RESULT_FREE = DIVIDER + "\n🎈 <i>مسابقه‌ی دوستانه بود (بدون ورودی).</i>"
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
MEDAL_OTHER = "▫️"

# ------------------------------------------------------------------ متن مشترک بازی‌ها
ROUND_HEADER = "🎯 <b>راند {n} از {total}</b>   {dots}"
ROUND_WON = "✅ {name} درست گفت: <b>{answer}</b>   <b>+{points}</b>"
ROUND_TIMEOUT = "⏰ <b>وقت تمام شد!</b>\nجواب: <b>{answer}</b>"
MATH_QUESTION = "{header}\n<blockquote>🧮  <b>{problem} = ؟</b></blockquote>\n<i>اولین جواب درست امتیاز می‌گیرد.</i>"

# ------------------------------------------------------------------ رتبه‌بندی
TOP_HEADER = "🏆 <b>برترین‌های {scope}</b>  ·  <i>{period}</i>\n" + DIVIDER + "\n"
TOP_LINE = "{rank} {badge}<b>{name}</b>\n      {coins} " + COIN + "  ·  {wins} برد\n"
TOP_EMPTY = "هنوز مسابقه‌ای ثبت نشده است. با /game شروع کنید!"
TOP_SCOPE_GROUP = "گروه"
TOP_SCOPE_GLOBAL = "کل ربات"
TOP_PERIODS = {"day": "امروز", "week": "این هفته", "all": "کل"}
WEEKLY_CHAMPION = (
    "👑 <b>قهرمان هفته‌ی گروه</b>\n" + DIVIDER + "\n"
    "{name} با <b>{coins}</b> " + COIN + " و {wins} برد!\n\n"
    "<i>جدول هفته از نو شروع شد. قهرمان بعدی کیست؟</i> /game"
)

# ------------------------------------------------------------------ تنظیمات گروه
SETTINGS_HEADER = (
    "⚙️ <b>تنظیمات گروه</b>\n" + DIVIDER + "\n"
    + COIN
    + " ورودی مجاز: {min} تا {max}\n"
    "⏳ زمان عضوگیری پیش‌فرض: {join} ثانیه\n"
    "👥 ساخت مسابقه توسط همه: {users}\n"
    "🎮 بازی‌های فعال: {enabled} از {total}\n\n"
    "<i>روی هر دکمه بزن تا مقدارش عوض شود.</i>"
)
SETTINGS_GAMES_BTN = "🎮 بازی‌های فعال"
SETTINGS_MIN_BTN = "حداقل ورودی: {v}"
SETTINGS_MAX_BTN = "حداکثر ورودی: {v}"
SETTINGS_JOIN_BTN = "زمان عضوگیری: {v} ثانیه"
SETTINGS_USERS_BTN = "ساخت مسابقه توسط همه: {v}"
SETTINGS_GAMES_HEADER = "🎮 <b>بازی‌های فعال گروه</b>\n<i>روی هر بازی بزن تا روشن یا خاموش شود.</i>"
SETTINGS_LAST_GAME = "حداقل یک بازی باید فعال بماند."
YES = "✅ بله"
NO = "❌ نه"
ON = "✅"
OFF = "▫️"

# ------------------------------------------------------------------ فروشگاه
SHOP_HEADER = (
    "🛍 <b>فروشگاه</b>\n" + DIVIDER + "\n"
    + COIN
    + " موجودی: <b>{coins}</b>\n\n"
    "<i>آیتم‌ها فقط ظاهری‌اند و خریدشان قابل برگشت نیست.</i>"
)
SHOP_KIND_BTN = {"title": "🏷 عنوان‌ها", "emoji": "😎 ایموجی‌ها", "frame": "🖼 قاب‌ها"}
SHOP_ITEM_BTN = "{value} — {price} " + COIN
SHOP_ITEM_OWNED_BTN = "{mark} {value}"
SHOP_EMPTY = "فعلاً آیتمی در این بخش نیست."
SHOP_CONFIRM = "خرید «{name}» ({value}) به قیمت <b>{price}</b> " + COIN + "؟\n⚠️ خرید قابل برگشت نیست."
SHOP_CONFIRM_BTN = "✅ می‌خرم"
SHOP_STARS_BTN = "⭐ خرید با {stars} استار"
SHOP_STARS_NOTE = "\n⭐ یا با <b>{stars}</b> استار تلگرام (پرداخت رسمی خود تلگرام)."
SHOP_STARS_TITLE = "{name}"
SHOP_STARS_DESCRIPTION = "آیتم ظاهری «{name}» ({value}) برای پروفایل تو در ربات بازی. ارزش پولی ندارد و به سکه تبدیل نمی‌شود."
SHOP_STARS_DONE = "🎉 پرداخت انجام شد؛ «{name}» به آیتم‌هایت اضافه و فعال شد."
SHOP_STARS_INVALID = "این آیتم دیگر قابل خرید نیست یا قبلاً آن را داری."
SHOP_BOUGHT = "🎉 خریدی و فعال شد!"
SHOP_EQUIPPED = "فعال شد ✅"
SHOP_UNEQUIPPED = "غیرفعال شد."
SHOP_NO_COINS = "سکه‌ات برای این آیتم کافی نیست."

# ------------------------------------------------------------------ سوپرادمین
PRIZE_USAGE = "استفاده: /prize <متن جایزه‌ی ویژه>  ·  برای پاک کردن: /prize -"
PRIZE_SET = "🎁 جایزه‌ی ویژه‌ی مسابقه‌های این گروه: <b>{note}</b>\n<i>در لابی و نتیجه نشان داده می‌شود. پرداختش با خود برگزارکننده است.</i>"
PRIZE_CLEARED = "جایزه‌ی ویژه پاک شد."
BACKUP_CAPTION = "🗄 <b>پشتیبان دیتابیس</b>\n📅 {date}  ·  {size} کیلوبایت\n<i>بازگردانی: python manage.py loaddata نام‌فایل</i>"
BACKUP_TOO_BIG = "⚠️ فایل پشتیبان از ۵۰ مگابایت بزرگ‌تر شده و تلگرام آن را نمی‌فرستد؛ از روی سرور پشتیبان بگیر."
BACKUP_STARTED = "🗄 در حال ساختن پشتیبان…"
BACKUP_FAILED = "ساختن یا فرستادن پشتیبان نشد؛ لاگ ربات را ببین."
GRANT_USAGE = "استفاده: /grant <آیدی عددی یا @username> <مقدار>"
GRANT_OK = "✅ {amount} " + COIN + " به {name} داده شد. موجودی جدید: {balance}"
GRANT_RECEIVED = "🎁 از طرف مدیریت <b>{amount}</b> " + COIN + " گرفتی!"
GRANT_FAILED = "موجودی کاربر برای این کسر کافی نیست."
USER_NOT_FOUND = "کاربر پیدا نشد (باید قبلاً ربات را استارت کرده باشد)."
BAN_USAGE = "استفاده: /ban <آیدی عددی یا @username>"
BAN_OK = "⛔️ {name} مسدود شد."
UNBAN_OK = "✅ {name} آزاد شد."
BROADCAST_USAGE = "استفاده: /broadcast <متن>  (یا روی یک پیام ریپلای کن)"
BROADCAST_STARTED = "📣 ارسال به {count} کاربر شروع شد…"
BROADCAST_DONE = "📣 ارسال تمام شد. موفق: {ok} — ناموفق: {failed}"
STATS = (
    "📊 <b>آمار ربات</b>\n" + DIVIDER + "\n"
    "👤 کاربران: {users}  (فعال امروز: {dau})\n"
    "👥 گروه‌های فعال: {groups}\n"
    "🎮 مسابقات امروز: {matches_today}  (کل: {matches})\n"
    "⭐ محبوب‌ترین بازی: {top_game}\n"
    + COIN
    + " سکه‌ی در گردش: {coins}"
)

# ------------------------------------------------------------------ آرکید (Mini App)
ARCADE_RUNNING = (
    "{emoji} <b>{title}</b>{variant}\n"
    "<i>مسابقه در جریان است — بهترین امتیاز هر نفر حساب می‌شود.</i>\n"
    + DIVIDER
    + "\n{board}\n"
    + DIVIDER
    + "\n🏆 جایزه‌ی کل: <b>{pot}</b> " + COIN + "  ·  🎯 {attempts} تلاش\n"
    "⏳ {bar}  <b>{minutes}:{seconds}</b>{flash}"
)
ARCADE_ROW = "{medal} <b>{name}</b>  {score}   <i>({used} از {total})</i>"
ARCADE_PLAY_BTN = "🎮 بازی کن"
ARCADE_RECORD = "🔥 {name} رکورد زد: {score}!"
ARCADE_PRACTICE = "🕹 <b>تمرین آزاد</b>\n<i>بدون سکه، فقط برای رکورد شخصی.</i>\n\nیک بازی انتخاب کن:"
ARCADE_NOT_CONFIGURED = "🕹 بازی‌های آرکید هنوز روی این ربات راه‌اندازی نشده است."
ARCADE_SETUP_HINT = (
    "\n\n<b>راه‌اندازی (فقط برای مدیر ربات):</b>\n"
    "۱. سرویس web را پشت یک آدرس HTTPS بگذار.\n"
    "۲. در BotFather با /newapp مینی‌اپ بساز؛ آدرس: <code>https://دامنه/arcade/</code> و نام کوتاه: <code>{short}</code>\n"
    "۳. در فایل .env مقدار <code>MINIAPP_BASE_URL=https://دامنه</code> را بگذار و ربات را دوباره راه‌اندازی کن."
)

# ------------------------------------------------------------------ بازی‌های متنی
NOT_A_PLAYER = "تو عضو این مسابقه نیستی."
NOT_YOUR_TURN = "نوبت تو نیست!"
HINT_FIRST_LETTER = "💡 راهنما: با «{letter}» شروع می‌شود"

ANAGRAM_QUESTION = "{header}\n\n🔀 این حروف را مرتب کن:\n<blockquote><b>{letters}</b></blockquote>{hint}"

EMOJI_QUESTION = "{header}\n\n🤔 این ایموجی‌ها چه چیزی را نشان می‌دهند؟\n<blockquote>{emojis}</blockquote>{hint}"
EMOJI_HINT = "\n💡 راهنما: {count} حرف، با «{letter}» شروع می‌شود"

CHAIN_START = (
    "🔗 <b>زنجیره‌ی کلمات</b>\n" + DIVIDER + "\n"
    "هر نفر باید کلمه‌ای بگوید که با حرف آخر کلمه‌ی قبلی شروع شود. کلمه‌ی تکراری قبول نیست.\n\n"
    "🔁 ترتیب: {order}"
)
CHAIN_TURN = "{prev}👉 نوبت <b>{name}</b>\nیک کلمه با «<b>{letter}</b>» بگو   ⏱ {seconds} ثانیه"
CHAIN_FIRST_WORD = "کلمه‌ی شروع: <b>{word}</b>\n"
CHAIN_ACCEPTED = "✅ {name}: <b>{word}</b>\n"
CHAIN_NEW_LETTER = "<i>با «{old}» کلمه‌ای نمانده بود؛ حرف جدید انتخاب شد.</i>\n"
CHAIN_ELIMINATED = "⏰ {name} جا ماند و حذف شد!\n"
CHAIN_WRONG_LETTER = "{name}، کلمه باید با «{letter}» شروع شود."
CHAIN_USED = "{name}، «{word}» قبلاً گفته شده است."
CHAIN_INVALID = "{name}، «{word}» در فهرست کلمات نیست."
CHAIN_WINNER = "🏆 {name} آخرین نفر باقی‌مانده است!"
CHAIN_LIMIT = "🤝 سقف نوبت‌ها پر شد؛ بازمانده‌ها مساوی شدند."

HANGMAN_BOARD = (
    "{header}\n<blockquote><b>{pattern}</b></blockquote>\n"
    "❤️ جان گروه:   {lives}\n"
    "❌ حرف‌های غلط:   {wrong}\n\n"
    "<i>یک حرف بفرست (+۲) یا کل کلمه را حدس بزن (+۱۰).</i>{note}"
)
HANGMAN_LETTER_OK = "\n\n✅ {name} حرف «{letter}» را پیدا کرد (+{points})"
HANGMAN_LETTER_BAD = "\n\n❌ {name}: «{guess}» نبود!"
HANGMAN_SOLVED = "🎉 {name} کلمه را گفت: <b>{word}</b>  (+{points})"
HANGMAN_COMPLETED = "✅ کلمه کامل شد: <b>{word}</b>"
HANGMAN_DEAD = "💀 جان گروه تمام شد! کلمه: <b>{word}</b>"

QUIZ_QUESTION = (
    "{header}\n<blockquote>❓ <b>{question}</b></blockquote>\n"
    "⏱ {seconds} ثانیه  ·  <i>جواب سریع‌تر، امتیاز بیشتر</i>"
)
QUIZ_REVEAL = "{header}\n<blockquote>❓ <b>{question}</b></blockquote>\n✅ جواب: <b>{answer}</b>\n{winners}"
QUIZ_WINNERS = "🎯 درست گفتند: {names}"
QUIZ_NO_WINNER = "😶 هیچ‌کس درست نگفت."
QUIZ_SAVED = "جوابت ثبت شد ✅"
QUIZ_ALREADY = "فقط یک بار می‌توانی جواب بدهی."
QUIZ_CLOSED = "این سؤال تمام شده است."
QUIZ_CATEGORIES = {
    "general": "🌍 عمومی",
    "freefire": "🔫 فری فایر",
    "football": "⚽ فوتبال",
    "movie": "🎬 فیلم",
    "science": "🔬 علمی",
    "mixed": "🎲 ترکیبی",
}

NUMBER_BOARD = (
    "{header}\n<blockquote>🔢 عدد بین <b>{low}</b> و <b>{high}</b> است</blockquote>\n"
    "<i>حدست را بفرست؛ ربات می‌گوید عدد بزرگ‌تر است یا کوچک‌تر.</i>{last}"
)
NUMBER_HIGHER = "\n\n{name}: {guess} ⬆️ عدد بزرگ‌تر است"
NUMBER_LOWER = "\n\n{name}: {guess} ⬇️ عدد کوچک‌تر است"

TYPING_CAPTION = "{header}\n⌨️ جمله‌ی داخل تصویر را <b>دقیق و سریع</b> تایپ کن!   ⏱ {seconds} ثانیه"
TYPING_RESULT = "⌨️ <b>نتیجه‌ی راند</b>\n<blockquote>{sentence}</blockquote>\n{lines}"
TYPING_LINE = "▫️ <b>{name}</b> — دقت {accuracy}٪ · {seconds} ثانیه   <b>+{points}</b>"
TYPING_NOBODY = "هیچ‌کس تایپ نکرد!"

DICE_TURN = (
    "{emoji} <b>{title}</b>\n" + DIVIDER + "\n{board}\n" + DIVIDER + "\n"
    "👉 نوبت <b>{name}</b>  ·  پرتاب {n} از {total}\n"
    "<i>⏱ {seconds} ثانیه وقت داری؛ بعد از آن ربات خودش به نام تو پرتاب می‌کند.</i>"
)
DICE_BOARD_LINE = "▫️ {name}   <b>{score}</b>"
DICE_THROW_BTN = "{emoji} پرتاب"
DICE_DONE = "{emoji} <b>{title}</b> تمام شد!\n" + DIVIDER + "\n{board}"
DICE_VARIANTS = {
    "dice": "🎲 تاس",
    "darts": "🎯 دارت",
    "basket": "🏀 بسکتبال",
    "football": "⚽ فوتبال",
    "bowling": "🎳 بولینگ",
}

XO_BOARD = "❌⭕️ <b>دوز {size}×{size}</b>\n" + DIVIDER + "\n❌ {x}\n⭕️ {o}\n" + DIVIDER + "\n{status}"
XO_HINT = "\n<i>برای برد، {n} علامت را در یک ردیف، ستون یا قطر کنار هم بگذار.</i>"
XO_TURN = "👉 نوبت <b>{name}</b> ({mark})   ⏱ {seconds} ثانیه"
XO_WIN = "🏆 {name} برد!"
XO_DRAW = "🤝 مساوی شد!"
XO_TIMEOUT = "⏰ وقت {loser} تمام شد؛ {winner} برد!"
XO_TAKEN = "این خانه پر است!"

C4_BOARD = (
    "🔴🟡 <b>دوز چهارتایی</b>\n" + DIVIDER + "\n🔴 {red}\n🟡 {yellow}\n" + DIVIDER + "\n{grid}\n\n{status}"
)
C4_HINT = "\n<i>شماره‌ی ستون را بزن تا مهره‌ات در آن بیفتد؛ چهار مهره در یک خط یعنی برد.</i>"
C4_FULL = "این ستون پر است!"

# ------------------------------------------------------------------ شطرنج
CHESS_CAPTION = "♟ <b>شطرنج</b>\n⚪️ {white}   ·   ⚫️ {black}\n" + DIVIDER + "\n{status}{last}"
CHESS_TURN = "👉 نوبت <b>{name}</b> ({color})  ⏱ {seconds} ثانیه"
CHESS_CHECK = "  ⚠️ <b>کیش!</b>"
CHESS_LAST = "\n↩️ آخرین حرکت: <code>{move}</code>"
CHESS_HINT = "\n<i>اول مهره، بعد خانه‌ی مقصد را از کیبورد پایین بزن.</i>"
CHESS_DRAW_OFFER = "\n🤝 {name} پیشنهاد مساوی داده است؛ حریف می‌تواند قبول کند."
CHESS_LIVE_HINT = "\n\n<i>برای بازی، دکمه‌ی زیر را بزن تا صفحه‌ی شطرنج باز شود. بقیه هم می‌توانند تماشا کنند.</i>"
CHESS_PLAY_BTN = "♟ باز کردن صفحه‌ی شطرنج"
LIVE_PLAY_BTN = "🎮 باز کردن صفحه‌ی بازی"
LIVE_HINT = "\n\n<i>برای بازی، دکمه‌ی زیر را بزن تا صفحه‌ی بازی باز شود. بقیه هم می‌توانند تماشا کنند.</i>"
LIVE_RESIGN = "🏳 {loser} تسلیم شد؛ {winner} برد."
CHESS_WHITE = "سفید"
CHESS_BLACK = "سیاه"
CHESS_RESIGN_BTN = "🏳 تسلیم"
CHESS_DRAW_BTN = "🤝 مساوی"
CHESS_PICK_OWN = "یکی از مهره‌های خودت را انتخاب کن."
CHESS_NO_MOVES = "این مهره حرکت مجازی ندارد."
CHESS_DRAW_SENT = "پیشنهاد مساوی ثبت شد ✅"
CHESS_END_MATE = "🏆 <b>کیش و مات!</b> {name} برد."
CHESS_END_RESIGN = "🏳 {loser} تسلیم شد؛ {winner} برد."
CHESS_END_TIMEOUT = "⏰ وقت {loser} تمام شد؛ {winner} برد."
CHESS_END_DRAW = "🤝 <b>مساوی</b> — {reason}"
CHESS_DRAW_REASONS = {
    "stalemate": "پات (حرکت مجاز نمانده)",
    "insufficient": "مهره‌ی کافی برای مات نمانده",
    "fifty": "قانون ۵۰ حرکت",
    "repetition": "تکرار سه‌باره‌ی وضعیت",
    "agreed": "با توافق دو بازیکن",
    "limit": "سقف تعداد حرکت‌ها",
}
LOBBY_PLAYER = "{n}. {name}"
MORE_PLAYERS = "<i>… و {n} نفر دیگر</i>"


def progress_bar(fraction: float, width: int = 10) -> str:
    """نوار پیشرفت متنی: ▰▰▰▱▱"""
    fraction = max(0.0, min(1.0, fraction))
    filled = round(fraction * width)
    return "▰" * filled + "▱" * (width - filled)


def round_dots(current: int, total: int) -> str:
    if total > 12:
        return ""
    return "●" * current + "○" * max(0, total - current)


def _apply_currency_name() -> None:
    """نام و نماد واحد امتیاز را از تنظیمات (``COIN_NAME`` و ``COIN_EMOJI``) روی همه‌ی متن‌ها اعمال می‌کند."""
    try:
        from django.conf import settings

        name, emoji = settings.COIN_NAME, settings.COIN_EMOJI
    except Exception:  # تنظیمات جنگو در دسترس نیست (مثلاً اسکریپت مستقل)
        return
    if name == "سکه" and emoji == "🪙":
        return

    def swap(text: str) -> str:
        return text.replace("سکه", name).replace("🪙", emoji)

    namespace = globals()
    for key, value in list(namespace.items()):
        if not key.isupper():
            continue
        if isinstance(value, str):
            namespace[key] = swap(value)
        elif isinstance(value, dict):
            namespace[key] = {k: swap(v) if isinstance(v, str) else v for k, v in value.items()}


_apply_currency_name()
