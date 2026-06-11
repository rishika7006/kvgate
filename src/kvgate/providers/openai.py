"""OpenAI-style providers (OpenAI, and any OpenAI-compatible server such as vLLM,
TGI, Ollama, LM Studio, or LocalAI).

vLLM in particular exposes an OpenAI-compatible ``/v1/chat/completions`` endpoint,
so the same client works for hosted OpenAI and your own self-hosted GPU server —
you just point ``base_url`` at it. This mirrors the kind of vLLM serving stack
KVGate is designed to sit in front of.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from ..config import ProviderConfig
from ..models import ChatCompletionRequest, estimate_tokens
from .base import Provider, ProviderError, ProviderResult


class OpenAIProvider(Provider):
    default_base_url = "https://api.openai.com/v1"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = (config.base_url or self.default_base_url).rstrip("/")
        self.api_key = config.api_key
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _payload(self, request: ChatCompletionRequest, model: str, stream: bool) -> dict:
        payload = {
            "model": model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": stream,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.stop is not None:
            payload["stop"] = request.stop
        return payload

    async def complete(self, request: ChatCompletionRequest, model: str) -> ProviderResult:
        try:
            resp = await self._client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(request, model, stream=False),
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name}: network error: {exc}", retryable=True) from exc

        if resp.status_code >= 400:
            retryable = resp.status_code in (408, 409, 429, 500, 502, 503, 504)
            raise ProviderError(
                f"{self.name}: upstream {resp.status_code}: {resp.text[:300]}",
                status_code=resp.status_code,
                retryable=retryable,
            )

        data = resp.json()
        content = data["choices"][0]["message"].get("content", "") or ""
        usage = data.get("usage", {})
        return ProviderResult(
            content=content,
            prompt_tokens=usage.get("prompt_tokens", estimate_tokens(request.prompt_text())),
            completion_tokens=usage.get("completion_tokens", estimate_tokens(content)),
            upstream_model=data.get("model", model),
        )

    async def stream(self, request: ChatCompletionRequest, model: str) -> AsyncIterator[str]:
        try:
            async with self._client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
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
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = chunk["choices"][0].get("delta", {})
                    piece = delta.get("content")
                    if piece:
                        yield piece
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.name}: network error: {exc}", retryable=True) from exc

    async def aclose(self) -> None:
        await self._client.aclose()


class OpenAICompatibleProvider(OpenAIProvider):
    """Self-hosted OpenAI-compatible server (e.g. vLLM). ``base_url`` is required."""

    default_base_url = "http://localhost:8000/v1"
