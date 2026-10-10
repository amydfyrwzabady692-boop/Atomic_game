"""دسترسی بازی‌ها به بانک محتوا (کلمات، سوال‌ها، پازل‌ها، جمله‌ها) از دیتابیس."""

from core.textutils import normalize_fa

from ..models import EmojiPuzzle, Question, TypingSentence, WordEntry


class NoContent(Exception):
    """محتوای کافی برای اجرای بازی در دیتابیس نیست (``seed_content`` اجرا نشده؟)."""


class DbContentProvider:
    async def random_words(self, count: int, min_len: int = 3, max_len: int = 8) -> list[str]:
        qs = WordEntry.objects.filter(length__gte=min_len, length__lte=max_len).order_by("?")[:count]
        words = [w.word async for w in qs]
        if len(words) < count:
            raise NoContent("words")
        return words

    async def is_valid_word(self, word: str) -> bool:
        return await WordEntry.objects.filter(word=normalize_fa(word, keep_spaces=False)).aexists()

    async def has_word_starting_with(self, letter: str, exclude: set[str]) -> bool:
        return await WordEntry.objects.filter(word__startswith=letter).exclude(word__in=exclude).aexists()

    async def questions(self, category: str | None, count: int) -> list[dict]:
        qs = Question.objects.filter(is_active=True)
        if category and category != "mixed":
            qs = qs.filter(category=category)
        items = [
            {"text": q.text, "options": list(q.options), "correct_index": q.correct_index}
            async for q in qs.order_by("?")[:count]
        ]
        if len(items) < count:
            raise NoContent("questions")
        return items

    async def emoji_puzzles(self, count: int) -> list[dict]:
        qs = EmojiPuzzle.objects.filter(is_active=True).order_by("?")[:count]
        items = [{"emojis": p.emojis, "answer": p.answer, "alt_answers": list(p.alt_answers)} async for p in qs]
        if len(items) < count:
            raise NoContent("emoji")
        return items

    async def sentences(self, count: int) -> list[str]:
        qs = TypingSentence.objects.filter(is_active=True).order_by("?")[:count]
        items = [s.text async for s in qs]
        if len(items) < count:
            raise NoContent("sentences")
        return items
