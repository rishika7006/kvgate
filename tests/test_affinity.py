from __future__ import annotations

from kvgate.config import PrefixKvAwareSettings
from kvgate.routing.affinity import PrefixAffinityIndex, build_affinity_index


def test_matched_blocks_after_register():
    idx = PrefixAffinityIndex(ttl_s=1000, max_blocks_per_replica=100)
    chain = ["h1", "h2", "h3", "h4"]
    assert idx.matched_blocks("r1", chain, now=0) == 0
    idx.register("r1", chain, now=0)
    assert idx.matched_blocks("r1", chain, now=1) == 4


def test_partial_prefix_match():
    idx = PrefixAffinityIndex(ttl_s=1000)
    idx.register("r1", ["a", "b", "c"], now=0)
    # A request sharing the first two blocks then diverging matches 2.
    assert idx.matched_blocks("r1", ["a", "b", "x", "y"], now=1) == 2
    # A request that diverges immediately matches 0.
    assert idx.matched_blocks("r1", ["z", "b", "c"], now=1) == 0


def test_ttl_expiry_breaks_the_run():
    idx = PrefixAffinityIndex(ttl_s=10)
    idx.register("r1", ["a", "b"], now=0)
    assert idx.matched_blocks("r1", ["a", "b"], now=5) == 2
    assert idx.matched_blocks("r1", ["a", "b"], now=100) == 0  # expired


def test_lru_cap_evicts_oldest():
    idx = PrefixAffinityIndex(ttl_s=0, max_blocks_per_replica=3)
    idx.register("r1", ["a", "b", "c"], now=0)
    idx.register("r1", ["d"], now=1)  # exceeds cap -> evict 'a'
    assert idx.block_count("r1") == 3
    assert idx.matched_blocks("r1", ["a"], now=2) == 0
    assert idx.matched_blocks("r1", ["d"], now=2) == 1


def test_replicas_isolated():
    idx = PrefixAffinityIndex(ttl_s=1000)
    idx.register("r1", ["a", "b"], now=0)
    assert idx.matched_blocks("r2", ["a", "b"], now=1) == 0


def test_build_memory_backend():
    idx = build_affinity_index(PrefixKvAwareSettings(affinity_backend="memory"))
    assert isinstance(idx, PrefixAffinityIndex)


def test_build_redis_backend(monkeypatch):
    # redis backend is now implemented; see tests/test_affinity_redis.py for behavior.
    import fakeredis

    def fake_from_url(url, decode_responses=False):
        return fakeredis.FakeStrictRedis(decode_responses=decode_responses)

    monkeypatch.setattr("redis.from_url", fake_from_url)
    from kvgate.routing.affinity_redis import RedisPrefixAffinityIndex

    idx = build_affinity_index(PrefixKvAwareSettings(affinity_backend="redis"))
    assert isinstance(idx, RedisPrefixAffinityIndex)
