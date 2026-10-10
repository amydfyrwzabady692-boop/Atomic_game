from django.core.management.base import BaseCommand
from django.db import transaction

from games.content.importer import seed_all
from games.models import EmojiPuzzle, Question, TypingSentence, WordEntry


class Command(BaseCommand):
    help = "محتوای اولیه را بارگذاری می‌کند: کلمات، سوال‌های کوییز، پازل‌های ایموجی، جمله‌های تایپ، فروشگاه و دستاوردها."

    def handle(self, *args, **options):
        with transaction.atomic():
            added = seed_all()
        for name, count in added.items():
            self.stdout.write(f"  + {name}: {count}")
        self.stdout.write(
            self.style.SUCCESS(
                f"OK - words={WordEntry.objects.count()} questions={Question.objects.count()} "
                f"emoji={EmojiPuzzle.objects.count()} sentences={TypingSentence.objects.count()}"
            )
        )
