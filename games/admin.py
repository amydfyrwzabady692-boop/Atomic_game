from django.contrib import admin, messages

from core.admin_utils import CsvImportMixin

from .catalog import catalog
from .content import importer
from .engine import services
from .models import ACTIVE_STATUSES, EmojiPuzzle, Match, MatchPlayer, Question, TypingSentence, WordEntry


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
        info = catalog().get(obj.game_type)
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
