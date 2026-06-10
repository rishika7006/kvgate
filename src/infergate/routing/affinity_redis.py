"""Redis-backed prefix-affinity index — the **distributed** counterpart of
``PrefixAffinityIndex``.

The in-memory index only knows about traffic *this* gateway process routed. When you run
several gateway replicas behind a load balancer, each would learn a different, partial view
of which backend replica has which prefix warm — so they'd route inconsistently. Backing the
index with Redis makes it a **single shared source of truth**: every gateway replica reads and
writes the same affinity state, so they route coherently toward warm backends.

Layout (one Redis hash per backend replica):

    key   = "{prefix}{replica}"            e.g. "infergate:aff:r1"
    field = block_hash
    value = last-seen epoch seconds
    + a per-key TTL so a replica that goes quiet ages out entirely.

``matched_blocks`` is one pipelined ``HMGET`` (sub-millisecond on a local/colocated Redis);
``register`` is one ``HSET`` + ``EXPIRE``. We keep the same synchronous interface as the
in-memory index so the routing hot path is unchanged. Per-field TTL isn't native to Redis
hashes on all versions, so freshness is enforced on read (compare stored timestamp to ttl)
and bounded by the whole-key EXPIRE; size is bounded by ``max_blocks_per_replica`` via an
occasional trim. Trade-off: this adds a blocking Redis round-trip to routing — fine for a
colocated Redis; the in-memory backend remains the default for single-replica deploys.
"""

from __future__ import annotations

import time
from typing import List, Optional


class RedisPrefixAffinityIndex:
    def __init__(
        self,
        url: str,
        ttl_s: float = 300.0,
        max_blocks_per_replica: int = 200_000,
        key_prefix: str = "infergate:aff:",
    ):
        try:
            import redis  # sync client: routing path is sync; calls are tiny + colocated
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "affinity_backend=redis requires the 'redis' package. "
                "Install with: pip install 'infergate[redis]'"
            ) from exc
        self.ttl_s = ttl_s
        self.max_blocks = max(1, max_blocks_per_replica)
        self._prefix = key_prefix
        # decode_responses so values come back as str (we store epoch-second strings)
        self._redis = redis.from_url(url, decode_responses=True)

    def _key(self, replica: str) -> str:
        return f"{self._prefix}{replica}"

    def _now(self) -> float:
        return time.time()  # wall clock: shared across gateway hosts (unlike monotonic)

    def _fresh(self, ts: float, now: float) -> bool:
        return self.ttl_s <= 0 or (now - ts) <= self.ttl_s

    def matched_blocks(self, replica: str, chain: List[str], now: Optional[float] = None) -> int:
        """Length of the leading run of `chain` present & unexpired for `replica`."""
        if not chain:
            return 0
        now = self._now() if now is None else now
        values = self._redis.hmget(self._key(replica), chain)
        count = 0
        for raw in values:
            if raw is None:
                break
            try:
                ts = float(raw)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                break
            if not self._fresh(ts, now):
                break
            count += 1
        return count

    def register(self, replica: str, chain: List[str], now: Optional[float] = None) -> None:
        """Record that `replica` has now served (and thus warmed) this chain."""
        if not chain:
            return
        now = self._now() if now is None else now
        key = self._key(replica)
        mapping = dict.fromkeys(chain, now)
        pipe = self._redis.pipeline(transaction=False)
        # redis stubs type hset(mapping=) with an invariant Mapping key; dict[str, float]
        # is fine at runtime (decode_responses round-trips strings). Ignore the stub nit
        # rather than chase its exact union (which differs across redis-stub versions).
        pipe.hset(key, mapping=mapping)  # type: ignore[arg-type]
        if self.ttl_s > 0:
            pipe.expire(key, int(self.ttl_s) + 1)
        pipe.hlen(key)
        results = pipe.execute()
        hlen = results[-1]
        if isinstance(hlen, int) and hlen > self.max_blocks:
            self._trim(key, now)

    def _trim(self, key: str, now: float) -> None:
        """Bound a replica's set: drop expired fields first, then oldest by timestamp."""
        items = self._redis.hgetall(key)
        if not items:
            return
        parsed = []
        for h, raw in items.items():
            try:
                parsed.append((h, float(raw)))
            except (TypeError, ValueError):  # pragma: no cover - defensive
                parsed.append((h, 0.0))
        expired = [h for h, ts in parsed if not self._fresh(ts, now)]
        live = [(h, ts) for h, ts in parsed if self._fresh(ts, now)]
        to_drop = list(expired)
        overflow = len(live) - self.max_blocks
        if overflow > 0:
            live.sort(key=lambda x: x[1])  # oldest first
            to_drop.extend(h for h, _ in live[:overflow])
        if to_drop:
            self._redis.hdel(key, *to_drop)

    def block_count(self, replica: str) -> int:
        return int(self._redis.hlen(self._key(replica)))
