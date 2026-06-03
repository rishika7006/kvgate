"""Redis-backed KV store for cross-host cache reuse.

This is the multi-instance-safe path: any gateway replica can serve a cached
response another replica produced. (Conceptually the same cross-host KV-cache
reuse pattern used in high-throughput LLM serving.) Requires the ``redis`` extra.
"""

from __future__ import annotations

from typing import Optional

from .base import KVStore


class RedisKVStore(KVStore):
    def __init__(self, url: str) -> None:
        try:
            import redis.asyncio as redis  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "redis backend requested but 'redis' is not installed. "
                "Install with: pip install 'infergate[redis]'"
            ) from exc
        self._redis = redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Optional[str]:
        return await self._redis.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        if ttl_seconds > 0:
            await self._redis.set(key, value, ex=ttl_seconds)
        else:
            await self._redis.set(key, value)

    async def aclose(self) -> None:
        await self._redis.aclose()
