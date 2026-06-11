"""GatewayService — the request orchestration core.

For each request it: checks the cache (exact then semantic), selects a deployment
via the router, calls the upstream with automatic failover on retryable errors,
records metrics/cost, and writes the result back to cache. Streaming responses are
reconstructed and cached too, and cache hits are re-streamed transparently.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Optional, Set

from .cache import CacheManager
from .config import Settings
from .models import (
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    DeltaMessage,
    Usage,
)
from .observability import metrics
from .providers.base import ProviderError
from .routing import NoDeploymentAvailable, Router


class GatewayError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _request_id() -> str:
    return "chatcmpl-" + uuid.uuid4().hex


def _cost(usage: Usage, dep) -> float:
    return (
        usage.prompt_tokens / 1000.0 * dep.cost_per_1k_input
        + usage.completion_tokens / 1000.0 * dep.cost_per_1k_output
    )


class GatewayService:
    def __init__(self, settings: Settings, router: Router, cache: CacheManager):
        self.settings = settings
        self.router = router
        self.cache = cache
        self.max_attempts = max(1, len(settings.providers))

    # ---- non-streaming ----

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        if not self.router.has_model(request.model):
            raise GatewayError(404, f"Unknown model '{request.model}'.")

        t_start = time.monotonic()

        cached = await self.cache.get(request)
        if cached is not None:
            metrics.record_cache(f"{cached.kind}_hit")
            metrics.REQUESTS.labels(request.model, "cache", "false").inc()
            resp = ChatCompletionResponse.model_validate(cached.response)
            resp.id = _request_id()
            resp.kvgate = {
                "cache": cached.kind,
                "similarity": round(cached.similarity, 4),
                "latency_ms": round((time.monotonic() - t_start) * 1000, 2),
            }
            metrics.REQUEST_LATENCY.labels(request.model).observe(time.monotonic() - t_start)
            return resp
        metrics.record_cache("miss")

        tried: Set[str] = set()
        last_error: Optional[ProviderError] = None

        for _ in range(self.max_attempts):
            try:
                state = self.router.pick(request.model, exclude=tried, request=request)
            except NoDeploymentAvailable:
                break

            provider = self.router.provider_for(state)
            metrics.INFLIGHT.labels(state.dep.provider, state.dep.model).inc()
            state.on_start()
            t_upstream = time.monotonic()
            try:
                result = await provider.complete(request, state.dep.model)
            except ProviderError as exc:
                state.on_failure()
                metrics.INFLIGHT.labels(state.dep.provider, state.dep.model).dec()
                tried.add(state.key)
                last_error = exc
                if exc.retryable:
                    metrics.ROUTING_FAILOVERS.labels(request.model, state.dep.provider).inc()
                    continue
                raise GatewayError(exc.status_code, exc.message) from exc

            upstream_latency = time.monotonic() - t_upstream
            state.on_success(upstream_latency * 1000)
            metrics.INFLIGHT.labels(state.dep.provider, state.dep.model).dec()
            metrics.UPSTREAM_LATENCY.labels(state.dep.provider, request.model).observe(
                upstream_latency
            )
            metrics.ROUTING_DECISIONS.labels(
                request.model, state.dep.provider, state.dep.model
            ).inc()

            usage = Usage(
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.prompt_tokens + result.completion_tokens,
            )
            metrics.TOKENS.labels(request.model, "prompt").inc(usage.prompt_tokens)
            metrics.TOKENS.labels(request.model, "completion").inc(usage.completion_tokens)
            metrics.COST.labels(request.model, state.dep.provider).inc(_cost(usage, state.dep))

            total_latency = time.monotonic() - t_start
            response = ChatCompletionResponse(
                id=_request_id(),
                model=request.model,
                choices=[
                    ChatCompletionChoice(
                        index=0,
                        message=ChatMessage(role="assistant", content=result.content),
                        finish_reason="stop",
                    )
                ],
                usage=usage,
                kvgate={
                    "cache": "miss",
                    "provider": state.dep.provider,
                    "upstream_model": result.upstream_model,
                    "upstream_latency_ms": round(upstream_latency * 1000, 2),
                    "latency_ms": round(total_latency * 1000, 2),
                    "estimated_cost_usd": round(_cost(usage, state.dep), 6),
                },
            )

            await self.cache.put(request, response.model_dump())
            metrics.REQUESTS.labels(request.model, "success", "false").inc()
            metrics.REQUEST_LATENCY.labels(request.model).observe(total_latency)
            return response

        metrics.REQUESTS.labels(request.model, "error", "false").inc()
        detail = last_error.message if last_error else "no healthy deployment available"
        raise GatewayError(503, f"All upstream deployments failed: {detail}")

    # ---- streaming (Server-Sent Events) ----

    async def stream(self, request: ChatCompletionRequest) -> AsyncIterator[str]:
        if not self.router.has_model(request.model):
            raise GatewayError(404, f"Unknown model '{request.model}'.")

        cached = await self.cache.get(request)
        if cached is not None:
            metrics.record_cache(f"{cached.kind}_hit")
            metrics.REQUESTS.labels(request.model, "cache", "true").inc()
            content = cached.response["choices"][0]["message"]["content"]
            async for line in self._restream(request.model, content, cache_kind=cached.kind):
                yield line
            return
        metrics.record_cache("miss")

        tried: Set[str] = set()
        last_error: Optional[ProviderError] = None
        response_id = _request_id()

        for _ in range(self.max_attempts):
            try:
                state = self.router.pick(request.model, exclude=tried, request=request)
            except NoDeploymentAvailable:
                break

            provider = self.router.provider_for(state)
            metrics.INFLIGHT.labels(state.dep.provider, state.dep.model).inc()
            state.on_start()
            t_upstream = time.monotonic()
            collected: list = []
            stream_iter = provider.stream(request, state.dep.model)

            try:
                first = await stream_iter.__anext__()
            except StopAsyncIteration:
                first = None
            except ProviderError as exc:
                state.on_failure()
                metrics.INFLIGHT.labels(state.dep.provider, state.dep.model).dec()
                tried.add(state.key)
                last_error = exc
                if exc.retryable:
                    metrics.ROUTING_FAILOVERS.labels(request.model, state.dep.provider).inc()
                    continue
                yield _sse_error(exc.message)
                return

            metrics.ROUTING_DECISIONS.labels(
                request.model, state.dep.provider, state.dep.model
            ).inc()
            yield _sse_chunk(response_id, request.model, role="assistant")

            if first:
                collected.append(first)
                yield _sse_chunk(response_id, request.model, content=first)
            async for piece in stream_iter:
                collected.append(piece)
                yield _sse_chunk(response_id, request.model, content=piece)

            yield _sse_chunk(response_id, request.model, finish_reason="stop")
            yield "data: [DONE]\n\n"

            upstream_latency = time.monotonic() - t_upstream
            state.on_success(upstream_latency * 1000)
            metrics.INFLIGHT.labels(state.dep.provider, state.dep.model).dec()
            metrics.UPSTREAM_LATENCY.labels(state.dep.provider, request.model).observe(
                upstream_latency
            )
            metrics.REQUESTS.labels(request.model, "success", "true").inc()
            metrics.REQUEST_LATENCY.labels(request.model).observe(upstream_latency)

            await self._cache_stream(request, state, "".join(collected))
            return

        detail = last_error.message if last_error else "no healthy deployment available"
        yield _sse_error(f"All upstream deployments failed: {detail}")

    async def _restream(self, model: str, content: str, cache_kind: str) -> AsyncIterator[str]:
        response_id = _request_id()
        yield _sse_chunk(response_id, model, role="assistant", cache=cache_kind)
        for token in content.split(" "):
            yield _sse_chunk(response_id, model, content=token + " ")
        yield _sse_chunk(response_id, model, finish_reason="stop")
        yield "data: [DONE]\n\n"

    async def _cache_stream(self, request, state, content: str) -> None:
        from .models import estimate_tokens

        prompt_tokens = estimate_tokens(request.prompt_text())
        completion_tokens = estimate_tokens(content)
        usage = Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        metrics.TOKENS.labels(request.model, "prompt").inc(prompt_tokens)
        metrics.TOKENS.labels(request.model, "completion").inc(completion_tokens)
        metrics.COST.labels(request.model, state.dep.provider).inc(_cost(usage, state.dep))
        response = ChatCompletionResponse(
            id=_request_id(),
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=content),
                    finish_reason="stop",
                )
            ],
            usage=usage,
            kvgate={"cache": "miss", "provider": state.dep.provider},
        )
        await self.cache.put(request, response.model_dump())


def _sse_chunk(
    response_id: str,
    model: str,
    role: Optional[str] = None,
    content: Optional[str] = None,
    finish_reason: Optional[str] = None,
    cache: Optional[str] = None,
) -> str:
    delta = DeltaMessage(role=role, content=content)
    chunk = ChatCompletionChunk(
        id=response_id,
        model=model,
        choices=[ChatCompletionChunkChoice(index=0, delta=delta, finish_reason=finish_reason)],
    )
    payload = chunk.model_dump(exclude_none=True)
    if cache:
        payload["kvgate"] = {"cache": cache}
    return f"data: {json.dumps(payload)}\n\n"


def _sse_error(message: str) -> str:
    return f"data: {json.dumps({'error': {'message': message, 'type': 'gateway_error'}})}\n\n"
