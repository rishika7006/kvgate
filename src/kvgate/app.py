"""FastAPI application factory.

Wires the config into live components (providers → router, cache, rate limiter,
service) and exposes them on ``app.state`` so routes and dependencies can reach
them. Resources are torn down cleanly on shutdown via the lifespan handler.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import admin, chat, health
from .api import models as models_api
from .cache import build_cache
from .config import Settings, load_settings
from .providers import build_providers
from .ratelimit import build_rate_limiter
from .ratelimit.budget import BudgetTracker
from .routing import Router
from .service import GatewayService

logger = logging.getLogger("kvgate")


def create_app(settings: Optional[Settings] = None, config_path: Optional[str] = None) -> FastAPI:
    settings = settings or load_settings(config_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(
            "KVGate starting: %d providers, %d models, strategy=%s, cache=%s",
            len(settings.providers),
            len(settings.models),
            settings.routing.strategy,
            settings.cache.backend if settings.cache.enabled else "off",
        )
        yield
        for provider in app.state.providers.values():
            await provider.aclose()
        await app.state.cache.aclose()
        await app.state.rate_limiter.aclose()
        logger.info("KVGate shut down cleanly.")

    app = FastAPI(
        title="KVGate",
        description=(
            "OpenAI-compatible LLM inference gateway: "
            "routing, caching, rate limiting, observability."
        ),
        version=__import__("kvgate").__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    providers = build_providers(settings.providers)
    router = Router(settings, providers)
    cache = build_cache(settings.cache)
    rate_limiter = build_rate_limiter(settings.ratelimit)
    budget = BudgetTracker(settings.budget)
    service = GatewayService(settings, router, cache)

    app.state.settings = settings
    app.state.providers = providers
    app.state.router = router
    app.state.cache = cache
    app.state.rate_limiter = rate_limiter
    app.state.budget = budget
    app.state.service = service
    app.state.api_key_map = {k.key: k for k in settings.auth.api_keys}

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(models_api.router)
    app.include_router(admin.router)

    @app.get("/", tags=["ops"])
    async def root() -> dict:
        return {
            "name": "KVGate",
            "version": app.version,
            "docs": "/docs",
            "endpoints": ["/v1/chat/completions", "/v1/models", "/metrics", "/admin/stats"],
        }

    return app
