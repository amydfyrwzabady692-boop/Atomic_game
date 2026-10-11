"""همه‌ی متن‌های ربات یک‌جا، تا ویرایش لحن و جمله‌ها راحت باشد.

قالب پیام‌ها HTML است. سکه فقط ارز مجازی تفریحی است و هیچ متنی نباید خلاف این را القا کند.
"""

from core.textutils import fa_digits, fa_num  # noqa: F401  (برای استفاده‌ی راحت در بقیه‌ی ماژول‌ها)

COIN = "🪙"
DIVIDER = "━━━━━━━━━━━━━━"

# ------------------------------------------------------------------ عمومی
START_NEW = (
    "سلام {name}! 👋\n"
    "به ربات بازی‌های گروهی خوش اومدی.\n\n"
    "🎁 <b>{bonus} سکه</b> هدیه‌ی شروع گرفتی!\n\n"
    "منو به گروهت اضافه کن و با /game یه مسابقه راه بنداز.\n"
    "هر روز هم با /daily سکه‌ی رایگان بگیر.\n\n"
    "ℹ️ سکه‌ها فقط امتیاز مجازی داخل ربات هستن و ارزش پولی ندارن."
)
START_BACK = "خوش برگشتی {name}! 👋\nموجودی: <b>{coins}</b> " + COIN + "\n\nراهنما: /help"
START_JOIN_HINT = "✅ حله! حالا برگرد به گروه و دکمه‌ی «شرکت» رو بزن."
REFERRED_BY = "🤝 با دعوت {name} وارد شدی."
HELP_PRIVATE = (
    "📖 <b>راهنما</b>\n\n"
    "/me — پروفایل و آمار\n"
    "/daily — جایزه‌ی روزانه\n"
    "/invite — دعوت دوستان\n"
    "/shop — فروشگاه (آیتم‌های ظاهری)\n"
    "/history — ۲۰ تراکنش آخر سکه\n"
    "/arcade — تمرین آزاد بازی‌های آرکید\n\n"
    "<b>داخل گروه:</b>\n"
    "/game — ساخت مسابقه\n"
    "/top — رتبه‌بندی گروه\n"
    "/rules — قوانین\n\n"
    "ℹ️ سکه فقط امتیاز مجازی و تفریحیه: خرید و فروش، برداشت یا انتقالش ممکن نیست."
)
RULES = (
    "📜 <b>قوانین</b>\n\n"
    "• با /game مسابقه بساز؛ بقیه با دکمه‌ی «شرکت» وارد می‌شن.\n"
    "• ورودی هر نفر به جایزه‌ی کل اضافه می‌شه و بین برنده‌ها تقسیم می‌شه.\n"
    "• اگه بازیکن کافی نیاد یا بازی لغو بشه، ورودی‌ها کامل برمی‌گرده.\n"
    "• فقط جواب بازیکن‌های عضو مسابقه حساب می‌شه؛ پیام ادیت‌شده و فورواردی قبول نیست.\n"
    "• در تساوی، کسی که زودتر به اون امتیاز رسیده جلوتره.\n"
    "• سکه فقط امتیاز مجازی تفریحیه و هیچ ارزش پولی نداره."
)
BANNED = "⛔️ حساب شما مسدود شده."
ONLY_GROUP = "این دستور فقط داخل گروه کار می‌کنه."
ONLY_PRIVATE = "این دستور رو توی پیوی ربات بزن 🙂"
ONLY_PRIVATE_BTN = "🤖 رفتن به پیوی ربات"
ONLY_ADMIN = "این کار فقط برای ادمین‌های گروهه."
TOO_FAST = "یواش‌تر! 🙂"
ERROR_GENERIC = "یه مشکلی پیش اومد. دوباره امتحان کن."
GROUP_WELCOME = (
    "سلام به همه! 🎮\n"
    "من ربات بازی‌های گروهی‌ام. با /game مسابقه بسازید.\n\n"
    "⚠️ برای اینکه جواب‌ها رو ببینم، باید ادمین باشم یا Privacy Mode ربات خاموش باشه.\n"
    "هر کس بار اول باید توی پیوی من /start بزنه."
)

# ------------------------------------------------------------------ پروفایل و اقتصاد
PROFILE = (
    "{frame}👤 <b>{name}</b>{title}{frame}\n\n"
    + COIN
    + " سکه: <b>{coins}</b>\n"
    "⭐ سطح {level}  ({xp} / {next_xp} XP)\n"
    "🎮 بازی‌ها: {games}   🏆 برد: {wins}  ({win_rate}٪)\n"
    "💪 بهترین بازی: {best_game}\n"
    "🔥 streak روزانه: {streak} روز\n"
    "🏅 نشان‌ها: {badges}"
)
PROFILE_ARCADE = "\n👾 رکوردهای آرکید: {records}"
NO_BADGES = "هنوز هیچی"
NO_BEST_GAME = "—"
DAILY_OK = "🎁 <b>جایزه‌ی روزانه</b>\n" + DIVIDER + "\n<b>+{amount}</b> " + COIN + "\n🔥 streak: <b>{streak}</b> روز\n\n<i>فردا بیشتر می‌گیری؛ یه روز هم جا ننداز!</i>"
DAILY_ALREADY = "امروز جایزه‌ت رو گرفتی ✅\n⏳ جایزه‌ی بعدی: {hours} ساعت و {minutes} دقیقه‌ی دیگه"
RESCUE_OK = "\n\n🛟 موجودیت صفر بود؛ <b>{amount}</b> " + COIN + " سکه‌ی نجات گرفتی تا از بازی جا نمونی."
INVITE = (
    "🤝 <b>دعوت دوستان</b>\n\n"
    "لینک اختصاصی تو:\n{link}\n\n"
    "وقتی دوستت با این لینک وارد بشه و اولین بازیش رو انجام بده، "
    "<b>{reward}</b> " + COIN + " می‌گیری.\n"
    "(جایزه بعد از {hours} ساعت از عضویت دوستت فعال می‌شه.)\n\n"
    "دعوت‌شده‌ها: {count} نفر — جایزه‌گرفته: {rewarded}"
)
REFERRAL_REWARDED = "🎉 {name} با دعوت تو اولین بازیش رو کرد!\n<b>{amount}</b> " + COIN + " گرفتی."
HISTORY_HEADER = "🧾 <b>۲۰ تراکنش آخر</b>\n\n"
HISTORY_LINE = "{sign} <b>{amount}</b> — {type}  <i>({date})</i>\n"
HISTORY_EMPTY = "هنوز تراکنشی نداری."
ACHIEVEMENT_UNLOCKED = "{emoji} <b>دستاورد جدید:</b> {title}  (+{reward} " + COIN + ")"
LEVEL_UP = "⭐ {name} به سطح {level} رسید!"

# ------------------------------------------------------------------ ساخت بازی و لابی
GAME_MENU = "🎮 <b>چه بازی‌ای بسازیم؟</b>"
GAME_MENU_ARCADE = "🕹 <b>بازی‌های آرکید — {category}</b>\nبازی داخل تلگرام باز می‌شه و بهترین امتیازت حساب می‌شه."
ARCADE_BTN = "🕹 آرکید: {category}"
BACK_BTN = "« برگشت"
CLOSE_BTN = "✖️ بستن"
CHOOSE_VARIANT = "{emoji} <b>{title}</b>\n{description}\n\n{variant_title}:"
CHOOSE_FEE = "{emoji} <b>{title}</b>\n{description}\n\n" + COIN + " ورودی هر نفر چقدر باشه؟"
CHOOSE_SPLIT = "{emoji} <b>{title}</b>\n\n🏆 جایزه چطور تقسیم بشه؟"
CHOOSE_WINDOW = "{emoji} <b>{title}</b>\n\n⏱ مدت مسابقه چقدر باشه؟ (پیشنهاد: {suggested} دقیقه)"
CHOOSE_JOIN_TIME = "{emoji} <b>{title}</b>\n\n⏳ زمان عضوگیری؟"
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
NOT_YOUR_MENU = "این منو رو یکی دیگه باز کرده. خودت /game بزن 🙂"
MENU_EXPIRED = "این منو منقضی شده. دوباره /game بزن."
ACTIVE_MATCH_EXISTS = "یه مسابقه توی این گروه در جریانه. صبر کن تموم بشه."
USERS_CANNOT_CREATE = "توی این گروه فقط ادمین‌ها می‌تونن مسابقه بسازن."
NO_GAMES_ENABLED = "هیچ بازی‌ای توی این گروه فعال نیست."
GAME_DISABLED = "این بازی فعلاً غیرفعاله. یه بازی دیگه انتخاب کن."
CREATOR_NEEDS_START = "برای ساخت مسابقه اول توی پیوی ربات /start بزن."

LOBBY = (
    "{emoji} <b>{title}</b>{variant}\n"
    "<blockquote>{description}</blockquote>\n"
    + COIN
    + " ورودی  <b>{fee}</b>\n"
    "🏆 جایزه‌ی کل  <b>{pot}</b> " + COIN + "\n"
    "🎯 تقسیم  {split}\n"
    + DIVIDER
    + "\n👥 <b>بازیکن‌ها</b>  {count}/{max}\n{players}\n"
    + DIVIDER
    + "\n⏳ {bar}  <b>{remaining}</b> ثانیه\n"
    "<i>حداقل {min} نفر برای شروع لازم است</i>"
)
LOBBY_NO_PLAYERS = "<i>هنوز کسی نیومده؛ اولین نفر باش!</i>"
LOBBY_CREATED_BY = "سازنده: {name}"
JOIN_BTN = "✅ شرکت"
CANCEL_BTN = "❌ لغو"
START_BOT_BTN = "🤖 بار اولته؟ اول اینجا استارت بزن"
JOINED_OK = "وارد شدی! موفق باشی 🍀"
ALREADY_JOINED = "قبلاً وارد شدی ✅"
LOBBY_CLOSED = "عضوگیری تموم شده."
LOBBY_FULL = "ظرفیت پره!"
NEED_START = "اول باید توی پیوی ربات /start بزنی (دکمه‌ی پایین لابی)، بعد دوباره «شرکت» رو بزن."
NOT_ENOUGH_COINS = "سکه‌ت کمه! 😅\nموجودی: {balance} — لازم: {needed}\nتوی پیوی ربات /daily بزن و سکه‌ی رایگان بگیر."
FEE_NOT_ALLOWED = "این مبلغ ورودی توی این گروه مجاز نیست."
CANCEL_NOT_ALLOWED = "فقط سازنده‌ی مسابقه یا ادمین گروه می‌تونه لغو کنه."
NOTHING_TO_CANCEL = "مسابقه‌ی فعالی نیست."
MATCH_CANCELLED = "❌ <b>مسابقه لغو شد</b>\n" + DIVIDER + "\n{reason}"
REFUND_NOTE = "ورودی همه‌ی بازیکن‌ها برگشت. ↩️"
CANCEL_REASONS = {
    "not_enough_players": "بازیکن کافی نیومد.",
    "manual": "توسط سازنده/ادمین لغو شد.",
    "restart": "ربات ری‌استارت شد.",
    "error": "یه خطای فنی پیش اومد.",
    "admin": "توسط مدیریت لغو شد.",
    "no_content": "محتوای کافی برای این بازی موجود نیست.",
}
MATCH_STARTING = (
    "🚀 <b>{title}</b> شروع شد!\n" + DIVIDER + "\n"
    "👥 {players}\n"
    "🏆 جایزه‌ی کل  <b>{pot}</b> " + COIN + "\n\n"
    "<i>موفق باشید!</i> 🍀"
)

# ------------------------------------------------------------------ نتیجه
RESULT_HEADER = "🏁 <b>پایان {title}</b>\n" + DIVIDER + "\n"
RESULT_LINE = "{medal} <b>{name}</b> — {score} امتیاز{prize}  <i>✨{xp} XP</i>\n"
RESULT_PRIZE = "  ·  <b>+{prize}</b> " + COIN
RESULT_FOOTER = DIVIDER + "\n🏆 جایزه‌ی کل: <b>{pot}</b> " + COIN
RESULT_FREE = DIVIDER + "\n🎈 <i>مسابقه‌ی دوستانه بود (بدون ورودی)</i>"
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
MEDAL_OTHER = "▫️"

# ------------------------------------------------------------------ متن مشترک بازی‌ها
ROUND_HEADER = "🎯 <b>راند {n} از {total}</b>   {dots}"
ROUND_WON = "✅ {name} درست گفت: <b>{answer}</b>   <b>+{points}</b>"
ROUND_TIMEOUT = "⏰ <b>وقت تموم شد!</b>\nجواب: <b>{answer}</b>"
MATH_QUESTION = "{header}\n<blockquote>🧮  <b>{problem} = ؟</b></blockquote>\n<i>اولین جواب درست امتیاز می‌گیرد</i>"

# ------------------------------------------------------------------ رتبه‌بندی
TOP_HEADER = "🏆 <b>برترین‌های {scope}</b>  ·  <i>{period}</i>\n" + DIVIDER + "\n"
TOP_LINE = "{rank} {badge}<b>{name}</b>\n      {coins} " + COIN + "  ·  {wins} برد\n"
TOP_EMPTY = "هنوز بازی‌ای ثبت نشده. با /game شروع کنید!"
TOP_SCOPE_GROUP = "گروه"
TOP_SCOPE_GLOBAL = "کل ربات"
TOP_PERIODS = {"day": "امروز", "week": "این هفته", "all": "کل"}
WEEKLY_CHAMPION = (
    "👑 <b>قهرمان هفته‌ی گروه</b>\n" + DIVIDER + "\n"
    "{name} با <b>{coins}</b> " + COIN + " و {wins} برد!\n\n"
    "<i>جدول هفته از نو شروع شد. کی قهرمان بعدیه؟</i> /game"
)

# ------------------------------------------------------------------ تنظیمات گروه
SETTINGS_HEADER = (
    "⚙️ <b>تنظیمات گروه</b>\n\n"
    + COIN
    + " ورودی مجاز: {min} تا {max}\n"
    "⏳ زمان عضوگیری پیش‌فرض: {join} ثانیه\n"
    "👥 ساخت بازی توسط همه: {users}\n"
    "🎮 بازی‌های فعال: {enabled} از {total}"
)
SETTINGS_GAMES_BTN = "🎮 بازی‌های فعال"
SETTINGS_MIN_BTN = "حداقل ورودی: {v}"
SETTINGS_MAX_BTN = "حداکثر ورودی: {v}"
SETTINGS_JOIN_BTN = "زمان عضوگیری: {v} ثانیه"
SETTINGS_USERS_BTN = "ساخت بازی توسط همه: {v}"
SETTINGS_GAMES_HEADER = "🎮 <b>بازی‌های فعال گروه</b>\nروی هر بازی بزن تا روشن/خاموش بشه."
SETTINGS_LAST_GAME = "حداقل یک بازی باید فعال بمونه."
YES = "✅ بله"
NO = "❌ نه"
ON = "✅"
OFF = "▫️"

# ------------------------------------------------------------------ فروشگاه
SHOP_HEADER = (
    "🛍 <b>فروشگاه</b>\nموجودی: <b>{coins}</b> " + COIN + "\n\n"
    "آیتم‌ها فقط ظاهری‌ان و خریدشون قابل برگشت به سکه نیست."
)
SHOP_KIND_BTN = {"title": "🏷 عنوان‌ها", "emoji": "😎 ایموجی‌ها", "frame": "🖼 قاب‌ها"}
SHOP_ITEM_BTN = "{value} — {price} " + COIN
SHOP_ITEM_OWNED_BTN = "{mark} {value}"
SHOP_EMPTY = "فعلاً آیتمی توی این بخش نیست."
SHOP_CONFIRM = "خرید «{name}» ({value}) به قیمت <b>{price}</b> " + COIN + "؟\n⚠️ خرید قابل برگشت نیست."
SHOP_CONFIRM_BTN = "✅ می‌خرم"
SHOP_BOUGHT = "🎉 خریدی و فعال شد!"
SHOP_EQUIPPED = "فعال شد ✅"
SHOP_UNEQUIPPED = "غیرفعال شد."
SHOP_NO_COINS = "سکه‌ت برای این آیتم کافی نیست."

# ------------------------------------------------------------------ سوپرادمین
GRANT_USAGE = "استفاده: /grant <آیدی عددی یا @username> <مقدار>"
GRANT_OK = "✅ {amount} " + COIN + " به {name} داده شد. موجودی جدید: {balance}"
GRANT_RECEIVED = "🎁 از طرف مدیریت <b>{amount}</b> " + COIN + " گرفتی!"
GRANT_FAILED = "موجودی کاربر برای این کسر کافی نیست."
USER_NOT_FOUND = "کاربر پیدا نشد (باید قبلاً ربات رو استارت کرده باشه)."
BAN_USAGE = "استفاده: /ban <آیدی عددی یا @username>"
BAN_OK = "⛔️ {name} مسدود شد."
UNBAN_OK = "✅ {name} آزاد شد."
BROADCAST_USAGE = "استفاده: /broadcast <متن>  (یا روی یک پیام ریپلای کن)"
BROADCAST_STARTED = "📣 ارسال به {count} کاربر شروع شد…"
BROADCAST_DONE = "📣 ارسال تمام شد. موفق: {ok} — ناموفق: {failed}"
STATS = (
    "📊 <b>آمار ربات</b>\n\n"
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
    "<i>مسابقه در جریانه — بهترین امتیاز هر نفر حساب می‌شود</i>\n"
    + DIVIDER
    + "\n{board}\n"
    + DIVIDER
    + "\n🏆 جایزه‌ی کل <b>{pot}</b> " + COIN + "  ·  🎯 {attempts} تلاش\n"
    "⏳ {bar}  <b>{minutes}:{seconds}</b>{flash}"
)
ARCADE_ROW = "{medal} <b>{name}</b>  {score}   <i>({used}/{total})</i>"
ARCADE_PLAY_BTN = "🎮 بازی کن"
ARCADE_RECORD = "🔥 {name} رکورد زد: {score}!"
ARCADE_PRACTICE = "🕹 <b>تمرین آزاد</b>\nبدون سکه، فقط برای رکورد شخصی. یه بازی انتخاب کن:"
ARCADE_NOT_CONFIGURED = "بازی‌های آرکید هنوز روی این ربات راه‌اندازی نشده."

# ------------------------------------------------------------------ بازی‌های متنی
NOT_A_PLAYER = "تو عضو این مسابقه نیستی."
NOT_YOUR_TURN = "نوبت تو نیست!"
HINT_FIRST_LETTER = "💡 راهنما: با «{letter}» شروع می‌شه"

ANAGRAM_QUESTION = "{header}\n\n🔀 این حروف رو مرتب کن:\n<blockquote><b>{letters}</b></blockquote>{hint}"

EMOJI_QUESTION = "{header}\n\n🤔 این ایموجی‌ها یعنی چی؟\n<blockquote>{emojis}</blockquote>{hint}"
EMOJI_HINT = "\n💡 راهنما: {count} حرف، با «{letter}» شروع می‌شه"

CHAIN_START = (
    "🔗 <b>زنجیره‌ی کلمات</b>\n"
    "هر کس باید کلمه‌ای بگه که با حرف آخر کلمه‌ی قبلی شروع بشه. کلمه‌ی تکراری قبول نیست.\n\n"
    "ترتیب: {order}"
)
CHAIN_TURN = "{prev}👉 نوبت <b>{name}</b>\nیه کلمه با «<b>{letter}</b>» بگو   ⏱ {seconds} ثانیه"
CHAIN_FIRST_WORD = "کلمه‌ی شروع: <b>{word}</b>\n"
CHAIN_ACCEPTED = "✅ {name}: <b>{word}</b>\n"
CHAIN_NEW_LETTER = "(با «{old}» کلمه‌ای نمونده؛ حرف جدید انتخاب شد)\n"
CHAIN_ELIMINATED = "⏰ {name} جا موند و حذف شد!\n"
CHAIN_WRONG_LETTER = "{name}، کلمه باید با «{letter}» شروع بشه."
CHAIN_USED = "{name}، «{word}» قبلاً گفته شده."
CHAIN_INVALID = "{name}، «{word}» توی لیست کلمات نیست."
CHAIN_WINNER = "🏆 {name} آخرین نفر باقی‌مونده‌ست!"
CHAIN_LIMIT = "🤝 سقف نوبت‌ها پر شد؛ بازمانده‌ها مساوی شدن."

HANGMAN_BOARD = (
    "{header}\n<blockquote><b>{pattern}</b></blockquote>\n"
    "❤️ جان گروه   {lives}\n"
    "❌ حرف‌های غلط   {wrong}\n\n"
    "<i>یه حرف بفرست (+۲) یا کل کلمه رو حدس بزن (+۱۰)</i>{note}"
)
HANGMAN_LETTER_OK = "\n\n✅ {name} حرف «{letter}» رو پیدا کرد (+{points})"
HANGMAN_LETTER_BAD = "\n\n❌ {name}: «{guess}» نبود!"
HANGMAN_SOLVED = "🎉 {name} کلمه رو گفت: <b>{word}</b>  (+{points})"
HANGMAN_COMPLETED = "✅ کلمه کامل شد: <b>{word}</b>"
HANGMAN_DEAD = "💀 جان گروه تموم شد! کلمه: <b>{word}</b>"

QUIZ_QUESTION = "{header}\n<blockquote>❓ <b>{question}</b></blockquote>\n⏱ {seconds} ثانیه  ·  <i>جواب سریع‌تر = امتیاز بیشتر</i>"
QUIZ_REVEAL = "{header}\n<blockquote>❓ <b>{question}</b></blockquote>\n✅ جواب: <b>{answer}</b>\n{winners}"
QUIZ_WINNERS = "🎯 درست گفتن: {names}"
QUIZ_NO_WINNER = "😶 هیچ‌کس درست نگفت."
QUIZ_SAVED = "جوابت ثبت شد ✅"
QUIZ_ALREADY = "فقط یک بار می‌تونی جواب بدی."
QUIZ_CLOSED = "این سوال تموم شده."
QUIZ_CATEGORIES = {
    "general": "🌍 عمومی",
    "freefire": "🔫 فری فایر",
    "football": "⚽ فوتبال",
    "movie": "🎬 فیلم",
    "science": "🔬 علمی",
    "mixed": "🎲 ترکیبی",
}

NUMBER_BOARD = "{header}\n<blockquote>🔢 عدد بین <b>{low}</b> و <b>{high}</b> است</blockquote>\n<i>حدس بزن! ربات می‌گه بزرگ‌تره یا کوچیک‌تر.</i>{last}"
NUMBER_HIGHER = "\n\n{name}: {guess} ⬆️ بزرگ‌تره"
NUMBER_LOWER = "\n\n{name}: {guess} ⬇️ کوچیک‌تره"

TYPING_CAPTION = "{header}\n⌨️ جمله‌ی داخل تصویر رو <b>دقیق و سریع</b> تایپ کن!   ⏱ {seconds} ثانیه"
TYPING_RESULT = "⌨️ <b>نتیجه‌ی راند</b>\n<blockquote>{sentence}</blockquote>\n{lines}"
TYPING_LINE = "▫️ <b>{name}</b> — دقت {accuracy}٪ · {seconds} ثانیه   <b>+{points}</b>"
TYPING_NOBODY = "هیچ‌کس تایپ نکرد!"

DICE_TURN = (
    "{emoji} <b>{title}</b>\n" + DIVIDER + "\n{board}\n" + DIVIDER + "\n"
    "👉 نوبت <b>{name}</b>  ·  پرتاب {n} از {total}\n"
    "<i>⏱ {seconds} ثانیه؛ بعدش ربات خودش به نامت پرتاب می‌کند</i>"
)
DICE_BOARD_LINE = "▫️ {name}   <b>{score}</b>"
DICE_THROW_BTN = "{emoji} پرتاب"
DICE_DONE = "{emoji} <b>{title}</b> تموم شد!\n" + DIVIDER + "\n{board}"
DICE_VARIANTS = {
    "dice": "🎲 تاس",
    "darts": "🎯 دارت",
    "basket": "🏀 بسکتبال",
    "football": "⚽ فوتبال",
    "bowling": "🎳 بولینگ",
}

XO_BOARD = "❌⭕️ <b>دوز</b>\n" + DIVIDER + "\n❌ {x}\n⭕️ {o}\n" + DIVIDER + "\n{status}"
XO_TURN = "👉 نوبت <b>{name}</b> ({mark})   ⏱ {seconds} ثانیه"
XO_WIN = "🏆 {name} برد!"
XO_DRAW = "🤝 مساوی شد!"
XO_TIMEOUT = "⏰ وقت {loser} تموم شد؛ {winner} برد!"
XO_TAKEN = "این خونه پره!"

# ------------------------------------------------------------------ شطرنج
CHESS_CAPTION = (
    "♟ <b>شطرنج</b>\n"
    "⚪️ {white}   ·   ⚫️ {black}\n"
    "━━━━━━━━━━━━━━\n"
    "{status}{last}"
)
CHESS_TURN = "👉 نوبت <b>{name}</b> ({color})  ⏱ {seconds} ثانیه"
CHESS_CHECK = "  ⚠️ <b>کیش!</b>"
CHESS_LAST = "\n↩️ آخرین حرکت: <code>{move}</code>"
CHESS_HINT = "\n<i>اول مهره، بعد خانه‌ی مقصد را از کیبورد پایین بزن.</i>"
CHESS_DRAW_OFFER = "\n🤝 {name} پیشنهاد مساوی داده؛ حریف می‌تواند قبول کند."
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
