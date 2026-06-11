from __future__ import annotations

from kvgate.config import RateLimitSettings
from kvgate.ratelimit import MemoryRateLimiter


async def test_token_bucket_allows_then_blocks():
    limiter = MemoryRateLimiter(RateLimitSettings(default_rpm=60, burst=2))
    d1 = await limiter.check("tenant-1")
    d2 = await limiter.check("tenant-1")
    d3 = await limiter.check("tenant-1")
    assert d1.allowed and d2.allowed
    assert not d3.allowed
    assert d3.retry_after_s > 0


async def test_tenants_isolated():
    limiter = MemoryRateLimiter(RateLimitSettings(default_rpm=60, burst=1))
    assert (await limiter.check("a")).allowed
    # different tenant has its own bucket
    assert (await limiter.check("b")).allowed
    assert not (await limiter.check("a")).allowed


async def test_per_key_override():
    limiter = MemoryRateLimiter(RateLimitSettings(default_rpm=60, burst=1))
    # explicit higher rpm/burst via override is honored
    big = await limiter.check("vip", rpm=6000)
    assert big.allowed
    assert big.limit_rpm == 6000


async def test_disabled_always_allows():
    limiter = MemoryRateLimiter(RateLimitSettings(enabled=False, default_rpm=1, burst=1))
    for _ in range(10):
        assert (await limiter.check("x")).allowed
