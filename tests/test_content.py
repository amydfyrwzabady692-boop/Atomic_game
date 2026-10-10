import io

import pytest
from django.core.management import call_command

from core.textutils import normalize_fa
from games.content import importer
from games.content.emoji_puzzles import EMOJI_PUZZLES
from games.content.provider import DbContentProvider, NoContent
from games.content.questions import QUESTIONS, load_questions
from games.content.sentences import TYPING_SENTENCES
from games.content.words import load_words
from games.models import EmojiPuzzle, Question, TypingSentence, WordEntry
from shop.models import ShopItem


def test_word_bank_size_and_shape():
    words = [w for w, _ in load_words()]
    assert len(words) >= 500
    assert len(set(words)) == len(words)
    assert all(w.isalpha() and " " not in w and "‌" not in w for w in words)
    assert all(normalize_fa(w, keep_spaces=False) == w for w in words)
    lengths = {len(w) for w in words}
    assert {3, 4, 5, 6, 7} <= lengths  # طول‌های مختلف


def test_question_bank_has_100_questions_in_required_categories():
    questions = load_questions()
    assert len(questions) >= 100
    assert set(QUESTIONS) == {"general", "freefire", "football", "movie", "science"}
    assert all(len(items) >= 20 for items in QUESTIONS.values())
    assert len({q["text"] for q in questions}) == len(questions)
    for q in questions:
        assert len(q["options"]) == 4 and len(set(q["options"])) == 4
        assert 0 <= q["correct_index"] < 4
    for items in QUESTIONS.values():
        for text, correct, wrong in items:
            built = next(q for q in questions if q["text"] == text)
            assert built["options"][built["correct_index"]] == correct
            assert correct not in wrong
    # جواب درست همیشه در یک جای ثابت نیست
    assert len({q["correct_index"] for q in questions}) == 4


def test_emoji_and_sentence_banks():
    assert len(EMOJI_PUZZLES) >= 50
    assert len({p[0] for p in EMOJI_PUZZLES}) == len(EMOJI_PUZZLES)
    assert len(TYPING_SENTENCES) >= 50
    assert len(set(TYPING_SENTENCES)) == len(TYPING_SENTENCES)
    assert all("‌" not in s and 15 <= len(s) <= 80 for s in TYPING_SENTENCES)


@pytest.mark.django_db
def test_seed_content_is_idempotent():
    call_command("seed_content")
    counts = (
        WordEntry.objects.count(),
        Question.objects.count(),
        EmojiPuzzle.objects.count(),
        TypingSentence.objects.count(),
        ShopItem.objects.count(),
    )
    assert counts[0] >= 500 and counts[1] >= 100 and counts[2] >= 50 and counts[3] >= 50 and counts[4] > 0
    call_command("seed_content")
    assert counts == (
        WordEntry.objects.count(),
        Question.objects.count(),
        EmojiPuzzle.objects.count(),
        TypingSentence.objects.count(),
        ShopItem.objects.count(),
    )
    assert Question.objects.filter(category="freefire").count() >= 20


@pytest.mark.django_db
def test_csv_imports():
    words = io.BytesIO("word,category\nكهكشان,space\nکهکشان,space\nx1,bad\nآسمان,nature\n".encode())
    assert importer.import_words_csv(words) == 2
    assert WordEntry.objects.filter(word="کهکشان").exists()

    questions = io.StringIO(
        "category,text,option1,option2,option3,option4,correct,difficulty\n"
        "general,دو به‌علاوه‌ی دو؟,۳,۴,۵,۶,2,1\n"
    )
    assert importer.import_questions_csv(questions) == 1
    q = Question.objects.get()
    assert q.options[q.correct_index] == "۴"

    bad = io.StringIO("category,text,option1,option2,correct\nnope,سوال,الف,ب,1\n")
    with pytest.raises(importer.ImportError_):
        importer.import_questions_csv(bad)
    with pytest.raises(importer.ImportError_):
        importer.import_questions_csv(io.StringIO("text\nفقط متن\n"))

    puzzles = io.StringIO("emojis,answer,alt_answers\n🌞🌻,آفتابگردان,گل آفتابگردان|sunflower\n")
    assert importer.import_puzzles_csv(puzzles) == 1
    assert EmojiPuzzle.objects.get().alt_answers == ["گل آفتابگردان", "sunflower"]

    sentences = io.StringIO("text\nاین  یک   جمله است\nاین یک جمله است\n")
    assert importer.import_sentences_csv(sentences) == 1


@pytest.mark.django_db(transaction=True)
async def test_db_content_provider():
    provider = DbContentProvider()
    with pytest.raises(NoContent):
        await provider.random_words(3)
    from asgiref.sync import sync_to_async

    await sync_to_async(call_command)("seed_content")
    words = await provider.random_words(5, 4, 6)
    assert len(words) == 5 and all(4 <= len(w) <= 6 for w in words)
    assert await provider.is_valid_word("كتاب")
    assert not await provider.is_valid_word("قققق")
    assert await provider.has_word_starting_with("ک", set())
    questions = await provider.questions("freefire", 5)
    assert len(questions) == 5 and all("options" in q for q in questions)
    assert len(await provider.questions("mixed", 7)) == 7
    assert len(await provider.emoji_puzzles(4)) == 4
    assert len(await provider.sentences(4)) == 4
