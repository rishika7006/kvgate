from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from kvgate.cache import CacheManager
from kvgate.config import (
    CacheSettings,
    Deployment,
    ModelConfig,
    ProviderConfig,
    RoutingSettings,
    Settings,
)
from kvgate.models import ChatCompletionRequest
from kvgate.providers.base import Provider, ProviderError, ProviderResult
from kvgate.providers.mock import MockProvider
from kvgate.routing import NoDeploymentAvailable, Router
from kvgate.service import GatewayError, GatewayService


class FailingProvider(Provider):
    def __init__(self, config, retryable=True):
        super().__init__(config)
        self.retryable = retryable
        self.calls = 0

    async def complete(self, request, model) -> ProviderResult:
        self.calls += 1
        raise ProviderError("boom", status_code=503, retryable=self.retryable)

    async def stream(self, request, model) -> AsyncIterator[str]:
        self.calls += 1
        raise ProviderError("boom", status_code=503, retryable=self.retryable)
        yield  # pragma: no cover


def _settings(strategy="latency"):
    return Settings(
        routing=RoutingSettings(strategy=strategy, failure_threshold=2, cooldown_s=100),
        providers=[
            ProviderConfig(name="bad", type="mock"),
            ProviderConfig(name="good", type="mock", latency_ms=1),
        ],
        models=[
            ModelConfig(
                name="demo",
                deployments=[
                    Deployment(provider="bad", model="bad"),
                    Deployment(provider="good", model="good"),
                ],
            )
        ],
    )


def _req(content="hi"):
    return ChatCompletionRequest(model="demo", messages=[{"role": "user", "content": content}])


def test_pick_unknown_model_raises():
    s = _settings()
    r = Router(s, {"bad": MockProvider(s.providers[0]), "good": MockProvider(s.providers[1])})
    with pytest.raises(NoDeploymentAvailable):
        r.pick("does-not-exist")


def test_pick_excludes_tried():
    s = _settings(strategy="round_robin")
    r = Router(s, {"bad": MockProvider(s.providers[0]), "good": MockProvider(s.providers[1])})
    first = r.pick("demo")
    second = r.pick("demo", exclude={first.key})
    assert first.key != second.key


async def test_failover_to_healthy_deployment():
    s = _settings()
    bad = FailingProvider(s.providers[0])
    good = MockProvider(s.providers[1])
    router = Router(s, {"bad": bad, "good": good})
    svc = GatewayService(s, router, CacheManager(CacheSettings(enabled=False)))

    resp = await svc.complete(_req())
    assert resp.kvgate["provider"] == "good"
    assert bad.calls >= 1  # the bad deployment was attempted and failed over


async def test_non_retryable_error_propagates():
    s = _settings()
    s.models[0].deployments = [Deployment(provider="bad", model="bad")]
    bad = FailingProvider(s.providers[0], retryable=False)
    router = Router(s, {"bad": bad})
    svc = GatewayService(s, router, CacheManager(CacheSettings(enabled=False)))
    with pytest.raises(GatewayError) as exc:
        await svc.complete(_req())
    assert exc.value.status_code == 503


async def test_circuit_breaker_opens_after_threshold():
    s = _settings()
    s.models[0].deployments = [Deployment(provider="bad", model="bad")]
    bad = FailingProvider(s.providers[0])
    router = Router(s, {"bad": bad})
    svc = GatewayService(s, router, CacheManager(CacheSettings(enabled=False)))

    for _ in range(2):
        with pytest.raises(GatewayError):
            await svc.complete(_req())

    state = router.states("demo")[0]
    import time

    assert not state.is_available(time.monotonic())  # circuit is open


def test_cost_strategy_picks_cheapest():
    s = Settings(
        routing=RoutingSettings(strategy="cost"),
        providers=[ProviderConfig(name="a", type="mock"), ProviderConfig(name="b", type="mock")],
        models=[
            ModelConfig(
                name="demo",
                deployments=[
                    Deployment(
                        provider="a", model="a", cost_per_1k_input=1.0, cost_per_1k_output=1.0
                    ),
                    Deployment(
                        provider="b", model="b", cost_per_1k_input=0.1, cost_per_1k_output=0.1
                    ),
                ],
            )
        ],
    )
    r = Router(s, {"a": MockProvider(s.providers[0]), "b": MockProvider(s.providers[1])})
    assert r.pick("demo").dep.provider == "b"
