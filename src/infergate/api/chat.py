"""/v1/chat/completions — OpenAI-compatible chat endpoint (streaming + blocking)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..middleware.auth import Principal, get_principal
from ..models import ChatCompletionRequest
from ..observability import metrics
from ..service import GatewayError

router = APIRouter(prefix="/v1", tags=["chat"])


async def _enforce_rate_limit(request: Request, principal: Principal) -> None:
    limiter = request.app.state.rate_limiter
    decision = await limiter.check(principal.tenant, principal.rpm)
    if not decision.allowed:
        metrics.RATE_LIMITED.labels(principal.tenant).inc()
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded.",
            headers={
                "Retry-After": str(int(decision.retry_after_s) + 1),
                "X-RateLimit-Limit": str(decision.limit_rpm),
            },
        )


@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
    principal: Principal = Depends(get_principal),
):
    await _enforce_rate_limit(request, principal)
    service = request.app.state.service

    if body.stream:

        async def event_stream():
            try:
                async for line in service.stream(body):
                    yield line
            except GatewayError as exc:  # pragma: no cover - defensive
                yield f'data: {{"error": {{"message": {exc.message!r}}}}}\n\n'

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        response = await service.complete(body)
    except GatewayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return response
