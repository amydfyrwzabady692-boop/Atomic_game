"""فروشگاه آیتم‌های ظاهری. خرید فقط با سکه‌ی مجازی و غیرقابل برگشت است."""

from django.db import transaction

from wallet.models import TxType
from wallet.services import InsufficientFunds, apply_transaction

from .models import ShopItem, UserItem


class ShopError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def buy_item(user, item_id: int) -> UserItem:
    with transaction.atomic():
        item = ShopItem.objects.filter(pk=item_id, is_active=True).first()
        if item is None:
            raise ShopError("not_found")
        if UserItem.objects.filter(user=user, item=item).exists():
            raise ShopError("already_owned")
        try:
            apply_transaction(user, -item.price, TxType.SHOP, f"shop:{user.pk}:{item.pk}")
        except InsufficientFunds as exc:
            raise ShopError("no_coins") from exc
        owned = UserItem.objects.create(user=user, item=item)
    set_equipped(user, item_id, True)
    owned.refresh_from_db()
    return owned


def set_equipped(user, item_id: int, equipped: bool) -> UserItem:
    """از هر نوع (عنوان/ایموجی/قاب) فقط یک آیتم فعال است."""
    with transaction.atomic():
        owned = UserItem.objects.select_related("item").filter(user=user, item_id=item_id).first()
        if owned is None:
            raise ShopError("not_owned")
        if equipped:
            UserItem.objects.filter(user=user, item__kind=owned.item.kind, equipped=True).update(equipped=False)
        owned.equipped = equipped
        owned.save(update_fields=["equipped"])
    return owned


def toggle_equipped(user, item_id: int) -> UserItem:
    owned = UserItem.objects.filter(user=user, item_id=item_id).first()
    if owned is None:
        raise ShopError("not_owned")
    return set_equipped(user, item_id, not owned.equipped)


def decorations(user_ids: list[int]) -> dict[int, dict[str, str]]:
    """آیتم‌های فعال هر کاربر: ``{user_id: {"title": ..., "emoji": ..., "frame": ...}}``"""
    result: dict[int, dict[str, str]] = {}
    rows = UserItem.objects.filter(user_id__in=user_ids, equipped=True).values_list(
        "user_id", "item__kind", "item__value"
    )
    for user_id, kind, value in rows:
        result.setdefault(user_id, {})[kind] = value
    return result


def catalog_for(user, kind: str) -> list[tuple[ShopItem, UserItem | None]]:
    owned = {o.item_id: o for o in UserItem.objects.filter(user=user, item__kind=kind)}
    return [(item, owned.get(item.pk)) for item in ShopItem.objects.filter(kind=kind, is_active=True)]


DEFAULT_ITEMS = [
    ("title", "تازه‌کار", "تازه‌کار", 200),
    ("title", "حرفه‌ای", "حرفه‌ای", 1500),
    ("title", "استاد", "استاد", 5000),
    ("title", "افسانه", "افسانه", 15000),
    ("title", "مغز متفکر", "مغز متفکر", 3000),
    ("title", "سلطان کوییز", "سلطان کوییز", 4000),
    ("emoji", "آتش", "🔥", 500),
    ("emoji", "تاج", "👑", 3000),
    ("emoji", "صاعقه", "⚡", 800),
    ("emoji", "الماس", "💎", 5000),
    ("emoji", "اژدها", "🐉", 2500),
    ("emoji", "موشک", "🚀", 1000),
    ("emoji", "ستاره", "🌟", 600),
    ("frame", "قاب ستاره", "✨", 1000),
    ("frame", "قاب آتشین", "🔥", 2500),
    ("frame", "قاب طلایی", "🏆", 6000),
    ("frame", "قاب الماسی", "💠", 10000),
]


def seed_default_items() -> int:
    created = 0
    for order, (kind, name, value, price) in enumerate(DEFAULT_ITEMS):
        _, was_created = ShopItem.objects.get_or_create(
            kind=kind, name=name, defaults={"value": value, "price": price, "sort_order": order}
        )
        created += was_created
    return created
