"""/shop — فروشگاه آیتم‌های ظاهری (فقط پیوی، فقط با سکه‌ی مجازی، غیرقابل برگشت)."""

from html import escape

from telegram import InlineKeyboardMarkup, LabeledPrice, Update
from telegram.ext import ContextTypes

from core import texts
from core.models import TelegramUser
from core.texts import fa_num
from shop import services
from shop.models import ShopItem
from shop.services import ShopError

from .. import ui
from ..db import db
from ..tg import tg_call
from .common import answer, callback, command, reply


def _btn(text: str, data: str, style: str = ""):
    return ui.button(text, data, style=style)


def home_screen(user: TelegramUser):
    rows = [[_btn(label, f"shop:k:{kind}", ui.PRIMARY)] for kind, label in texts.SHOP_KIND_BTN.items()]
    rows.append([
        _btn(texts.WALLET_TOPUP_BTN, "wal:topup:menu", ui.SUCCESS),
        _btn(texts.WALLET_SELL_BTN, "wal:sell:menu", ui.PRIMARY),
    ])
    return texts.SHOP_HEADER.format(coins=fa_num(user.coins)), InlineKeyboardMarkup(rows)


def kind_screen(user: TelegramUser, kind: str, items):
    rows = []
    for item, owned in items:
        if owned:
            mark = "✅" if owned.equipped else "☑️"
            label = texts.SHOP_ITEM_OWNED_BTN.format(mark=mark, value=item.value)
            style = ui.SUCCESS if owned.equipped else ""
        else:
            label = texts.SHOP_ITEM_BTN.format(value=item.value, price=fa_num(item.price))
            style = ui.PRIMARY
        rows.append([_btn(label, f"shop:i:{item.pk}", style)])
    rows.append([_btn(texts.BACK_BTN, "shop:home")])
    text = texts.SHOP_HEADER.format(coins=fa_num(user.coins))
    if not items:
        text += "\n\n" + texts.SHOP_EMPTY
    return text, InlineKeyboardMarkup(rows)


@command(private=True)
async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser):
    await reply(update, *home_screen(user))


@db
def _item_state(user: TelegramUser, item_id: int):
    item = ShopItem.objects.filter(pk=item_id, is_active=True).first()
    owned = item is not None and item.owners.filter(user=user).exists()
    return item, owned


@callback
async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, user: TelegramUser, query):
    parts = query.data.split(":")
    action = parts[1]
    value = parts[2] if len(parts) > 2 else ""

    async def show(screen):
        await tg_call(query.edit_message_text, screen[0], parse_mode="HTML", reply_markup=screen[1])

    if action == "home":
        await show(home_screen(user))
        return
    if action == "k" and value in texts.SHOP_KIND_BTN:
        await show(kind_screen(user, value, await db(services.catalog_for)(user, value)))
        return
    if action == "s" and value.isdigit():
        await _send_invoice(update, context, user, int(value), query)
        return
    if action not in ("i", "b") or not value.isdigit():
        return
    item, owned = await _item_state(user, int(value))
    if item is None:
        return
    try:
        if owned:
            result = await db(services.toggle_equipped)(user, item.pk)
            await answer(query, texts.SHOP_EQUIPPED if result.equipped else texts.SHOP_UNEQUIPPED)
        elif action == "i":
            rows = [
                [
                    _btn(texts.SHOP_CONFIRM_BTN, f"shop:b:{item.pk}", ui.SUCCESS),
                    _btn(texts.BACK_BTN, f"shop:k:{item.kind}"),
                ]
            ]
            # نام و مقدار آیتم از پنل ادمین می‌آید و ممکن است نویسه‌ی HTML داشته باشد
            text = texts.SHOP_CONFIRM.format(
                name=escape(item.name), value=escape(item.value), price=fa_num(item.price)
            )
            if item.stars_price:
                rows.insert(1, [_btn(texts.SHOP_STARS_BTN.format(stars=fa_num(item.stars_price)), f"shop:s:{item.pk}", ui.PRIMARY)])
                text += texts.SHOP_STARS_NOTE.format(stars=fa_num(item.stars_price))
            keyboard = InlineKeyboardMarkup(rows)
            await show((text, keyboard))
            return
        else:
            await db(services.buy_item)(user, item.pk)
            await answer(query, texts.SHOP_BOUGHT, alert=True)
    except ShopError as exc:
        await answer(query, texts.SHOP_NO_COINS if exc.code == "no_coins" else texts.ERROR_GENERIC, alert=True)
    await db(user.refresh_from_db)()
    await show(kind_screen(user, item.kind, await db(services.catalog_for)(user, item.kind)))


# ------------------------------------------------------------------ پرداخت با استار تلگرام (XTR)
STARS_PAYLOAD = "stars:{item}:{user}"


async def _send_invoice(update, context, user: TelegramUser, item_id: int, query) -> None:
    item = await db(services.stars_item)(user, item_id)
    if item is None:
        await answer(query, texts.SHOP_STARS_INVALID, alert=True)
        return
    await tg_call(
        context.bot.send_invoice,
        update.effective_chat.id,
        title=texts.SHOP_STARS_TITLE.format(name=item.name)[:32],
        description=texts.SHOP_STARS_DESCRIPTION.format(name=item.name, value=item.value)[:255],
        payload=STARS_PAYLOAD.format(item=item.pk, user=user.pk),
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(item.name[:32], item.stars_price)],
    )


def _parse_payload(payload: str) -> tuple[int, int] | None:
    parts = (payload or "").split(":")
    if len(parts) != 3 or parts[0] != "stars" or not parts[1].isdigit() or not parts[2].isdigit():
        return None
    return int(parts[1]), int(parts[2])


async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تلگرام قبل از گرفتن استار می‌پرسد؛ فقط وقتی تأیید می‌شود که آیتم هنوز قابل خرید باشد."""
    query = update.pre_checkout_query
    if query is None:
        return
    from ..users import ensure_user

    parsed = _parse_payload(query.invoice_payload)
    user = await ensure_user(query.from_user)
    item = await db(services.stars_item)(user, parsed[0]) if parsed and parsed[1] == user.pk else None
    ok = item is not None and query.currency == "XTR" and query.total_amount == item.stars_price
    await tg_call(query.answer, ok=ok, error_message=None if ok else texts.SHOP_STARS_INVALID)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    payment = message.successful_payment if message else None
    if payment is None or payment.currency != "XTR":
        return
    parsed = _parse_payload(payment.invoice_payload)
    if parsed is None:
        return
    from ..users import ensure_user

    user = await ensure_user(update.effective_user)
    owned = await db(services.grant_stars_purchase)(
        user, parsed[0], payment.total_amount, payment.telegram_payment_charge_id
    )
    name = await db(lambda: owned.item.name)()
    await reply(update, texts.SHOP_STARS_DONE.format(name=escape(name)))
