"""Provider registry and factory."""

from __future__ import annotations

from typing import Callable, Dict

from ..config import ProviderConfig
from .anthropic import AnthropicProvider
from .base import Provider, ProviderError, ProviderResult
from .mock import MockProvider
from .openai import OpenAICompatibleProvider, OpenAIProvider

_REGISTRY: Dict[str, Callable[[ProviderConfig], Provider]] = {
    "mock": MockProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "openai_compatible": OpenAICompatibleProvider,
}


def build_provider(config: ProviderConfig) -> Provider:
    try:
        cls = _REGISTRY[config.type]
    except KeyError as exc:  # pragma: no cover - guarded by pydantic Literal
        raise ValueError(f"Unknown provider type: {config.type}") from exc
    return cls(config)


def build_providers(configs: list) -> Dict[str, Provider]:
    return {c.name: build_provider(c) for c in configs}


__all__ = [
    "Provider",
    "ProviderError",
    "ProviderResult",
    "MockProvider",
    "OpenAIProvider",
    "OpenAICompatibleProvider",
    "AnthropicProvider",
    "build_provider",
    "build_providers",
]
