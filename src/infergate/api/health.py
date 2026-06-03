"""Health, readiness, and Prometheus metrics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ..observability.metrics import REGISTRY

router = APIRouter(tags=["ops"])


@router.get("/healthz")
async def healthz() -> dict:
    """Liveness: the process is up."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> dict:
    """Readiness: at least one model with a deployment is configured."""
    router_ = request.app.state.router
    models = router_.known_models()
    ready = len(models) > 0
    return {"status": "ready" if ready else "not_ready", "models": models}


@router.get("/metrics")
async def metrics_endpoint() -> Response:
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
