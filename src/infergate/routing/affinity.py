"""Prefix-affinity index — the gateway-side model of "which replica has which
prefix warm", learned purely from the traffic the gateway routes.

For each replica we keep the set of block hashes it has recently served, with a
last-seen timestamp. ``matched_blocks`` returns the length of the leading run of a
request's block-hash chain that a replica still holds (unexpired) — i.e. how much
of the prompt's prefix is likely warm in that replica's KV cache. TTL + LRU cap
approximate the engine's real KV eviction, which the gateway cannot observe
directly. This needs **no cooperation from the inference engine** (no KV events).
"""

from __future__ import annotations

import time
from collections import OrderedDict, defaultdict
from typing import Dict, List, Optional, Protocol


class AffinityIndex(Protocol):
    """Shared interface of the in-memory and Redis prefix-affinity indexes."""

    def matched_blocks(
        self, replica: str, chain: List[str], now: Optional[float] = None
    ) -> int: ...
    def register(self, replica: str, chain: List[str], now: Optional[float] = None) -> None: ...
    def block_count(self, replica: str) -> int: ...


class PrefixAffinityIndex:
    def __init__(self, ttl_s: float = 300.0, max_blocks_per_replica: int = 200_000):
        self.ttl_s = ttl_s
        self.max_blocks = max(1, max_blocks_per_replica)
        # replica_id -> OrderedDict(block_hash -> last_seen_monotonic), LRU order
        self._seen: Dict[str, OrderedDict[str, float]] = defaultdict(OrderedDict)

    def _now(self) -> float:
        return time.monotonic()

    def _fresh(self, ts: float, now: float) -> bool:
        return self.ttl_s <= 0 or (now - ts) <= self.ttl_s

    def matched_blocks(self, replica: str, chain: List[str], now: Optional[float] = None) -> int:
        """Length of the leading run of `chain` present & unexpired for `replica`."""
        seen = self._seen.get(replica)
        if not seen:
            return 0
        now = self._now() if now is None else now
        count = 0
        for h in chain:
            ts = seen.get(h)
            if ts is None or not self._fresh(ts, now):
                break
            count += 1
        return count

    def register(self, replica: str, chain: List[str], now: Optional[float] = None) -> None:
        """Record that `replica` has now served (and thus warmed) this chain."""
        now = self._now() if now is None else now
        seen = self._seen[replica]
        for h in chain:
            seen.pop(h, None)  # move-to-end on refresh
            seen[h] = now
        self._evict(seen, now)

    def _evict(self, seen: OrderedDict[str, float], now: float) -> None:
        if self.ttl_s > 0:
            for h in [h for h, ts in seen.items() if not self._fresh(ts, now)]:
                seen.pop(h, None)
        while len(seen) > self.max_blocks:
            seen.popitem(last=False)  # drop least-recently-used

    def block_count(self, replica: str) -> int:
        return len(self._seen.get(replica, ()))


def build_affinity_index(settings) -> AffinityIndex:
    """Construct the affinity index from PrefixKvAwareSettings.

    - ``memory`` (default): fast, per-process — right for a single gateway replica.
    - ``redis``: shared across gateway replicas so they route coherently (see
      ``affinity_redis.RedisPrefixAffinityIndex``). The URL is already ${ENV}-expanded
      by the config loader.
    """
    backend = getattr(settings, "affinity_backend", "memory")
    if backend == "redis":
        from .affinity_redis import RedisPrefixAffinityIndex

        return RedisPrefixAffinityIndex(
            url=getattr(settings, "affinity_redis_url", "redis://localhost:6379/0"),
            ttl_s=settings.affinity_ttl_s,
            max_blocks_per_replica=settings.max_blocks_per_replica,
        )
    return PrefixAffinityIndex(
        ttl_s=settings.affinity_ttl_s,
        max_blocks_per_replica=settings.max_blocks_per_replica,
    )
