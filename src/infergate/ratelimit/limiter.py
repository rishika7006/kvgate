"""Token-bucket rate limiting, per API key / tenant.

Memory backend is a classic token bucket (smooth, supports bursts). Redis backend
uses an atomic Lua token bucket so limits hold across gateway replicas.
"""

from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

from pydantic import BaseModel

from ..config import RateLimitSettings


class RateLimitDecision(BaseModel):
    allowed: bool
    remaining: float = 0.0
    retry_after_s: float = 0.0
    limit_rpm: int = 0


class RateLimiter:
    def __init__(self, settings: RateLimitSettings):
        self.settings = settings
        self.enabled = settings.enabled

    async def check(self, identity: str, rpm: Optional[int] = None) -> RateLimitDecision:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


class MemoryRateLimiter(RateLimiter):
    def __init__(self, settings: RateLimitSettings):
        super().__init__(settings)
        # identity -> (tokens, last_refill_monotonic)
        self._buckets: Dict[str, Tuple[float, float]] = {}

    async def check(self, identity: str, rpm: Optional[int] = None) -> RateLimitDecision:
        if not self.enabled:
            return RateLimitDecision(allowed=True)

        rpm = rpm or self.settings.default_rpm
        capacity = float(self.settings.burst or rpm)
        refill_per_s = rpm / 60.0
        now = time.monotonic()

        tokens, last = self._buckets.get(identity, (capacity, now))
        tokens = min(capacity, tokens + (now - last) * refill_per_s)

        if tokens >= 1.0:
            tokens -= 1.0
            self._buckets[identity] = (tokens, now)
            return RateLimitDecision(allowed=True, remaining=tokens, limit_rpm=rpm)

        self._buckets[identity] = (tokens, now)
        deficit = 1.0 - tokens
        retry_after = deficit / refill_per_s if refill_per_s > 0 else 60.0
        return RateLimitDecision(
            allowed=False, remaining=tokens, retry_after_s=retry_after, limit_rpm=rpm
        )


_REDIS_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local bucket = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(bucket[1])
local ts = tonumber(bucket[2])
if tokens == nil then tokens = capacity; ts = now end
tokens = math.min(capacity, tokens + (now - ts) * refill)
local allowed = 0
if tokens >= 1 then tokens = tokens - 1; allowed = 1 end
redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, 120)
return {allowed, tostring(tokens)}
"""


class RedisRateLimiter(RateLimiter):  # pragma: no cover - requires redis
    def __init__(self, settings: RateLimitSettings):
        super().__init__(settings)
        try:
            import redis.asyncio as redis
        except ImportError as exc:
            raise RuntimeError(
                "redis rate-limit backend requested but 'redis' is not installed."
            ) from exc
        self._redis = redis.from_url(settings.redis_url, decode_responses=True)
        self._script = self._redis.register_script(_REDIS_LUA)

    async def check(self, identity: str, rpm: Optional[int] = None) -> RateLimitDecision:
        if not self.enabled:
            return RateLimitDecision(allowed=True)
        rpm = rpm or self.settings.default_rpm
        capacity = float(self.settings.burst or rpm)
        refill_per_s = rpm / 60.0
        now = time.time()
        allowed, tokens = await self._script(
            keys=[f"infergate:rl:{identity}"], args=[capacity, refill_per_s, now]
        )
        tokens = float(tokens)
        if int(allowed) == 1:
            return RateLimitDecision(allowed=True, remaining=tokens, limit_rpm=rpm)
        retry_after = (1.0 - tokens) / refill_per_s if refill_per_s > 0 else 60.0
        return RateLimitDecision(
            allowed=False, remaining=tokens, retry_after_s=retry_after, limit_rpm=rpm
        )

    async def aclose(self) -> None:
        await self._redis.aclose()


def build_rate_limiter(settings: RateLimitSettings) -> RateLimiter:
    if settings.enabled and settings.backend == "redis":
        return RedisRateLimiter(settings)
    return MemoryRateLimiter(settings)
