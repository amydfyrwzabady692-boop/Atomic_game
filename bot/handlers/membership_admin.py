"""پنل /admin: جوین اجباری (کانال‌ها) و کلیدهای API ربات‌های دیگر.

کانال‌ها با دسترسی «تنظیمات» و کلیدهای API (که رمزند) با دسترسی «مدیران» مدیریت می‌شوند.
"""

import logging
import re
from datetime import UTC, datetime
from html import escape

from django.conf import settings
from django.db.models import Max
from django.utils import timezone
from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import ContextTypes

from core import texts
from core.texts import fa_num
from membership import checks
from membership.models import ForcedChannel, PartnerKey, new_key

from .. import partner_hooks, ui
from ..db import db
from ..tg import tg_call
from .common import admin_permissions, answer, callback, reply

logger = logging.getLogger(__name__)

SECTION_PERMISSION = {"fj": "settings", "api": "admins"}
STEPS = {"fj_add": "settings", "api_name": "admins", "api_hook": "admins"}
USERNAME = re.compile(r"@?([A-Za-z][A-Za-z0-9_]{3,31})")


def _btn(text: str, data: str | None = None, style: str = "", url: str | None = None):
    return ui.button(text, None if url else data, url=url, style=style)


def _ago(moment) -> str:
    if moment is None:
        return texts.ADMIN_API_NEVER
    seconds = max(0, int((timezone.now() - moment).total_seconds()))
    if seconds < 3600:
        return f"{fa_num(max(1, seconds // 60))} دقیقه پیش"
    if seconds < 86400:
        return f"{fa_num(seconds // 3600)} ساعت پیش"
    return f"{fa_num(seconds // 86400)} روز پیش"


# ================================================================== جوین اجباری
@db
def _channels() -> list[ForcedChannel]:
    return list(ForcedChannel.objects.all())


@db
def _channel(pk: int) -> ForcedChannel | None:
    return ForcedChannel.objects.filter(pk=pk).first()


def _fj_screen(rows: list[ForcedChannel]):
    lines = "\n".join(
        texts.ADMIN_FJ_ROW.format(
            n=fa_num(i + 1), state="✅" if row.is_active else "⏸", title=escape(row.title or row.handle), handle=escape(row.handle)
        )
        for i, row in enumerate(rows)
    )
    buttons = [[_btn(f"{fa_num(i + 1)}. {row.title or row.handle}"[:48], f"adm:fj:show:{row.pk}", ui.PRIMARY)] for i, row in enumerate(rows)]
    buttons.append([_btn(texts.ADMIN_FJ_ADD_BTN, "adm:fj:add", ui.SUCCESS)])
    buttons.append([_btn(texts.ADMIN_BACK_TO_PANEL_BTN, "adm:home")])
    return texts.ADMIN_FJ.format(rows=lines or texts.ADMIN_FJ_EMPTY), InlineKeyboardMarkup(buttons)


async def _bot_id(context) -> int:
    if not context.bot_data.get("bot_id"):
        me = await context.bot.get_me()
        context.bot_data["bot_id"] = me.id
    return context.bot_data["bot_id"]


async def _bot_is_admin(context, chat_id: int) -> bool | None:
    member = await tg_call(context.bot.get_chat_member, chat_id, await _bot_id(context), retries=1)
    if member is None:
        return None
    return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)


async def _fj_detail(context, row: ForcedChannel):
    is_admin = await _bot_is_admin(context, row.chat_id)
    count = await tg_call(context.bot.get_chat_member_count, row.chat_id, retries=1)
    text = texts.ADMIN_FJ_DETAIL.format(
        title=escape(row.title or row.handle),
        chat_id=row.chat_id,
        link=escape(row.link) or "—",
        state=texts.ADMIN_FJ_ACTIVE if row.is_active else texts.ADMIN_FJ_PAUSED,
        bot=texts.ADMIN_FJ_BOT_ADMIN if is_admin else texts.ADMIN_FJ_BOT_NOT_ADMIN,
        members=fa_num(count) if isinstance(count, int) else texts.ADMIN_FJ_UNKNOWN,
    )
    toggle = texts.ADMIN_FJ_PAUSE_BTN if row.is_active else texts.ADMIN_FJ_RESUME_BTN
    rows = [
        [_btn(toggle, f"adm:fj:toggle:{row.pk}", ui.PRIMARY), _btn(texts.ADMIN_FJ_RECHECK_BTN, f"adm:fj:show:{row.pk}")],
        [_btn(texts.ADMIN_FJ_DEL_BTN, f"adm:fj:del:{row.pk}", ui.DANGER)],
        [_btn(texts.BACK_BTN, "adm:fj:list")],
    ]
    if row.link:
        rows.insert(0, [_btn("🔗 " + (row.title or row.handle)[:40], url=row.link)])
    return text, InlineKeyboardMarkup(rows)


@db
def _toggle_channel(pk: int) -> ForcedChannel | None:
    row = ForcedChannel.objects.filter(pk=pk).first()
    if row is not None:
        row.is_active = not row.is_active
        row.save(update_fields=["is_active"])
    checks.forget_channels()
    return row


@db
def _delete_channel(pk: int) -> None:
    ForcedChannel.objects.filter(pk=pk).delete()
    checks.forget_channels()


@db
def _save_channel(chat, link: str, admin_tg_id: int) -> tuple[ForcedChannel, bool]:
    position = (ForcedChannel.objects.aggregate(m=Max("position"))["m"] or 0) + 1
    row, created = ForcedChannel.objects.get_or_create(
        chat_id=chat.id,
        defaults={
            "title": (chat.title or "")[:255],
            "username": chat.username or "",
            "invite_link": link[:255],
            "position": position,
            "added_by": admin_tg_id,
        },
    )
    if not created:
        row.title, row.username, row.is_active = (chat.title or row.title)[:255], chat.username or "", True
        row.invite_link = link[:255] or row.invite_link
        row.save(update_fields=["title", "username", "invite_link", "is_active"])
    checks.forget_channels()
    return row, created


def chat_ref(message) -> int | str | None:
    """کانال از پیام مدیر: پیام فورواردشده، آیدی عددی، ‎@یوزرنیم یا لینک عمومی t.me."""
    origin = getattr(message, "forward_origin", None)
    chat = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
    if chat is not None:
        return chat.id
    text = (message.text or "").strip()
    if "t.me/" in text:
        tail = text.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        if tail.startswith("+") or "joinchat" in text:
            return None  # لینک دعوت خصوصی را ربات نمی‌تواند باز کند؛ فوروارد یا آیدی عددی لازم است
        text = tail
    if re.fullmatch(r"-?\d{5,20}", text):
        return int(text)
    match = USERNAME.fullmatch(text)
    return "@" + match.group(1) if match else None


async def _add_channel(update: Update, context, user, flow: dict) -> None:
    keep = InlineKeyboardMarkup([[_btn(texts.BACK_BTN, "adm:fj:list")]])
    ref = chat_ref(update.effective_message)
    if ref is None:
        await reply(update, texts.ADMIN_FJ_BAD_REF, keep)
        return
    chat = await tg_call(context.bot.get_chat, ref, retries=1)
    if chat is None:
        await reply(update, texts.ADMIN_FJ_NOT_FOUND, keep)
        return
    title = escape(chat.title or str(chat.id))
    if chat.type not in (ChatType.CHANNEL, ChatType.GROUP, ChatType.SUPERGROUP):
        await reply(update, texts.ADMIN_FJ_BAD_TYPE, keep)
        return
    if not await _bot_is_admin(context, chat.id):
        await reply(update, texts.ADMIN_FJ_NOT_ADMIN.format(title=title), keep)
        return
    link = ""
    if not chat.username:
        link = getattr(chat, "invite_link", None) or await tg_call(context.bot.export_chat_invite_link, chat.id, retries=1) or ""
        if not isinstance(link, str) or not link:
            await reply(update, texts.ADMIN_FJ_NO_LINK.format(title=title), keep)
            return
    row, created = await _save_channel(chat, link, user.tg_id)
    context.user_data.pop("admin_flow", None)
    logger.info("forced channel saved", extra={"admin": user.tg_id, "chat": chat.id})
    note = (texts.ADMIN_FJ_ADDED if created else texts.ADMIN_FJ_EXISTS).format(title=title)
    text, markup = _fj_screen(await _channels())
    await reply(update, note + "\n\n" + text, markup)


# ================================================================== کلیدهای API ربات‌های دیگر
def api_base() -> str:
    base = settings.MINIAPP_BASE_URL.rstrip("/")
    return f"{base}/api/v1/" if base.startswith("https://") else ""


@db
def _keys() -> list[PartnerKey]:
    return list(PartnerKey.objects.all())


@db
def _key(pk: int) -> PartnerKey | None:
    return PartnerKey.objects.filter(pk=pk).first()


@db
def _update_key(pk: int, **fields) -> PartnerKey | None:
    PartnerKey.objects.filter(pk=pk).update(**fields)
    partner_hooks.forget_targets()
    return PartnerKey.objects.filter(pk=pk).first()


@db
def _create_key(name: str, admin_tg_id: int) -> PartnerKey:
    return PartnerKey.objects.create(name=name, created_by=admin_tg_id)


@db
def _delete_key(pk: int) -> None:
    PartnerKey.objects.filter(pk=pk).delete()
    partner_hooks.forget_targets()


def _api_screen(keys: list[PartnerKey]):
    lines = "\n".join(
        texts.ADMIN_API_ROW.format(
            n=fa_num(i + 1),
            state="✅" if key.is_active else "⏸",
            name=escape(key.name),
            used=_ago(key.last_used_at),
            hook=texts.ADMIN_API_ROW_HOOK if key.webhook_url else "",
        )
        for i, key in enumerate(keys)
    )
    buttons = [[_btn(f"{fa_num(i + 1)}. {key.name}"[:48], f"adm:api:show:{key.pk}", ui.PRIMARY)] for i, key in enumerate(keys)]
    buttons.append([_btn(texts.ADMIN_API_NEW_BTN, "adm:api:new", ui.SUCCESS)])
    buttons.append([_btn(texts.ADMIN_BACK_TO_PANEL_BTN, "adm:home")])
    base = escape(api_base()) or texts.ADMIN_API_NO_BASE
    return texts.ADMIN_API.format(base=base, rows=lines or texts.ADMIN_API_EMPTY), InlineKeyboardMarkup(buttons)


async def _api_detail(key: PartnerKey):
    last = await partner_hooks.last_result(key.pk)
    if last:
        moment = datetime.fromtimestamp(last["at"], tz=UTC)
        last_text = f"{escape(last['status'])} ({escape(last['event'])}، {_ago(moment)})"
    else:
        last_text = texts.ADMIN_API_NEVER
    text = texts.ADMIN_API_DETAIL.format(
        name=escape(key.name),
        state=texts.ADMIN_FJ_ACTIVE if key.is_active else texts.ADMIN_FJ_PAUSED,
        key=escape(key.key),
        hook=escape(key.webhook_url) or texts.ADMIN_API_NO_HOOK,
        last=last_text,
        used=_ago(key.last_used_at),
        base=escape(api_base() or "https://<domain>/api/v1/"),
    )
    hook_row = [_btn(texts.ADMIN_API_HOOK_BTN, f"adm:api:hook:{key.pk}", ui.PRIMARY)]
    if key.webhook_url:
        hook_row += [_btn(texts.ADMIN_API_TEST_BTN, f"adm:api:test:{key.pk}"), _btn(texts.ADMIN_API_UNHOOK_BTN, f"adm:api:unhook:{key.pk}")]
    toggle = texts.ADMIN_API_PAUSE_BTN if key.is_active else texts.ADMIN_API_RESUME_BTN
    rows = [
        hook_row,
        [_btn(toggle, f"adm:api:toggle:{key.pk}"), _btn(texts.ADMIN_API_ROTATE_BTN, f"adm:api:rotate:{key.pk}")],
        [_btn(texts.ADMIN_API_DEL_BTN, f"adm:api:del:{key.pk}", ui.DANGER)],
        [_btn(texts.BACK_BTN, "adm:api:list")],
    ]
    return text, InlineKeyboardMarkup(rows)


# ================================================================== دکمه‌ها
@callback
async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user, query):
    from .wallet import show_photo_or_text

    parts = query.data.split(":")
    section, action = parts[1], parts[2] if len(parts) > 2 else "list"
    arg = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    if SECTION_PERMISSION[section] not in await admin_permissions(user.tg_id):
        await answer(query, texts.ADMIN_NO_ACCESS, alert=True)
        return

    async def show(text, markup):
        await show_photo_or_text(update, context, query, text, markup)

    def confirm(text: str, yes: str, yes_data: str, back: str):
        return text, InlineKeyboardMarkup([[_btn(yes, yes_data, ui.DANGER)], [_btn(texts.BACK_BTN, back)]])

    flow = context.user_data
    if section == "fj":
        if action == "list":
            flow.pop("admin_flow", None)
            await answer(query)
            await show(*_fj_screen(await _channels()))
        elif action == "add":
            flow["admin_flow"] = {"step": "fj_add"}
            await answer(query)
            await show(texts.ADMIN_FJ_ASK, InlineKeyboardMarkup([[_btn(texts.BACK_BTN, "adm:fj:list")]]))
        elif action == "show":
            row = await _channel(arg)
            if row is None:
                await answer(query, texts.ADMIN_FJ_REMOVED)
                await show(*_fj_screen(await _channels()))
                return
            await answer(query)
            await show(*await _fj_detail(context, row))
        elif action == "toggle":
            row = await _toggle_channel(arg)
            if row is None:
                return
            state = texts.ADMIN_FJ_ACTIVE if row.is_active else texts.ADMIN_FJ_PAUSED
            await answer(query, texts.ADMIN_FJ_TOGGLED.format(state=state))
            await show(*await _fj_detail(context, row))
        elif action == "del":
            row = await _channel(arg)
            if row is None:
                return
            await answer(query)
            await show(*confirm(texts.ADMIN_FJ_DEL_SURE.format(title=escape(row.title or row.handle)), texts.ADMIN_DEL_SURE_BTN, f"adm:fj:delok:{row.pk}", f"adm:fj:show:{row.pk}"))
        elif action == "delok":
            await _delete_channel(arg)
            logger.info("forced channel removed", extra={"admin": user.tg_id, "row": arg})
            await answer(query, texts.ADMIN_FJ_REMOVED)
            await show(*_fj_screen(await _channels()))
        return

    # ---------------------------------------------------------- API
    if action == "list":
        flow.pop("admin_flow", None)
        await answer(query)
        await show(*_api_screen(await _keys()))
        return
    if action == "new":
        flow["admin_flow"] = {"step": "api_name"}
        await answer(query)
        await show(texts.ADMIN_API_ASK_NAME, InlineKeyboardMarkup([[_btn(texts.BACK_BTN, "adm:api:list")]]))
        return
    key = await _key(arg)
    if key is None:
        await answer(query, texts.ADMIN_API_REMOVED)
        await show(*_api_screen(await _keys()))
        return
    if action == "show":
        flow.pop("admin_flow", None)
        await answer(query)
    elif action == "hook":
        flow["admin_flow"] = {"step": "api_hook", "key": key.pk}
        await answer(query)
        await show(texts.ADMIN_API_ASK_HOOK, InlineKeyboardMarkup([[_btn(texts.BACK_BTN, f"adm:api:show:{key.pk}")]]))
        return
    elif action == "unhook":
        key = await _update_key(key.pk, webhook_url="")
        await answer(query, texts.ADMIN_API_SAVED)
    elif action == "test":
        if not key.webhook_url:
            await answer(query)
        else:
            body = partner_hooks.body_of("ping", context.bot_data.get("username") or settings.BOT_USERNAME, key=key.name)
            status = await partner_hooks.deliver(key.pk, key.key, key.webhook_url, "ping", body, retries=False)
            await answer(query, texts.ADMIN_API_TEST_RESULT.format(status=status), alert=True)
    elif action == "toggle":
        key = await _update_key(key.pk, is_active=not key.is_active)
        await answer(query, texts.ADMIN_API_SAVED)
    elif action == "rotate":
        await answer(query)
        await show(*confirm(texts.ADMIN_API_ROTATE_SURE.format(name=escape(key.name)), texts.ADMIN_API_ROTATE_SURE_BTN, f"adm:api:rotok:{key.pk}", f"adm:api:show:{key.pk}"))
        return
    elif action == "rotok":
        key = await _update_key(key.pk, key=new_key())
        logger.info("partner key rotated", extra={"admin": user.tg_id, "key": key.pk})
        await answer(query, texts.ADMIN_API_SAVED)
    elif action == "del":
        await answer(query)
        await show(*confirm(texts.ADMIN_API_DEL_SURE.format(name=escape(key.name)), texts.ADMIN_DEL_SURE_BTN, f"adm:api:delok:{key.pk}", f"adm:api:show:{key.pk}"))
        return
    elif action == "delok":
        await _delete_key(key.pk)
        logger.info("partner key removed", extra={"admin": user.tg_id, "key": key.pk})
        await answer(query, texts.ADMIN_API_REMOVED)
        await show(*_api_screen(await _keys()))
        return
    else:
        await answer(query)
    await show(*await _api_detail(key))


# ================================================================== پیام‌های مرحله‌ای پنل
async def flow_message(update: Update, context, user, flow: dict) -> bool:
    step = flow.get("step")
    text = (update.effective_message.text or "").strip()
    if step == "fj_add":
        await _add_channel(update, context, user, flow)
        return True
    if step == "api_name":
        if not 2 <= len(text) <= 64:
            await reply(update, texts.ADMIN_API_BAD_NAME)
            return True
        key = await _create_key(text, user.tg_id)
        context.user_data.pop("admin_flow", None)
        logger.info("partner key created", extra={"admin": user.tg_id, "key": key.pk})
        await reply(update, *await _api_detail(key))
        return True
    if step == "api_hook":
        if not re.fullmatch(r"https://[^\s/]+\.[^\s]+", text) or len(text) > 500:
            await reply(update, texts.ADMIN_API_BAD_HOOK)
            return True
        key = await _update_key(flow.get("key") or 0, webhook_url=text)
        context.user_data.pop("admin_flow", None)
        if key is None:
            await reply(update, texts.ADMIN_API_REMOVED)
            return True
        text, markup = await _api_detail(key)
        await reply(update, texts.ADMIN_API_SAVED + "\n\n" + text, markup)
        return True
    return False
