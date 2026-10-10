"""بارگذاری محتوا: seed اولیه و import از CSV (پنل ادمین).

قالب CSV (ردیف اول عنوان ستون‌هاست، کدگذاری UTF-8):
- کلمات:   ``word,category``
- سوال‌ها:  ``category,text,option1,option2,option3,option4,correct,difficulty``  (correct از ۱ تا ۴)
- ایموجی:  ``emojis,answer,alt_answers``  (جایگزین‌ها با ``|`` جدا می‌شوند)
- جمله‌ها:  ``text``
"""

import csv
import io

from core.textutils import normalize_fa

from ..models import EmojiPuzzle, Question, TypingSentence, WordEntry
from .emoji_puzzles import EMOJI_PUZZLES
from .questions import load_questions
from .sentences import TYPING_SENTENCES
from .words import MAX_LENGTH, MIN_LENGTH, difficulty_of, load_words


class ImportError_(Exception):
    pass


def _reader(file) -> csv.DictReader:
    raw = file.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise ImportError_("فایل خالی است یا ردیف عنوان ندارد.")
    reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]
    return reader


def _require(reader: csv.DictReader, *columns: str) -> None:
    missing = [c for c in columns if c not in reader.fieldnames]
    if missing:
        raise ImportError_(f"ستون‌های لازم پیدا نشد: {', '.join(missing)}")


# ------------------------------------------------------------------ کلمات
def add_words(pairs) -> int:
    existing = set(WordEntry.objects.values_list("word", flat=True))
    new = []
    for raw, category in pairs:
        word = normalize_fa(raw or "", keep_spaces=False)
        if not (MIN_LENGTH <= len(word) <= MAX_LENGTH) or not word.isalpha() or word in existing:
            continue
        existing.add(word)
        new.append(
            WordEntry(word=word, category=(category or "general")[:32], length=len(word), difficulty=difficulty_of(word))
        )
    WordEntry.objects.bulk_create(new, ignore_conflicts=True)
    return len(new)


def import_words_csv(file) -> int:
    reader = _reader(file)
    _require(reader, "word")
    return add_words((row.get("word"), row.get("category")) for row in reader)


# ------------------------------------------------------------------ سوال‌ها
def add_questions(items) -> int:
    existing = set(Question.objects.values_list("text", flat=True))
    new = []
    for item in items:
        text = (item["text"] or "").strip()
        if not text or text in existing:
            continue
        existing.add(text)
        new.append(
            Question(
                category=item["category"],
                text=text,
                options=item["options"],
                correct_index=item["correct_index"],
                difficulty=item.get("difficulty", 1),
            )
        )
    Question.objects.bulk_create(new)
    return len(new)


def import_questions_csv(file) -> int:
    reader = _reader(file)
    _require(reader, "category", "text", "option1", "option2", "correct")
    valid_categories = set(Question.Category.values)
    items = []
    for line, row in enumerate(reader, start=2):
        options = [row[f"option{i}"].strip() for i in range(1, 5) if (row.get(f"option{i}") or "").strip()]
        correct = (row.get("correct") or "").strip()
        category = (row.get("category") or "").strip().lower()
        if category not in valid_categories:
            raise ImportError_(f"ردیف {line}: دسته‌ی نامعتبر «{category}»")
        if len(options) < 2 or not correct.isdigit() or not 1 <= int(correct) <= len(options):
            raise ImportError_(f"ردیف {line}: گزینه‌ها یا شماره‌ی جواب درست نامعتبر است")
        difficulty = (row.get("difficulty") or "1").strip()
        items.append(
            {
                "category": category,
                "text": row.get("text"),
                "options": options,
                "correct_index": int(correct) - 1,
                "difficulty": int(difficulty) if difficulty.isdigit() else 1,
            }
        )
    return add_questions(items)


# ------------------------------------------------------------------ پازل ایموجی
def add_puzzles(items) -> int:
    existing = set(EmojiPuzzle.objects.values_list("emojis", flat=True))
    new = []
    for emojis, answer, alts in items:
        emojis, answer = (emojis or "").strip(), (answer or "").strip()
        if not emojis or not answer or emojis in existing:
            continue
        existing.add(emojis)
        new.append(EmojiPuzzle(emojis=emojis, answer=answer, alt_answers=[a.strip() for a in alts if a.strip()]))
    EmojiPuzzle.objects.bulk_create(new)
    return len(new)


def import_puzzles_csv(file) -> int:
    reader = _reader(file)
    _require(reader, "emojis", "answer")
    return add_puzzles(
        (row.get("emojis"), row.get("answer"), (row.get("alt_answers") or "").split("|")) for row in reader
    )


# ------------------------------------------------------------------ جمله‌ها
def add_sentences(texts) -> int:
    existing = set(TypingSentence.objects.values_list("text", flat=True))
    new = []
    for raw in texts:
        text = " ".join((raw or "").split())
        if not text or len(text) > 200 or text in existing:
            continue
        existing.add(text)
        new.append(TypingSentence(text=text))
    TypingSentence.objects.bulk_create(new, ignore_conflicts=True)
    return len(new)


def import_sentences_csv(file) -> int:
    reader = _reader(file)
    _require(reader, "text")
    return add_sentences(row.get("text") for row in reader)


# ------------------------------------------------------------------ seed
def seed_all() -> dict[str, int]:
    """محتوای اولیه را بارگذاری می‌کند. اجرای دوباره چیزی را تکراری نمی‌سازد."""
    from leaderboard.models import Achievement
    from leaderboard.progress import ACHIEVEMENTS
    from shop.services import seed_default_items

    achievements = 0
    for code, (emoji, title, description, reward) in ACHIEVEMENTS.items():
        _, created = Achievement.objects.get_or_create(
            code=code, defaults={"emoji": emoji, "title": title, "description": description, "reward_coins": reward}
        )
        achievements += created
    return {
        "words": add_words(load_words()),
        "questions": add_questions(load_questions()),
        "emoji_puzzles": add_puzzles(EMOJI_PUZZLES),
        "sentences": add_sentences(TYPING_SENTENCES),
        "shop_items": seed_default_items(),
        "achievements": achievements,
    }
