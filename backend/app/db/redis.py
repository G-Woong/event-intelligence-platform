from __future__ import annotations

import redis as _redis
import redis.asyncio as aioredis
from backend.app.core.config import settings

_sync_client: _redis.Redis | None = None
_async_client: aioredis.Redis | None = None


def get_redis() -> _redis.Redis:
    global _sync_client
    if _sync_client is None:
        _sync_client = _redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _sync_client


async def get_async_redis() -> aioredis.Redis:
    global _async_client
    if _async_client is None:
        _async_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _async_client


def ping() -> bool:
    try:
        return get_redis().ping()
    except Exception:
        return False


def ensure_group(stream: str, group: str) -> None:
    r = get_redis()
    try:
        r.xgroup_create(stream, group, id="0", mkstream=True)
    except _redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def xadd(stream: str, payload: dict) -> str:
    return get_redis().xadd(stream, payload)


def xreadgroup(
    stream: str,
    group: str,
    consumer: str,
    count: int = 10,
    block: int = 5000,
) -> list:
    r = get_redis()
    result = r.xreadgroup(
        groupname=group,
        consumername=consumer,
        streams={stream: ">"},
        count=count,
        block=block,
    )
    return result or []


def xack(stream: str, group: str, message_id: str) -> int:
    return get_redis().xack(stream, group, message_id)
