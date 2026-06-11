from __future__ import annotations

import pytest

from kvgate.cache import CacheManager, canonical_key
from kvgate.cache.embedders import HashingEmbedder, cosine_similarity
from kvgate.config import CacheSettings, SemanticCacheSettings
from kvgate.models import ChatCompletionRequest


def _req(content, model="demo", **kw):
    return ChatCompletionRequest(model=model, messages=[{"role": "user", "content": content}], **kw)


def test_canonical_key_stable_and_sensitive():
    a = canonical_key(_req("hello"))
    b = canonical_key(_req("hello"))
    c = canonical_key(_req("hello", temperature=0.5))
    assert a == b
    assert a != c  # sampling params are part of the key


def test_hashing_embedder_similarity():
    emb = HashingEmbedder()
    same = cosine_similarity(emb.embed("the cat sat"), emb.embed("the cat sat"))
    diff = cosine_similarity(emb.embed("the cat sat"), emb.embed("quantum chromodynamics"))
    assert same == pytest.approx(1.0, abs=1e-6)
    assert diff < same


async def test_exact_cache_roundtrip():
    cm = CacheManager(CacheSettings(semantic=SemanticCacheSettings(enabled=False)))
    req = _req("store this")
    assert await cm.get(req) is None
    await cm.put(req, {"id": "x", "model": "demo", "choices": [], "object": "chat.completion"})
    hit = await cm.get(req)
    assert hit is not None and hit.kind == "exact"


async def test_semantic_cache_hit():
    cm = CacheManager(CacheSettings(semantic=SemanticCacheSettings(enabled=True, threshold=0.6)))
    stored = _req("how do I reset my password")
    await cm.put(
        stored,
        {
            "id": "1",
            "model": "demo",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "answer"},
                    "finish_reason": "stop",
                }
            ],
            "object": "chat.completion",
        },
    )
    # Reworded but lexically overlapping query should hit semantically.
    similar = _req("how do I reset my password again")
    hit = await cm.get(similar)
    assert hit is not None and hit.kind == "semantic"
    assert hit.similarity >= 0.6


async def test_semantic_cache_respects_threshold():
    cm = CacheManager(CacheSettings(semantic=SemanticCacheSettings(enabled=True, threshold=0.99)))
    await cm.put(
        _req("alpha beta gamma"),
        {"id": "1", "model": "demo", "choices": [], "object": "chat.completion"},
    )
    assert await cm.get(_req("completely unrelated text here")) is None


async def test_cache_disabled():
    cm = CacheManager(CacheSettings(enabled=False))
    req = _req("x")
    await cm.put(req, {"id": "1"})
    assert await cm.get(req) is None
