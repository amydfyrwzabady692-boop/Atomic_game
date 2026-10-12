"""context و محتوای ساختگی برای تست منطق بازی‌ها بدون تلگرام."""

import random

from games.engine.base import IncomingCallback, IncomingMessage, Player


class FakeContent:
    def __init__(self, words=None, questions=None, puzzles=None, sentences=None):
        self.words = words or ["کتاب", "باران", "نان", "نمک", "کلاه", "هوا", "اردک", "کبوتر", "رود", "دریا"]
        self._questions = questions or [
            {"text": f"سوال {i}", "options": ["الف", "ب", "ج", "د"], "correct_index": i % 4} for i in range(20)
        ]
        self._puzzles = puzzles or [
            {"emojis": "🦁👑", "answer": "شیر شاه", "alt_answers": ["شیرشاه", "lion king"]},
            {"emojis": "🕷👨", "answer": "مرد عنکبوتی", "alt_answers": ["اسپایدرمن"]},
        ]
        self._sentences = sentences or ["زندگی زیباست", "امروز هوا خوب است"]

    async def random_words(self, count, min_len=3, max_len=8):
        pool = [w for w in self.words if min_len <= len(w) <= max_len] or self.words
        return [pool[i % len(pool)] for i in range(count)]

    async def is_valid_word(self, word):
        return word in self.words

    async def has_word_starting_with(self, letter, exclude):
        return any(w.startswith(letter) and w not in exclude for w in self.words)

    async def questions(self, category, count):
        return [self._questions[i % len(self._questions)] for i in range(count)]

    async def emoji_puzzles(self, count):
        return [self._puzzles[i % len(self._puzzles)] for i in range(count)]

    async def sentences(self, count):
        return [self._sentences[i % len(self._sentences)] for i in range(count)]


class FakeContext:
    """همه‌ی خروجی‌ها را ضبط می‌کند و تایمرها را دستی اجرا می‌کند."""

    def __init__(self, n_players=3, options=None, seed=1, content=None, dice=None):
        self.players = [Player(user_id=i, tg_id=1000 + i, name=f"بازیکن{i}") for i in range(1, n_players + 1)]
        self.options = options or {}
        self.rng = random.Random(seed)
        self.content = content or FakeContent()
        self.clock = 1000.0
        self.sent: list[dict] = []
        self.edits: list[dict] = []
        self.flashes: list[str] = []
        self.timers: dict[str, tuple[float, object]] = {}
        self.ended = False
        self.dice_values = list(dice or [])
        self._msg_id = 100

    # ----------------------------------------------------- GameContext
    def now(self):
        return self.clock

    async def send(self, text, buttons=None):
        self._msg_id += 1
        self.sent.append({"id": self._msg_id, "text": text, "buttons": buttons})
        return self._msg_id

    async def edit(self, message_id, text, buttons=None, urgent=False):
        self.edits.append({"id": message_id, "text": text, "buttons": buttons})

    async def send_photo(self, image, caption="", buttons=None):
        self._msg_id += 1
        self.sent.append({"id": self._msg_id, "photo": image, "text": caption, "buttons": buttons})
        return self._msg_id

    async def edit_photo(self, message_id, image, caption="", buttons=None):
        self.edits.append({"id": message_id, "photo": image, "text": caption, "buttons": buttons})

    async def send_dice(self, emoji):
        value = self.dice_values.pop(0) if self.dice_values else 3
        self.sent.append({"id": 0, "dice": emoji, "value": value, "text": "", "buttons": None})
        return value

    async def flash(self, text, seconds=6):
        self.flashes.append(text)

    def set_timer(self, name, seconds, callback):
        self.timers[name] = (self.clock + seconds, callback)

    def cancel_timer(self, name):
        self.timers.pop(name, None)

    async def end_game(self):
        self.ended = True
        self.timers.clear()

    # ----------------------------------------------------- ابزار تست
    @property
    def last_text(self):
        return self.sent[-1]["text"] if self.sent else ""

    def all_text(self):
        return "\n".join(m["text"] for m in self.sent) + "\n".join(e["text"] for e in self.edits)

    async def fire(self, name):
        """تایمر ``name`` را همین حالا اجرا می‌کند (ساعت را هم جلو می‌برد)."""
        when, callback = self.timers.pop(name)
        self.clock = max(self.clock, when)
        await callback()

    async def advance(self, seconds):
        """ساعت را جلو می‌برد و تایمرهای سررسیده را به ترتیب اجرا می‌کند."""
        target = self.clock + seconds
        while True:
            due = [(when, name) for name, (when, _) in self.timers.items() if when <= target]
            if not due:
                break
            when, name = min(due)
            _, callback = self.timers.pop(name)
            self.clock = max(self.clock, when)
            await callback()
        self.clock = target

    def msg(self, player_index, text):
        return IncomingMessage(player=self.players[player_index], text=text, message_id=0, date=self.clock)

    def cb(self, player_index, data, message_id=0):
        answers = []

        async def answer(text="", alert=False):
            answers.append((text, alert))

        player = self.players[player_index] if player_index is not None else None
        cb = IncomingCallback(player=player, data=data, message_id=message_id, answer=answer)
        cb.answers = answers
        return cb
