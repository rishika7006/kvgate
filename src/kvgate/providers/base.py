"""Provider abstraction.

A Provider knows how to talk to one upstream inference backend (OpenAI,
Anthropic, a vLLM server, or the built-in mock). The gateway speaks to every
backend through this uniform interface, which is what lets the router treat
heterogeneous backends interchangeably.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator

from pydantic import BaseModel

from ..config import ProviderConfig
from ..models import ChatCompletionRequest


class ProviderResult(BaseModel):
    """Normalized non-streaming result returned by every provider."""

    content: str
    prompt_tokens: int
    completion_tokens: int
    upstream_model: str


class ProviderError(Exception):
    """Raised when an upstream call fails. ``retryable`` drives router failover."""

    def __init__(self, message: str, status_code: int = 502, retryable: bool = True):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.retryable = retryable


class Provider(abc.ABC):
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.name = config.name

    @abc.abstractmethod
    async def complete(self, request: ChatCompletionRequest, model: str) -> ProviderResult:
        """Return a full completion."""

    @abc.abstractmethod
    def stream(self, request: ChatCompletionRequest, model: str) -> AsyncIterator[str]:
        """Yield content deltas (token chunks) as they arrive."""

    async def aclose(self) -> None:  # pragma: no cover - optional override
        """Release any held resources (HTTP clients, etc.)."""
        return None
