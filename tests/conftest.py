from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from infergate import create_app
from infergate.config import (
    CacheSettings,
    Deployment,
    ModelConfig,
    ProviderConfig,
    RateLimitSettings,
    SemanticCacheSettings,
    Settings,
)


def make_settings(**overrides) -> Settings:
    base = Settings(
        providers=[
            ProviderConfig(name="mock-a", type="mock", latency_ms=1, tokens_per_second=10000),
            ProviderConfig(name="mock-b", type="mock", latency_ms=1, tokens_per_second=10000),
        ],
        models=[
            ModelConfig(
                name="demo",
                deployments=[
                    Deployment(
                        provider="mock-a",
                        model="mock-a",
                        weight=1,
                        cost_per_1k_input=0.001,
                        cost_per_1k_output=0.002,
                    ),
                    Deployment(
                        provider="mock-b",
                        model="mock-b",
                        weight=1,
                        cost_per_1k_input=0.003,
                        cost_per_1k_output=0.004,
                    ),
                ],
            )
        ],
        cache=CacheSettings(semantic=SemanticCacheSettings(enabled=True, threshold=0.95)),
        ratelimit=RateLimitSettings(enabled=False),
    )
    data = base.model_dump()
    data.update(overrides)
    return Settings.model_validate(data)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def client(settings) -> TestClient:
    with TestClient(create_app(settings)) as c:
        yield c
