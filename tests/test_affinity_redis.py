"""Tests for the Redis-backed (distributed) prefix-affinity index.

Uses fakeredis so no real server is needed. Verifies the index behaves like the in-memory
one (leading-prefix match, TTL freshness, size cap) AND the property that makes it useful:
two independent index instances backed by the same Redis share affinity state.
"""

from __future__ import annotations

import fakeredis
import pytest

from infergate.config import PrefixKvAwareSettings
from infergate.routing.affinity import build_affinity_index
from infergate.routing.affinity_redis import RedisPrefixAffinityIndex


@pytest.fixture
def shared_server():
    return fakeredis.FakeServer()


def make_index(monkeypatch, server, **kwargs) -> RedisPrefixAffinityIndex:
    # Route from_url to a FakeRedis bound to a specific in-memory server, so multiple
    # indexes can share (or not share) state deterministically.
    def fake_from_url(url, decode_responses=False):
        return fakeredis.FakeStrictRedis(server=server, decode_responses=decode_responses)

    monkeypatch.setattr("redis.from_url", fake_from_url)
    return RedisPrefixAffinityIndex(url="redis://test", **kwargs)


def test_matched_blocks_leading_prefix(monkeypatch, shared_server):
    idx = make_index(monkeypatch, shared_server, ttl_s=300)
    chain = ["a", "b", "c", "d"]
    assert idx.matched_blocks("r1", chain) == 0
    idx.register("r1", ["a", "b"])
    # only the leading run that r1 has seen counts
    assert idx.matched_blocks("r1", chain) == 2
    assert idx.matched_blocks("r1", ["x", "a", "b"]) == 0  # must match from the head
    assert idx.block_count("r1") == 2


def test_ttl_expiry(monkeypatch, shared_server):
    idx = make_index(monkeypatch, shared_server, ttl_s=100)
    idx.register("r1", ["a", "b"], now=1000.0)
    assert idx.matched_blocks("r1", ["a", "b"], now=1050.0) == 2  # fresh
    assert idx.matched_blocks("r1", ["a", "b"], now=1200.0) == 0  # both expired on read


def test_size_cap_trims_oldest(monkeypatch, shared_server):
    idx = make_index(monkeypatch, shared_server, ttl_s=0, max_blocks_per_replica=2)
    idx.register("r1", ["a"], now=1.0)
    idx.register("r1", ["b"], now=2.0)
    idx.register("r1", ["c"], now=3.0)  # overflow -> oldest ("a") trimmed
    assert idx.block_count("r1") == 2
    assert idx.matched_blocks("r1", ["c"], now=4.0) == 1
    assert idx.matched_blocks("r1", ["a"], now=4.0) == 0


def test_two_indexes_share_state(monkeypatch, shared_server):
    """The whole point of the Redis backend: a second gateway replica sees the first's writes."""
    gw1 = make_index(monkeypatch, shared_server, ttl_s=300)
    gw2 = make_index(monkeypatch, shared_server, ttl_s=300)
    gw1.register("r1", ["a", "b", "c"])
    assert gw2.matched_blocks("r1", ["a", "b", "c"]) == 3  # gw2 learns from gw1 via Redis


def test_build_affinity_index_selects_redis(monkeypatch, shared_server):
    def fake_from_url(url, decode_responses=False):
        return fakeredis.FakeStrictRedis(server=shared_server, decode_responses=decode_responses)

    monkeypatch.setattr("redis.from_url", fake_from_url)
    settings = PrefixKvAwareSettings(affinity_backend="redis")
    idx = build_affinity_index(settings)
    assert isinstance(idx, RedisPrefixAffinityIndex)
