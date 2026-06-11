"""/v1/models — list models the gateway exposes (OpenAI-compatible)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..models import ModelCard, ModelList

router = APIRouter(prefix="/v1", tags=["models"])


@router.get("/models")
async def list_models(request: Request) -> ModelList:
    router_ = request.app.state.router
    return ModelList(data=[ModelCard(id=name) for name in router_.known_models()])
