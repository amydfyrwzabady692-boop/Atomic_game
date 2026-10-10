"""اعتبارسنجی ``initData`` مینی‌اپ تلگرام (طبق مستندات رسمی).

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
بدون امضای معتبر هیچ session یا امتیازی ثبت نمی‌شود.
"""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from django.conf import settings


class InitDataError(Exception):
    pass


def validate_init_data(init_data: str, bot_token: str | None = None, max_age: int | None = None) -> dict:
    """امضا و تازگی initData را بررسی می‌کند و فیلدها را برمی‌گرداند (``user`` به‌صورت dict)."""
    bot_token = bot_token if bot_token is not None else settings.BOT_TOKEN
    max_age = settings.ARCADE_INITDATA_MAX_AGE if max_age is None else max_age
    if not init_data or not bot_token or len(init_data) > 8192:
        raise InitDataError("missing")
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError as exc:
        raise InitDataError("malformed") from exc
    received_hash = pairs.pop("hash", "")
    if not received_hash:
        raise InitDataError("no_hash")
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise InitDataError("bad_signature")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError as exc:
        raise InitDataError("bad_auth_date") from exc
    if max_age and (auth_date <= 0 or time.time() - auth_date > max_age):
        raise InitDataError("expired")
    try:
        user = json.loads(pairs.get("user", ""))
        user_id = int(user["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InitDataError("no_user") from exc
    if user.get("is_bot"):
        raise InitDataError("bot_user")
    pairs["user"] = user
    pairs["user_id"] = user_id
    return pairs


def sign_init_data(fields: dict, bot_token: str) -> str:
    """initData امضاشده می‌سازد (فقط برای تست و حالت توسعه)."""
    from urllib.parse import urlencode

    data = {k: (json.dumps(v, separators=(",", ":"), ensure_ascii=False) if isinstance(v, dict) else str(v)) for k, v in fields.items()}
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)
