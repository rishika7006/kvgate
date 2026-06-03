"""Anthropic Messages API provider.

Anthropic uses a different request/response shape than OpenAI (system prompt is a
top-level field, content is a list of blocks, SSE event types differ), so this
provider translates between InferGate's OpenAI-shaped requests and the Anthropic
Messages API in both directions.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import List, Tuple

import httpx

from ..config import ProviderConfig
from ..models import ChatCompletionRequest, ChatMessage, estimate_tokens
from .base import Provider, ProviderError, ProviderResult

_ANTHROPIC_VERSION = "2023-06-01"


def _split_system(messages: List[ChatMessage]) -> Tuple[str, list]:
    system_parts, convo = [], []
    for m in messages:
        if m.role == "system":
            system_parts.append(m.content or "")
        else:
            role = "assistant" if m.role == "assistant" else "user"
            convo.append({"role": role, "content": m.content or ""})
    return "\n".join(system_parts), convo


class AnthropicProvider(Provider):
    default_base_url = "https://api.anthropic.com/v1"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = (config.base_url or self.default_base_url).rstrip("/")
        self.api_key = config.api_key
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key or "",
            "anthropic-version": _ANTHROPIC_VERSION,
        }

    def _payload(self, request: ChatCompletionRequest, model: str, stream: bool) -> dict:
        system, convo = _split_system(request.messages)
        payload = {
            "model": model,
            "messages": convo,
            "max_tokens": request.max_tokens or 1024,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": stream,
        }
        if system:
            payload["system"] = system
        return payload

    async def complete(self, request: ChatCompletionRequest, model: str) -> ProviderResult:
        try:
            resp = await self._client.post(
                f"{self.base_url}/messages",
                headers=self._headers(),
                json=self._payload(request, model, stream=False),
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name}: network error: {exc}", retryable=True) from exc

        if resp.status_code >= 400:
            raise ProviderError(
                f"{self.name}: upstream {resp.status_code}: {resp.text[:300]}",
                status_code=resp.status_code,
                retryable=resp.status_code in (429, 500, 502, 503, 504),
            )

        data = resp.json()
        content = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        usage = data.get("usage", {})
        return ProviderResult(
            content=content,
            prompt_tokens=usage.get("input_tokens", estimate_tokens(request.prompt_text())),
            completion_tokens=usage.get("output_tokens", estimate_tokens(content)),
            upstream_model=data.get("model", model),
        )

    async def stream(self, request: ChatCompletionRequest, model: str) -> AsyncIterator[str]:
        try:
            async with self._client.stream(
                "POST",
                f"{self.base_url}/messages",
                headers=self._headers(),
                json=self._payload(request, model, stream=True),
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise ProviderError(
                        f"{self.name}: upstream {resp.status_code}: {body[:300]!r}",
                        status_code=resp.status_code,
                        retryable=resp.status_code in (429, 500, 502, 503, 504),
                    )
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "content_block_delta":
                        piece = event.get("delta", {}).get("text")
                        if piece:
                            yield piece
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name}: network error: {exc}", retryable=True) from exc

    async def aclose(self) -> None:
        await self._client.aclose()
