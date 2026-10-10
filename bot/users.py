"""ثبت/به‌روزرسانی کاربران و گروه‌ها و بررسی ادمین بودن."""

from telegram.constants import ChatMemberStatus

from core.models import TelegramGroup, TelegramUser
from core.redis import get_redis

from .db import db
from .tg import tg_call


@db
def ensure_user(tg_user) -> TelegramUser:
    """کاربر تلگرام را در DB پیدا می‌کند یا می‌سازد و نام/یوزرنیم را به‌روز نگه می‌دارد."""
    first_name = (tg_user.first_name or "")[:128]
    username = (tg_user.username or "")[:64]
    user, created = TelegramUser.objects.get_or_create(
        tg_id=tg_user.id, defaults={"first_name": first_name, "username": username}
    )
    if not created and (user.first_name != first_name or user.username != username):
        user.first_name, user.username = first_name, username
        user.save(update_fields=["first_name", "username"])
    return user


@db
def ensure_group(chat) -> TelegramGroup:
    title = (chat.title or "")[:255]
    group, created = TelegramGroup.objects.get_or_create(chat_id=chat.id, defaults={"title": title})
    if not created and (group.title != title or not group.is_active):
        group.title, group.is_active = title, True
        group.save(update_fields=["title", "is_active"])
    return group


@db
def deactivate_group(chat_id: int) -> None:
    TelegramGroup.objects.filter(chat_id=chat_id).update(is_active=False)


@db
def find_user(ref: str) -> TelegramUser | None:
    """کاربر را با آیدی عددی یا @username پیدا می‌کند."""
    ref = ref.strip()
    if ref.startswith("@"):
        return TelegramUser.objects.filter(username__iexact=ref[1:]).first()
    if ref.lstrip("-").isdigit():
        return TelegramUser.objects.filter(tg_id=int(ref)).first()
    return None


async def is_group_admin(bot, chat_id: int, tg_id: int) -> bool:
    """با ``getChatMember`` بررسی می‌کند؛ نتیجه ۶۰ ثانیه کش می‌شود."""
    redis = get_redis()
    key = f"admin:{chat_id}:{tg_id}"
    cached = await redis.get(key)
    if cached is not None:
        return cached == "1"
    member = await tg_call(bot.get_chat_member, chat_id, tg_id)
    is_admin = member is not None and member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    await redis.set(key, "1" if is_admin else "0", ex=60)
    return is_admin
