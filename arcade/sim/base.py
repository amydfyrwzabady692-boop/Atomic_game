from dataclasses import dataclass
from typing import ClassVar


@dataclass
class SimResult:
    score: int
    level: int = 0
    duration_ms: int = 0  # زمان بازی در لحظه‌ی پایان شبیه‌سازی
    over: bool = False  # بازی به پایان طبیعی (باخت/اتمام) رسیده؟
    cause: str = ""
    used_inputs: int = 0

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "level": self.level,
            "duration_ms": self.duration_ms,
            "over": self.over,
            "cause": self.cause,
        }


registry: dict[str, type["ArcadeSimulator"]] = {}


def register_simulator(cls: type["ArcadeSimulator"]) -> type["ArcadeSimulator"]:
    if not cls.key:
        raise ValueError(f"{cls.__name__} کلید ندارد")
    registry[cls.key] = cls
    return cls


class ArcadeSimulator:
    """پایه‌ی شبیه‌سازهای قطعی. زیرکلاس باید ``new_state`` و ``step`` را پیاده کند.

    قرارداد مشترک با ``core.js`` هر بازی:
    - زمان با گام ثابت ``TICK_MS`` جلو می‌رود و همه‌ی محاسبات عدد صحیح‌اند.
    - ورودی‌ها لیستی از ``[t_ms, ...]`` هستند؛ هر ورودی در تیک ``t_ms // TICK_MS`` و
      قبل از ``step`` همان تیک اعمال می‌شود.
    - شبیه‌سازی تا باخت/اتمام یا رسیدن به ``duration_ms`` ادامه دارد.
    """

    key: ClassVar[str] = ""
    title_fa: ClassVar[str] = ""
    emoji: ClassVar[str] = "🕹"
    description_fa: ClassVar[str] = ""
    howto_fa: ClassVar[str] = ""
    # قوانین کوتاه بازی (کنترل، امتیاز، پایان)؛ در صفحه‌ی شروع مینی‌اپ و دستور /rules نشان داده می‌شود
    rules_fa: ClassVar[list[str]] = []
    category: ClassVar[str] = "skill"  # speed | skill | stage
    suggested_minutes: ClassVar[int] = 5
    variant_title_fa: ClassVar[str] = ""
    variants: ClassVar[dict[str, str]] = {}

    TICK_MS: ClassVar[int] = 16
    MAX_DURATION_MS: ClassVar[int] = 10 * 60 * 1000
    MAX_INPUTS: ClassVar[int] = 20_000
    INPUT_ARITY: ClassVar[int] = 1  # تعداد عناصر هر ورودی (با احتساب زمان)
    # کمترین فاصله‌ی انسانی بین دو ورودی؛ صفر یعنی ورودی پیوسته است و بررسی نمی‌شود
    MIN_INPUT_GAP_MS: ClassVar[int] = 50

    # ------------------------------------------------------------ پیاده‌سازی بازی
    @classmethod
    def config(cls, seed: int, options: dict | None = None) -> dict:
        """داده‌ای که همراه seed به کلاینت داده می‌شود (مثلاً حالت بازی)."""
        return {"variant": (options or {}).get("variant", "")}

    @classmethod
    def new_state(cls, seed: int, config: dict) -> dict:
        raise NotImplementedError

    @classmethod
    def apply_input(cls, state: dict, event: list) -> None:
        raise NotImplementedError

    @classmethod
    def step(cls, state: dict) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------ ابزار تست (fixtureها)
    FIXTURE_MS: ClassVar[int] = 90_000  # سقف طول بازی‌های آزمایشی

    @classmethod
    def demo_policy(cls, rng, skill: int, options: dict | None = None):
        """بازیکن خودکار برای تست: تابع ``policy(state, tick) -> payload | None``."""
        raise NotImplementedError

    @classmethod
    def random_payload(cls, rng, state: dict) -> list:
        """یک ورودی تصادفیِ معتبر (بدون زمان)."""
        return []

    # ------------------------------------------------------------ اجرای مشترک
    @classmethod
    def validate_inputs(cls, inputs, duration_ms) -> str | None:
        """بررسی ساختاری لاگ ورودی. در صورت خطا کد دلیل را برمی‌گرداند."""
        if not isinstance(duration_ms, int) or isinstance(duration_ms, bool):
            return "bad_duration"
        if duration_ms < 0 or duration_ms > cls.MAX_DURATION_MS:
            return "bad_duration"
        if not isinstance(inputs, list) or len(inputs) > cls.MAX_INPUTS:
            return "bad_inputs"
        last = 0
        for event in inputs:
            if not isinstance(event, list) or len(event) != cls.INPUT_ARITY:
                return "bad_inputs"
            for value in event:
                if not isinstance(value, int) or isinstance(value, bool) or abs(value) > 10_000_000:
                    return "bad_inputs"
            if event[0] < last or event[0] > duration_ms:
                return "bad_inputs"
            last = event[0]
        return None

    @classmethod
    def simulate(cls, seed: int, inputs: list, duration_ms: int, options: dict | None = None) -> SimResult:
        config = cls.config(seed, options)
        state = cls.new_state(seed, config)
        tick_ms = cls.TICK_MS
        end_tick = min(duration_ms, cls.MAX_DURATION_MS) // tick_ms
        index, total = 0, len(inputs)
        tick = 0
        while True:
            while index < total and inputs[index][0] // tick_ms <= tick:
                if not state["over"]:
                    cls.apply_input(state, inputs[index])
                index += 1
            if state["over"] or tick >= end_tick:
                break
            cls.step(state)
            tick += 1
        return SimResult(
            score=int(state["score"]),
            level=int(state.get("level", 0)),
            duration_ms=tick * tick_ms,
            over=bool(state["over"]),
            cause=str(state.get("cause", "")),
            used_inputs=index,
        )
