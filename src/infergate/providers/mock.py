"""A deterministic, dependency-free mock provider.

This is what makes InferGate runnable (and load-testable) the moment you clone
it, with zero API keys. It produces a stable pseudo-response, simulates realistic
latency, and streams token-by-token at a configurable rate so the routing,
caching, rate-limiting, and metrics paths all exercise end to end.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator

from ..config import ProviderConfig
from ..models import ChatCompletionRequest, estimate_tokens
from .base import Provider, ProviderResult

_LOREM = (
    "InferGate routed this request through the {name} backend. "
    "This is a deterministic mock response generated locally so the gateway can "
    "run, stream, cache, and load-test without any upstream API keys. "
    "Prompt fingerprint: {fp}. The quick brown fox jumps over the lazy dog."
)


class MockProvider(Provider):
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.latency_ms = config.latency_ms
        self.tokens_per_second = max(1.0, config.tokens_per_second)

    def _render(self, request: ChatCompletionRequest) -> str:
        fp = hashlib.sha256(request.prompt_text().encode()).hexdigest()[:8]
        text = _LOREM.format(name=self.name, fp=fp)
        if request.max_tokens:
            words = text.split()
            text = " ".join(words[: max(1, request.max_tokens)])
        return text

    async def complete(self, request: ChatCompletionRequest, model: str) -> ProviderResult:
        await asyncio.sleep(self.latency_ms / 1000.0)
        content = self._render(request)
        return ProviderResult(
            content=content,
            prompt_tokens=estimate_tokens(request.prompt_text()),
            completion_tokens=estimate_tokens(content),
            upstream_model=model,
        )

    async def stream(self, request: ChatCompletionRequest, model: str) -> AsyncIterator[str]:
        await asyncio.sleep(self.latency_ms / 1000.0)  # time-to-first-token
        content = self._render(request)
        delay = 1.0 / self.tokens_per_second
        for token in content.split(" "):
            yield token + " "
            await asyncio.sleep(delay)
