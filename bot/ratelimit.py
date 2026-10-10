from core.redis import get_redis


async def allow(key: str, limit: int, window: int = 1) -> bool:
    """حداکثر ``limit`` رویداد در هر ``window`` ثانیه برای این کلید."""
    redis = get_redis()
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window)
    return count <= limit


async def allow_message(tg_id: int) -> bool:
    return await allow(f"rl:msg:{tg_id}", 3)


async def allow_callback(tg_id: int) -> bool:
    return await allow(f"rl:cb:{tg_id}", 4)
