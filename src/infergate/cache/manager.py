"""CacheManager — orchestrates exact-match and semantic caching.

Lookup order on a request:
  1. Exact match (canonical hash) in the KV store — backend may be Redis, so this
     is shared across gateway replicas.
  2. Semantic match: embed the prompt and find the nearest previously-cached
     prompt for the same model above the similarity threshold; if found, return
     that prompt's stored response.

Only non-streaming, deterministic-ish requests are cached. Streaming responses
are reconstructed into a normal response before caching so a later request can
be served from cache (and re-streamed) transparently.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Deque, List, Optional, Tuple

from ..config import CacheSettings
from ..models import ChatCompletionRequest
from .base import CacheHit, KVStore, canonical_key
from .embedders import Embedder, build_embedder, cosine_similarity
from .memory import MemoryKVStore


class CacheManager:
    def __init__(self, settings: CacheSettings, store: Optional[KVStore] = None) -> None:
        self.settings = settings
        self.enabled = settings.enabled
        self.store = store or MemoryKVStore()
        self._embedder: Optional[Embedder] = None
        # (model, embedding, exact_key) for brute-force nearest-neighbour search.
        self._index: Deque[Tuple[str, List[float], str]] = deque(
            maxlen=settings.semantic.max_entries
        )
        if settings.enabled and settings.semantic.enabled:
            self._embedder = build_embedder(settings.semantic.embedder, settings.semantic.model)

    @property
    def semantic_enabled(self) -> bool:
        return self._embedder is not None

    async def get(self, request: ChatCompletionRequest) -> Optional[CacheHit]:
        if not self.enabled:
            return None

        key = canonical_key(request)
        raw = await self.store.get(key)
        if raw is not None:
            return CacheHit(response=json.loads(raw), kind="exact", similarity=1.0)

        if self._embedder is None:
            return None

        query_vec = self._embedder.embed(request.prompt_text())
        best_key, best_sim = self._nearest(request.model, query_vec)
        if best_key and best_sim >= self.settings.semantic.threshold:
            raw = await self.store.get(best_key)
            if raw is not None:
                return CacheHit(response=json.loads(raw), kind="semantic", similarity=best_sim)
        return None

    def _nearest(self, model: str, query_vec: List[float]) -> Tuple[Optional[str], float]:
        best_key, best_sim = None, -1.0
        for m, vec, key in self._index:
            if m != model:
                continue
            sim = cosine_similarity(query_vec, vec)
            if sim > best_sim:
                best_key, best_sim = key, sim
        return best_key, best_sim

    async def put(self, request: ChatCompletionRequest, response: dict) -> None:
        if not self.enabled:
            return
        key = canonical_key(request)
        await self.store.set(key, json.dumps(response), self.settings.ttl_seconds)
        if self._embedder is not None:
            vec = self._embedder.embed(request.prompt_text())
            self._index.append((request.model, vec, key))

    async def aclose(self) -> None:
        await self.store.aclose()


def build_cache(settings: CacheSettings) -> CacheManager:
    store: KVStore
    if settings.enabled and settings.backend == "redis":
        from .redis_store import RedisKVStore

        store = RedisKVStore(settings.redis_url)
    else:
        store = MemoryKVStore()
    return CacheManager(settings, store)
