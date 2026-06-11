from __future__ import annotations

import httpx
import pytest
import respx

from kvgate.config import ProviderConfig
from kvgate.models import ChatCompletionRequest
from kvgate.providers import build_provider
from kvgate.providers.anthropic import AnthropicProvider
from kvgate.providers.base import ProviderError
from kvgate.providers.mock import MockProvider
from kvgate.providers.openai import OpenAIProvider


def _req(content="hello"):
    return ChatCompletionRequest(model="m", messages=[{"role": "user", "content": content}])


async def test_mock_provider_is_deterministic():
    p = MockProvider(ProviderConfig(name="m", type="mock", latency_ms=0))
    a = await p.complete(_req("same"), "m")
    b = await p.complete(_req("same"), "m")
    assert a.content == b.content
    assert a.completion_tokens > 0


async def test_mock_provider_streams_tokens():
    p = MockProvider(ProviderConfig(name="m", type="mock", latency_ms=0, tokens_per_second=100000))
    pieces = [piece async for piece in p.stream(_req(), "m")]
    assert len(pieces) > 1
    assert "".join(pieces).strip()


def test_build_provider_registry():
    assert isinstance(build_provider(ProviderConfig(name="x", type="mock")), MockProvider)
    assert isinstance(
        build_provider(ProviderConfig(name="x", type="openai", api_key="k")), OpenAIProvider
    )
    assert isinstance(
        build_provider(ProviderConfig(name="x", type="anthropic", api_key="k")), AnthropicProvider
    )


@respx.mock
async def test_openai_provider_complete():
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "gpt-4o",
                "choices": [{"message": {"role": "assistant", "content": "hi there"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        )
    )
    p = OpenAIProvider(ProviderConfig(name="openai", type="openai", api_key="sk-test"))
    result = await p.complete(_req(), "gpt-4o")
    await p.aclose()
    assert route.called
    assert result.content == "hi there"
    assert result.prompt_tokens == 3 and result.completion_tokens == 2


@respx.mock
async def test_openai_provider_maps_429_to_retryable():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(429, text="rate limited")
    )
    p = OpenAIProvider(ProviderConfig(name="openai", type="openai", api_key="sk-test"))
    with pytest.raises(ProviderError) as exc:
        await p.complete(_req(), "gpt-4o")
    await p.aclose()
    assert exc.value.retryable is True
    assert exc.value.status_code == 429


@respx.mock
async def test_anthropic_provider_translates_response():
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "claude-3-5-sonnet",
                "content": [{"type": "text", "text": "translated reply"}],
                "usage": {"input_tokens": 5, "output_tokens": 4},
            },
        )
    )
    p = AnthropicProvider(ProviderConfig(name="anthropic", type="anthropic", api_key="k"))
    result = await p.complete(_req(), "claude-3-5-sonnet")
    await p.aclose()
    assert result.content == "translated reply"
    assert result.prompt_tokens == 5 and result.completion_tokens == 4
