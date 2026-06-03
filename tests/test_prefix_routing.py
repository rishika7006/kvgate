from __future__ import annotations

from infergate.cache import CacheManager
from infergate.config import (
    CacheSettings,
    Deployment,
    ModelConfig,
    PrefixKvAwareSettings,
    ProviderConfig,
    RoutingSettings,
    Settings,
)
from infergate.models import ChatCompletionRequest
from infergate.providers.mock import MockProvider
from infergate.routing import Router
from infergate.service import GatewayService


def _settings(**pkv):
    return Settings(
        routing=RoutingSettings(
            strategy="prefix_kv_aware",
            prefix_kv_aware=PrefixKvAwareSettings(block_size=4, **pkv),
        ),
        providers=[
            ProviderConfig(name="r1", type="mock", latency_ms=0),
            ProviderConfig(name="r2", type="mock", latency_ms=0),
        ],
        models=[
            ModelConfig(
                name="qwen-vl",
                deployments=[
                    Deployment(provider="r1", model="m"),
                    Deployment(provider="r2", model="m"),
                ],
            )
        ],
    )


def _router(s):
    return Router(s, {"r1": MockProvider(s.providers[0]), "r2": MockProvider(s.providers[1])})


def _req(text):
    return ChatCompletionRequest(model="qwen-vl", messages=[{"role": "user", "content": text}])


def test_router_is_prefix_aware():
    r = _router(_settings())
    assert r.affinity is not None


def test_same_prefix_routes_to_same_replica():
    r = _router(_settings())
    sys = "You are a helpful assistant. " * 30
    first = r.pick("qwen-vl", request=_req(sys + "first question"))
    # A second request sharing the long system-prompt prefix should stick to it.
    second = r.pick("qwen-vl", request=_req(sys + "second different question"))
    assert second.key == first.key


def test_identical_request_is_sticky():
    r = _router(_settings())
    req = _req("the exact same prompt repeated")
    first = r.pick("qwen-vl", request=req)
    again = r.pick("qwen-vl", request=req)
    assert again.key == first.key


def test_affinity_recorded_in_index():
    r = _router(_settings())
    req = _req("warm me up " * 10)
    chosen = r.pick("qwen-vl", request=req)
    assert r.affinity.block_count(chosen.key) > 0


def test_load_guard_prevents_snowball():
    # With a tight skew, an overloaded warm replica is bypassed for the idle one.
    s = _settings(max_inflight_skew=2)
    r = _router(s)
    req = _req("a long shared system prefix " * 20)
    first = r.pick("qwen-vl", request=req)
    # Simulate the warm replica being heavily loaded (beyond the skew).
    states = {st.key: st for st in r.states("qwen-vl")}
    states[first.key].in_flight = 10
    second = r.pick("qwen-vl", request=req)
    assert second.key != first.key  # routed to the idle replica despite the warm prefix


def test_high_skew_keeps_affinity_sticky():
    # With a generous skew, prefix affinity wins even under moderate load.
    s = _settings(max_inflight_skew=100)
    r = _router(s)
    req = _req("a long shared system prefix " * 20)
    first = r.pick("qwen-vl", request=req)
    states = {st.key: st for st in r.states("qwen-vl")}
    states[first.key].in_flight = 5
    second = r.pick("qwen-vl", request=req)
    assert second.key == first.key  # still sticky to the warm replica


async def test_service_routes_repeated_prompt_to_same_provider():
    s = _settings()
    router = _router(s)
    svc = GatewayService(s, router, CacheManager(CacheSettings(enabled=False)))
    sys = "System preamble. " * 40
    r1 = await svc.complete(_req(sys + "alpha"))
    r2 = await svc.complete(_req(sys + "beta"))
    # Both share the long prefix -> same replica serves them (warm KV reuse).
    assert r1.infergate["provider"] == r2.infergate["provider"]
