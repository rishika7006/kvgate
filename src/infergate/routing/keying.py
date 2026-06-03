"""Routing-key construction for prefix/KV-aware routing.

Turns a chat request into a chain of cumulative block hashes such that two
requests sharing a leading prefix produce identical leading block hashes. The key
is **multimodal-aware**: each image is reduced to a hash marker (mirroring the
``mm_hash`` trick LMCache/vLLM use), so the same text with two *different* images
diverges immediately — and the same image with the same prompt collapses to the
same key and routes to the replica that already has its (large) vision KV warm.

Tokenization is deliberately approximate (whitespace) and dependency-free: routing
only needs *consistency*, not byte-identical parity with the engine's own block
hashes. An exact HF tokenizer can be plugged in later for higher fidelity.
"""

from __future__ import annotations

import hashlib
from typing import List

from pydantic import BaseModel

from ..models import ChatCompletionRequest

_BLOCK_SEP = "\x1e"
_CHAIN_SEP = "\x1f"
_IMG_PREFIX = "\x00IMG:"


class RoutingKey(BaseModel):
    block_hashes: List[str]
    num_units: int
    num_images: int


def image_marker(ref: str, mode: str = "bytes_sha256") -> str:
    """Deterministic short hash identifying an image by content or by URL."""
    if mode == "url":
        payload = ref
    else:  # bytes_sha256: hash the base64 payload of a data: URI, else the ref
        if ref.startswith("data:") and "," in ref:
            payload = ref.split(",", 1)[1]
        else:
            payload = ref
    return _IMG_PREFIX + hashlib.sha256(payload.encode("utf-8", "ignore")).hexdigest()[:16]


def _approx_tokenize(text: str) -> List[str]:
    return text.split()


def build_routing_key(
    request: ChatCompletionRequest,
    block_size: int = 16,
    image_key: str = "bytes_sha256",
    seed: str = "infergate",
) -> RoutingKey:
    """Build the cumulative block-hash chain for a request."""
    units: List[str] = []
    num_images = 0
    for m in request.messages:
        units.append(f"\x02role:{m.role}")
        units.extend(_approx_tokenize(m.text_content()))
        for ref in m.image_refs():
            units.append(image_marker(ref, image_key))
            num_images += 1

    block_hashes: List[str] = []
    prev = hashlib.sha256(seed.encode()).hexdigest()
    step = max(1, block_size)
    for i in range(0, len(units), step):
        block = units[i : i + step]
        prev = hashlib.sha256(
            (prev + _CHAIN_SEP + _BLOCK_SEP.join(block)).encode("utf-8", "ignore")
        ).hexdigest()
        block_hashes.append(prev)

    return RoutingKey(block_hashes=block_hashes, num_units=len(units), num_images=num_images)
