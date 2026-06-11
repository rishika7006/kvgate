"""/admin — live introspection of routing state (powers the status dashboard)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
async def stats(request: Request) -> dict:
    router_ = request.app.state.router
    settings = request.app.state.settings
    now = time.monotonic()

    models = {}
    for model in router_.known_models():
        deployments = []
        for s in router_.states(model):
            deployments.append(
                {
                    "provider": s.dep.provider,
                    "upstream_model": s.dep.model,
                    "weight": s.dep.weight,
                    "in_flight": s.in_flight,
                    "ewma_latency_ms": round(s.ewma_latency_ms, 2),
                    "total_requests": s.total_requests,
                    "total_failures": s.total_failures,
                    "circuit_open": not s.is_available(now),
                    "cost_per_1k": round(s.cost_per_1k, 6),
                }
            )
        models[model] = deployments

    return {
        "routing_strategy": settings.routing.strategy,
        "cache": {
            "enabled": settings.cache.enabled,
            "backend": settings.cache.backend,
            "semantic": settings.cache.semantic.enabled,
            "semantic_threshold": settings.cache.semantic.threshold,
        },
        "rate_limit": {
            "enabled": settings.ratelimit.enabled,
            "default_rpm": settings.ratelimit.default_rpm,
        },
        "models": models,
    }
