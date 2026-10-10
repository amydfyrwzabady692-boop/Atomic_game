"""/shop — فروشگاه آیتم‌های ظاهری (فقط پیوی، فقط با سکه‌ی مجازی، غیرقابل برگشت)."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core import texts
from core.models import TelegramUser
from core.texts import fa_num
from shop import services
from shop.models import ShopItem
from shop.services import ShopError

from ..db import db
from ..tg import tg_call
from .common import answer, callback, command, reply


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def home_screen(user: TelegramUser):
    rows = [[_btn(label, f"shop:k:{kind}")] for kind, label in texts.SHOP_KIND_BTN.items()]
    return texts.SHOP_HEADER.format(coins=fa_num(user.coins)), InlineKeyboardMarkup(rows)


def kind_screen(user: TelegramUser, kind: str, items):
    rows = []
    for item, owned in items:
        if owned:
            mark = "✅" if owned.equipped else "☑️"
            label = texts.SHOP_ITEM_OWNED_BTN.format(mark=mark, value=item.value)
        else:
            label = texts.SHOP_ITEM_BTN.format(value=item.value, price=fa_num(item.price))
        rows.append([_btn(label, f"shop:i:{item.pk}")])
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
            keyboard = InlineKeyboardMarkup(
                [[_btn(texts.SHOP_CONFIRM_BTN, f"shop:b:{item.pk}"), _btn(texts.BACK_BTN, f"shop:k:{item.kind}")]]
            )
            text = texts.SHOP_CONFIRM.format(name=item.name, value=item.value, price=fa_num(item.price))
            await show((text, keyboard))
            return
        else:
            await db(services.buy_item)(user, item.pk)
            await answer(query, texts.SHOP_BOUGHT, alert=True)
    except ShopError as exc:
        await answer(query, texts.SHOP_NO_COINS if exc.code == "no_coins" else texts.ERROR_GENERIC, alert=True)
    await db(user.refresh_from_db)()
    await show(kind_screen(user, item.kind, await db(services.catalog_for)(user, item.kind)))
