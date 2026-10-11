from django.contrib import admin, messages
from django.http import JsonResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from core.admin_utils import CsvImportMixin
from core.textutils import fa_num

from . import config
from .catalog import ARCADE_CATEGORIES, catalog, defaults
from .content import importer
from .engine import services
from .models import (
    ACTIVE_STATUSES,
    EmojiPuzzle,
    GameSetting,
    Match,
    MatchPlayer,
    Question,
    TypingSentence,
    WordEntry,
)


class MatchPlayerInline(admin.TabularInline):
    model = MatchPlayer
    fields = ("user", "score", "rank", "prize", "paid_fee", "refunded", "xp_gained", "joined_at")
    readonly_fields = fields
    extra = 0
    max_num = 0
    can_delete = False


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("id", "game_title", "group", "status", "entry_fee", "pot", "player_count", "creator", "created_at")
    list_filter = ("status", "game_type", "created_at")
    search_fields = ("group__title", "group__chat_id", "creator__tg_id", "token")
    list_select_related = ("group", "creator")
    date_hierarchy = "created_at"
    inlines = [MatchPlayerInline]
    actions = ["cancel_and_refund"]

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="بازی")
    def game_title(self, obj):
        info = catalog(include_disabled=True).get(obj.game_type)
        return f"{info.emoji} {info.title_fa}" if info else obj.game_type

    @admin.display(description="بازیکن‌ها")
    def player_count(self, obj):
        return obj.players.count()

    @admin.action(description="لغو مسابقه و برگشت ورودی‌ها")
    def cancel_and_refund(self, request, queryset):
        cancelled = refunded = 0
        for match in queryset.filter(status__in=ACTIVE_STATUSES):
            _, entries = services.cancel_match(match.pk, "admin")
            cancelled += 1
            refunded += sum(1 for e in entries if e.paid_fee)
        skipped = queryset.count() - cancelled
        level = messages.SUCCESS if cancelled else messages.WARNING
        self.message_user(
            request,
            f"{cancelled} مسابقه لغو شد و ورودی {refunded} بازیکن برگشت."
            + (f" ({skipped} مسابقه‌ی تمام‌شده/لغوشده نادیده گرفته شد.)" if skipped else ""),
            level,
        )


@admin.register(Question)
class QuestionAdmin(CsvImportMixin, admin.ModelAdmin):
    list_display = ("text", "category", "difficulty", "is_active")
    list_filter = ("category", "difficulty", "is_active")
    search_fields = ("text",)
    list_editable = ("is_active",)
    csv_import_func = staticmethod(importer.import_questions_csv)
    csv_columns = "category,text,option1,option2,option3,option4,correct,difficulty"


@admin.register(WordEntry)
class WordEntryAdmin(CsvImportMixin, admin.ModelAdmin):
    list_display = ("word", "category", "length", "difficulty")
    list_filter = ("category", "length", "difficulty")
    search_fields = ("word",)
    readonly_fields = ("length",)
    csv_import_func = staticmethod(importer.import_words_csv)
    csv_columns = "word,category"


@admin.register(EmojiPuzzle)
class EmojiPuzzleAdmin(CsvImportMixin, admin.ModelAdmin):
    list_display = ("emojis", "answer", "is_active")
    list_filter = ("is_active",)
    search_fields = ("answer",)
    csv_import_func = staticmethod(importer.import_puzzles_csv)
    csv_columns = "emojis,answer,alt_answers   (جایگزین‌ها با | جدا شوند)"


@admin.register(TypingSentence)
class TypingSentenceAdmin(CsvImportMixin, admin.ModelAdmin):
    list_display = ("text", "is_active")
    list_filter = ("is_active",)
    search_fields = ("text",)
    csv_import_func = staticmethod(importer.import_sentences_csv)
    csv_columns = "text"


@admin.register(GameSetting)
class GameSettingAdmin(admin.ModelAdmin):
    """فعال/غیرفعال کردن هر بازی و کم/زیاد کردن تعداد شرکت‌کننده‌ها.

    دکمه‌های − و + صفحه‌ی لیست بلافاصله ذخیره می‌شوند (``adjust_view``). مقدار همیشه در بازه‌ی
    مجاز همان بازی می‌ماند؛ مثلاً شطرنج و دوز همیشه دونفره‌اند.
    """

    list_display = ("game", "kind", "enabled_switch", "min_stepper", "max_stepper", "allowed_range", "updated_at")
    list_display_links = ("game",)
    fields = ("game", "kind", "allowed_range", "default_range", "is_enabled", "min_players", "max_players")
    readonly_fields = ("game", "kind", "allowed_range", "default_range")
    actions = ["max_plus_1", "max_minus_1", "max_plus_5", "max_minus_5", "reset_defaults", "enable", "disable"]
    change_list_template = "admin/game_settings_change_list.html"
    ordering = ("id",)

    class Media:
        js = ("panel/game_settings.js",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        config.sync_rows()
        return super().get_queryset(request).filter(game_key__in=list(defaults()))

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, {**(extra_context or {}), "title": "تنظیمات بازی‌ها و تعداد شرکت‌کننده"})

    def get_urls(self):
        return [
            path(
                "<int:pk>/adjust/",
                self.admin_site.admin_view(require_POST(self.adjust_view)),
                name="games_gamesetting_adjust",
            ),
            *super().get_urls(),
        ]

    # ------------------------------------------------------------ ستون‌ها
    @staticmethod
    def _info(obj):
        return defaults().get(obj.game_key)

    @admin.display(description="بازی", ordering="id")
    def game(self, obj):
        info = self._info(obj)
        if info is None:
            return obj.game_key
        return format_html('<span class="gs-game"><i>{}</i> {}</span>', info.emoji, info.title_fa)

    @admin.display(description="نوع")
    def kind(self, obj):
        info = self._info(obj)
        if info is None:
            return "—"
        return f"آرکید · {ARCADE_CATEGORIES.get(info.category, '')}" if info.is_arcade else "داخل گروه"

    @admin.display(description="بازه‌ی مجاز")
    def allowed_range(self, obj):
        info = self._info(obj)
        if info is None:
            return "—"
        if info.fixed_players:
            return f"همیشه {fa_num(info.floor)} نفر"
        return f"{fa_num(info.floor)} تا {fa_num(info.ceiling)} نفر"

    @admin.display(description="پیش‌فرض")
    def default_range(self, obj):
        info = self._info(obj)
        return f"{fa_num(info.default_min)} تا {fa_num(info.default_max)} نفر" if info else "—"

    def _adjust_url(self, obj) -> str:
        return reverse("admin:games_gamesetting_adjust", args=[obj.pk])

    def _stepper(self, obj, field: str, value: int):
        info = self._info(obj)
        if info is None:
            return "—"
        if info.fixed_players:
            return format_html('<span class="gs-fixed">🔒 {} نفر</span>', fa_num(value))
        lo = info.floor if field == "min" else obj.min_players
        hi = obj.max_players if field == "min" else info.ceiling
        return format_html(
            '<span class="gs-stepper" data-url="{}" data-field="{}">'
            '<button type="button" data-delta="-1" title="کم کردن"{}>−</button>'
            "<output>{}</output>"
            '<button type="button" data-delta="1" title="زیاد کردن"{}>+</button></span>',
            self._adjust_url(obj),
            field,
            mark_safe(" disabled") if value <= lo else "",
            fa_num(value),
            mark_safe(" disabled") if value >= hi else "",
        )

    @admin.display(description="حداقل شرکت‌کننده", ordering="min_players")
    def min_stepper(self, obj):
        return self._stepper(obj, "min", obj.min_players)

    @admin.display(description="حداکثر شرکت‌کننده", ordering="max_players")
    def max_stepper(self, obj):
        return self._stepper(obj, "max", obj.max_players)

    @admin.display(description="وضعیت", ordering="is_enabled")
    def enabled_switch(self, obj):
        return format_html(
            '<button type="button" class="gs-switch{}" data-url="{}" title="فعال / غیرفعال">'
            "<i></i><span>{}</span></button>",
            " on" if obj.is_enabled else "",
            self._adjust_url(obj),
            "فعال" if obj.is_enabled else "غیرفعال",
        )

    # ------------------------------------------------------------ تغییر فوری از صفحه‌ی لیست
    @staticmethod
    def _shift(obj, info, field: str, delta: int) -> bool:
        """مقدار را در بازه‌ی مجاز جابه‌جا می‌کند؛ اگر تغییری نکرد ``False`` برمی‌گرداند."""
        before = (obj.min_players, obj.max_players)
        if field == "min":
            obj.min_players = max(info.floor, min(obj.max_players, obj.min_players + delta))
        else:
            obj.max_players = max(obj.min_players, info.floor, min(info.ceiling, obj.max_players + delta))
        return (obj.min_players, obj.max_players) != before

    def adjust_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if obj is None or not self.has_change_permission(request, obj):
            return JsonResponse({"ok": False}, status=403)
        info = self._info(obj)
        if info is None:
            return JsonResponse({"ok": False}, status=404)
        field = request.POST.get("field", "")
        if field == "enabled":
            obj.is_enabled = not obj.is_enabled
            obj.save(update_fields=["is_enabled", "updated_at"])
        elif field in ("min", "max"):
            try:
                delta = max(-10, min(10, int(request.POST.get("delta", "0"))))
            except ValueError:
                return JsonResponse({"ok": False}, status=400)
            if self._shift(obj, info, field, delta):
                obj.save(update_fields=["min_players", "max_players", "updated_at"])
        else:
            return JsonResponse({"ok": False}, status=400)
        return JsonResponse(
            {
                "ok": True,
                "enabled": obj.is_enabled,
                "min": obj.min_players,
                "max": obj.max_players,
                "floor": info.floor,
                "ceiling": info.ceiling,
            }
        )

    # ------------------------------------------------------------ اکشن‌های گروهی
    def _bulk_shift(self, request, queryset, delta: int):
        changed = 0
        for obj in queryset:
            info = self._info(obj)
            if info is not None and self._shift(obj, info, "max", delta):
                obj.save(update_fields=["min_players", "max_players", "updated_at"])
                changed += 1
        skipped = queryset.count() - changed
        note = f" ({fa_num(skipped)} بازی به سقف/کف مجاز رسیده بود.)" if skipped else ""
        self.message_user(request, f"حداکثر شرکت‌کننده‌ی {fa_num(changed)} بازی تغییر کرد.{note}")

    @admin.action(description="حداکثر شرکت‌کننده: ۱ نفر بیشتر")
    def max_plus_1(self, request, queryset):
        self._bulk_shift(request, queryset, 1)

    @admin.action(description="حداکثر شرکت‌کننده: ۱ نفر کمتر")
    def max_minus_1(self, request, queryset):
        self._bulk_shift(request, queryset, -1)

    @admin.action(description="حداکثر شرکت‌کننده: ۵ نفر بیشتر")
    def max_plus_5(self, request, queryset):
        self._bulk_shift(request, queryset, 5)

    @admin.action(description="حداکثر شرکت‌کننده: ۵ نفر کمتر")
    def max_minus_5(self, request, queryset):
        self._bulk_shift(request, queryset, -5)

    @admin.action(description="برگرداندن تعداد شرکت‌کننده به پیش‌فرض")
    def reset_defaults(self, request, queryset):
        for obj in queryset:
            info = self._info(obj)
            if info is not None:
                obj.min_players, obj.max_players = info.default_min, info.default_max
                obj.save(update_fields=["min_players", "max_players", "updated_at"])
        self.message_user(request, f"{fa_num(queryset.count())} بازی به پیش‌فرض برگشت.")

    @admin.action(description="فعال کردن بازی‌های انتخاب‌شده")
    def enable(self, request, queryset):
        for obj in queryset.filter(is_enabled=False):
            obj.is_enabled = True
            obj.save(update_fields=["is_enabled", "updated_at"])
        self.message_user(request, "بازی‌های انتخاب‌شده فعال شدند.")

    @admin.action(description="غیرفعال کردن بازی‌های انتخاب‌شده")
    def disable(self, request, queryset):
        for obj in queryset.filter(is_enabled=True):
            obj.is_enabled = False
            obj.save(update_fields=["is_enabled", "updated_at"])
        self.message_user(request, "بازی‌های انتخاب‌شده غیرفعال شدند.", messages.WARNING)
