"""پنل /admin: «👥 گروه‌های ربات» — ربات الان در چه گروه‌هایی است و هر گروه چه وضعی دارد.

فهرست از جدول گروه‌ها می‌آید (ربات هر گروهی را که در آن پیام یا دستوری ببیند ثبت می‌کند و وقتی بیرونش کنند
غیرفعالش می‌کند)؛ جزئیات هر گروه همان لحظه از تلگرام پرسیده می‌شود (نام، تعداد عضو، ادمین بودن ربات و لینک).
دیدن با دسترسی «آمار» و بیرون بردن ربات از گروه با دسترسی «تنظیمات» است.
"""

import logging
from datetime import timedelta
from html import escape

from django.db.models import Count, F, Max, Q
from django.utils import timezone
from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus
from telegram.ext import ContextTypes

from core import texts
from core.models import TelegramGroup
from core.texts import fa_num
from core.textutils import fa_date

from .. import ui
from ..db import db
from ..tg import tg_call
from .common import admin_permissions, answer, callback, manager_of

logger = logging.getLogger(__name__)

PAGE = 8
VIEW_PERMISSION = "stats"
LEAVE_PERMISSION = "settings"


def _btn(text: str, data: str | None = None, style: str = "", url: str | None = None):
    return ui.button(text, None if url else data, url=url, style=style)


def _short(title: str, limit: int = 28) -> str:
    title = (title or "").strip() or texts.ADMIN_GROUPS_NO_TITLE
    return title if len(title) <= limit else title[: limit - 1] + "…"


@db
def _groups(active: bool, page: int) -> tuple[list[TelegramGroup], int, dict]:
    week = timezone.now() - timedelta(days=7)
    rows = (
        TelegramGroup.objects.filter(is_active=active)
        .annotate(last=Max("matches__created_at"), week=Count("matches", filter=Q(matches__created_at__gte=week)))
        .order_by(F("last").desc(nulls_last=True), "-created_at", "-pk")  # گروه بی‌مسابقه ته فهرست
    )
    total = rows.count()
    counts = {
        "active": TelegramGroup.objects.filter(is_active=True).count(),
        "left": TelegramGroup.objects.filter(is_active=False).count(),
        "promo": TelegramGroup.objects.filter(is_active=True, promo_enabled=True).count(),
    }
    return list(rows[page * PAGE : (page + 1) * PAGE]), total, counts


@db
def _group(pk: int):
    group = TelegramGroup.objects.filter(pk=pk).first()
    if group is None:
        return None, {}
    week = timezone.now() - timedelta(days=7)
    stats = group.matches.aggregate(
        total=Count("pk"), week=Count("pk", filter=Q(created_at__gte=week)), last=Max("created_at")
    )
    return group, stats


@db
def _mark_left(pk: int) -> None:
    TelegramGroup.objects.filter(pk=pk).update(is_active=False)


def list_screen(groups: list[TelegramGroup], total: int, counts: dict, page: int, active: bool):
    pages = max(1, (total + PAGE - 1) // PAGE)
    lines = []
    for n, group in enumerate(groups, start=page * PAGE + 1):
        when = fa_date(timezone.localtime(group.last)) if group.last else texts.ADMIN_GROUPS_NO_MATCH
        lines.append(
            texts.ADMIN_GROUPS_ROW.format(n=fa_num(n), title=escape(_short(group.title, 40)), week=fa_num(group.week), last=when)
        )
    body = "\n".join(lines) if lines else (texts.ADMIN_GROUPS_EMPTY if active else texts.ADMIN_GROUPS_NONE_LEFT)
    text = (texts.ADMIN_GROUPS if active else texts.ADMIN_GROUPS_LEFT_TITLE).format(
        active=fa_num(counts["active"]), left=fa_num(counts["left"]), promo=fa_num(counts["promo"]),
        page=fa_num(page + 1), pages=fa_num(pages), body=body,
    )  # fmt: skip
    kind = "a" if active else "l"
    rows = [[_btn(f"{fa_num(n)}. {_short(g.title)}", f"adm:grp:show:{g.pk}:{kind}{page}", ui.PRIMARY)] for n, g in enumerate(groups, start=page * PAGE + 1)]
    nav = []
    if page > 0:
        nav.append(_btn(texts.ADMIN_PREV_BTN, f"adm:grp:{kind}:{page - 1}"))
    if page + 1 < pages:
        nav.append(_btn(texts.ADMIN_NEXT_BTN, f"adm:grp:{kind}:{page + 1}"))
    if nav:
        rows.append(nav)
    if active:
        rows.append([_btn(texts.ADMIN_GROUPS_LEFT_BTN.format(n=fa_num(counts["left"])), "adm:grp:l:0")])
    else:
        rows.append([_btn(texts.ADMIN_GROUPS_ACTIVE_BTN.format(n=fa_num(counts["active"])), "adm:grp:a:0")])
    rows.append([_btn(texts.ADMIN_REFRESH_BTN, f"adm:grp:{kind}:{page}"), _btn(texts.ADMIN_BACK_TO_PANEL_BTN, "adm:home")])
    return text, InlineKeyboardMarkup(rows)


async def _bot_id(context) -> int:
    if not context.bot_data.get("bot_id"):
        me = await context.bot.get_me()
        context.bot_data["bot_id"] = me.id
    return context.bot_data["bot_id"]


async def live_info(context, chat_id: int) -> dict:
    """نام، یوزرنیم، لینک، تعداد عضو و جایگاه ربات، همین لحظه از تلگرام (هر کدام ممکن است نامعلوم بماند)."""
    info = {"title": None, "link": None, "members": None, "role": None, "rights": []}
    chat = await tg_call(context.bot.get_chat, chat_id, retries=1)
    if chat is not None and chat is not True:
        info["title"] = getattr(chat, "title", None)
        username = getattr(chat, "username", None)
        # فقط لینک موجود خوانده می‌شود؛ exportChatInviteLink لینک فعلی گروه را باطل می‌کرد
        info["link"] = f"https://t.me/{username}" if username else getattr(chat, "invite_link", None)
    count = await tg_call(context.bot.get_chat_member_count, chat_id, retries=1)
    if isinstance(count, int) and not isinstance(count, bool):
        info["members"] = count
    member = await tg_call(context.bot.get_chat_member, chat_id, await _bot_id(context), retries=1)
    if member is not None and member is not True:
        info["role"] = member.status
        for name, label in texts.ADMIN_GROUP_RIGHTS.items():
            if getattr(member, name, False):
                info["rights"].append(label)
    return info


def role_text(info: dict) -> str:
    role = info.get("role")
    if role in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        rights = "، ".join(info["rights"]) if info["rights"] else texts.ADMIN_GROUP_NO_RIGHTS
        return texts.ADMIN_GROUP_ROLE_ADMIN.format(rights=rights)
    if role in (ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED):
        return texts.ADMIN_GROUP_ROLE_MEMBER
    if role in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        return texts.ADMIN_GROUP_ROLE_GONE
    return texts.ADMIN_GROUP_ROLE_UNKNOWN


def detail_screen(group: TelegramGroup, stats: dict, info: dict, live: int, back: str, can_leave: bool):
    last = fa_date(timezone.localtime(stats["last"])) if stats.get("last") else texts.ADMIN_GROUPS_NO_MATCH
    text = texts.ADMIN_GROUP_DETAIL.format(
        title=escape(info.get("title") or group.title or texts.ADMIN_GROUPS_NO_TITLE),
        chat_id=group.chat_id,
        state=texts.ADMIN_GROUP_ACTIVE if group.is_active else texts.ADMIN_GROUP_LEFT,
        members=fa_num(info["members"]) if info.get("members") is not None else texts.ADMIN_FJ_UNKNOWN,
        role=role_text(info),
        live=fa_num(live),
        week=fa_num(stats.get("week") or 0),
        total=fa_num(stats.get("total") or 0),
        last=last,
        promo=texts.ADMIN_ON if group.promo_enabled else texts.ADMIN_OFF,
        games=texts.ADMIN_GROUP_ALL_GAMES if not group.enabled_games else fa_num(len(group.enabled_games)),
        added=fa_date(timezone.localtime(group.created_at)),
        link=texts.ADMIN_GROUP_LINK if info.get("link") else texts.ADMIN_GROUP_NO_LINK,
    )
    rows = []
    if info.get("link"):
        rows.append([_btn(texts.ADMIN_GROUP_OPEN_BTN, url=info["link"], style=ui.PRIMARY)])
    actions = [_btn(texts.ADMIN_FJ_RECHECK_BTN, f"adm:grp:show:{group.pk}:{back}")]
    if can_leave and group.is_active:
        actions.append(_btn(texts.ADMIN_GROUP_LEAVE_BTN, f"adm:grp:leave:{group.pk}:{back}", ui.DANGER))
    rows.append(actions)
    rows.append([_btn(texts.BACK_BTN, f"adm:grp:{back[0]}:{back[1:] or 0}")])
    return text, InlineKeyboardMarkup(rows)


def _back(value: str) -> str:
    """«a3» یعنی صفحه‌ی ۴ فهرست گروه‌های فعال و «l0» صفحه‌ی اول خارج‌شده‌ها."""
    if len(value) >= 2 and value[0] in "al" and value[1:].isdigit():
        return value
    return "a0"


@callback
async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user, query):
    """adm:grp:<a|l>:<صفحه> · adm:grp:show:<id>:<برگشت> · adm:grp:leave|leaveok:<id>:<برگشت>"""
    from .wallet import show_photo_or_text

    perms = await admin_permissions(user.tg_id)
    if VIEW_PERMISSION not in perms:
        await answer(query, texts.ADMIN_NO_ACCESS, alert=True)
        return
    parts = query.data.split(":")
    action = parts[2] if len(parts) > 2 else "a"
    arg = parts[3] if len(parts) > 3 else "0"

    async def show(text, markup):
        await show_photo_or_text(update, context, query, text, markup)

    if action in ("a", "l"):
        page = int(arg) if arg.isdigit() else 0
        groups, total, counts = await _groups(action == "a", page)
        if page and not groups:
            page = 0
            groups, total, counts = await _groups(action == "a", 0)
        await answer(query)
        await show(*list_screen(groups, total, counts, page, action == "a"))
        return

    pk = int(arg) if arg.isdigit() else 0
    back = _back(parts[4] if len(parts) > 4 else "")
    group, stats = await _group(pk)
    if group is None:
        await answer(query, texts.ADMIN_GROUP_GONE, alert=True)
        return
    can_leave = LEAVE_PERMISSION in perms
    if action == "show":
        await answer(query)
        info = await live_info(context, group.chat_id)
        live = len(manager_of(context).in_chat(group.chat_id)) if context.bot_data.get("manager") else 0
        await show(*detail_screen(group, stats, info, live, back, can_leave))
    elif action == "leave" and can_leave:
        await answer(query)
        sure = InlineKeyboardMarkup(
            [[_btn(texts.ADMIN_GROUP_LEAVE_SURE_BTN, f"adm:grp:leaveok:{group.pk}:{back}", ui.DANGER)], [_btn(texts.BACK_BTN, f"adm:grp:show:{group.pk}:{back}")]]
        )
        await show(texts.ADMIN_GROUP_LEAVE_SURE.format(title=escape(group.title or texts.ADMIN_GROUPS_NO_TITLE)), sure)
    elif action == "leaveok" and can_leave:
        left = await tg_call(context.bot.leave_chat, group.chat_id, retries=1)
        await _mark_left(group.pk)
        logger.info("bot left group from panel", extra={"chat": group.chat_id, "admin": user.tg_id, "ok": bool(left)})
        await answer(query, texts.ADMIN_GROUP_LEFT_DONE if left else texts.ADMIN_GROUP_LEFT_MARKED, alert=not left)
        groups, total, counts = await _groups(True, 0)
        await show(*list_screen(groups, total, counts, 0, True))
    else:
        await answer(query, texts.ADMIN_NO_ACCESS, alert=True)
