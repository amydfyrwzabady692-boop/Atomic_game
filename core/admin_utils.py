"""ابزارهای مشترک پنل ادمین: مدل فقط‌خواندنی و import از CSV."""

from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse


class ReadOnlyAdmin(admin.ModelAdmin):
    """بدون افزودن، ویرایش و حذف (مثلاً برای ledger سکه)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CsvImportMixin:
    """دکمه‌ی «Import از CSV» را به صفحه‌ی لیست اضافه می‌کند.

    زیرکلاس باید ``csv_import_func`` (تابعی که فایل می‌گیرد و تعداد ردیف‌های اضافه‌شده را
    برمی‌گرداند) و ``csv_columns`` (راهنمای ستون‌ها) را تعیین کند.
    """

    change_list_template = "admin/csv_change_list.html"
    csv_import_func = None
    csv_columns = ""

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name
        return [
            path("import-csv/", self.admin_site.admin_view(self.import_csv_view), name="{}_{}_import_csv".format(*info)),
            *super().get_urls(),
        ]

    def import_csv_view(self, request):
        from games.content.importer import ImportError_

        opts = self.model._meta
        changelist = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
        if request.method == "POST":
            upload = request.FILES.get("file")
            if upload is None:
                messages.error(request, "فایلی انتخاب نشده است.")
            elif upload.size > 5 * 1024 * 1024:
                messages.error(request, "حجم فایل بیشتر از ۵ مگابایت است.")
            else:
                try:
                    added = type(self).csv_import_func(upload)
                except ImportError_ as exc:
                    messages.error(request, f"خطا در فایل: {exc}")
                except UnicodeDecodeError:
                    messages.error(request, "کدگذاری فایل باید UTF-8 باشد.")
                else:
                    messages.success(request, f"{added} ردیف جدید اضافه شد (ردیف‌های تکراری نادیده گرفته شدند).")
                    return redirect(changelist)
        context = {
            **self.admin_site.each_context(request),
            "opts": opts,
            "title": f"Import از CSV — {opts.verbose_name_plural}",
            "columns": self.csv_columns,
            "changelist_url": changelist,
        }
        return render(request, "admin/csv_import.html", context)
