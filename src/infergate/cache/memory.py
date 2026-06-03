"""In-process KV store with TTL. The zero-dependency default backend."""

from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

from .base import KVStore


class MemoryKVStore(KVStore):
    def __init__(self) -> None:
        self._data: Dict[str, Tuple[float, str]] = {}

    async def get(self, key: str) -> Optional[str]:
        item = self._data.get(key)
        if item is None:
            return None
        expiry, value = item
        if expiry and expiry < time.monotonic():
            self._data.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        expiry = time.monotonic() + ttl_seconds if ttl_seconds > 0 else 0.0
        self._data[key] = (expiry, value)

    async def aclose(self) -> None:
        self._data.clear()
