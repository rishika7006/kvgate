"""Cache interfaces and the canonical request key."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel

from ..models import ChatCompletionRequest


class CacheHit(BaseModel):
    response: Dict[str, Any]
    kind: Literal["exact", "semantic"]
    similarity: float = 1.0


def canonical_key(request: ChatCompletionRequest) -> str:
    """Stable hash of the semantically-significant request fields.

    Sampling parameters are part of the key: two requests with the same prompt
    but different ``temperature`` are *not* an exact hit.
    """
    payload = {
        "model": request.model,
        "messages": [m.model_dump(exclude_none=True) for m in request.messages],
        "temperature": request.temperature,
        "top_p": request.top_p,
        "max_tokens": request.max_tokens,
        "stop": request.stop,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "kvgate:exact:" + hashlib.sha256(blob.encode()).hexdigest()


class KVStore:
    """Minimal async key/value store with TTL. Backends implement these."""

    async def get(self, key: str) -> Optional[str]:  # pragma: no cover - interface
        raise NotImplementedError

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:  # pragma: no cover
        raise NotImplementedError

    async def aclose(self) -> None:  # pragma: no cover - optional
        return None
