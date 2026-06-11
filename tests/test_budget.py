"""Per-tenant spend cap (budget) tests."""

from __future__ import annotations

import time

from kvgate.config import BudgetSettings
from kvgate.ratelimit.budget import BudgetTracker


def test_disabled_is_always_allowed():
    t = BudgetTracker(BudgetSettings(enabled=False, default_usd=0.01))
    t.record("acme", 100.0)
    assert t.check("acme", None).allowed is True


def test_no_cap_is_unlimited():
    t = BudgetTracker(BudgetSettings(enabled=True, default_usd=None))
    t.record("acme", 100.0)
    assert t.check("acme", None).allowed is True


def test_under_then_over_cap():
    t = BudgetTracker(BudgetSettings(enabled=True, default_usd=1.0))
    assert t.check("acme", None).allowed is True
    t.record("acme", 0.6)
    d = t.check("acme", None)
    assert d.allowed is True and abs(d.remaining_usd - 0.4) < 1e-6
    t.record("acme", 0.5)  # total 1.1 >= cap 1.0
    d = t.check("acme", None)
    assert d.allowed is False and d.remaining_usd == 0.0


def test_per_key_cap_overrides_default():
    t = BudgetTracker(BudgetSettings(enabled=True, default_usd=100.0))
    t.record("vip", 5.0)
    assert t.check("vip", cap_usd=2.0).allowed is False  # per-key cap of $2 is exceeded


def test_tenants_are_isolated():
    t = BudgetTracker(BudgetSettings(enabled=True, default_usd=1.0))
    t.record("a", 2.0)
    assert t.check("a", None).allowed is False
    assert t.check("b", None).allowed is True


def test_window_reset():
    t = BudgetTracker(BudgetSettings(enabled=True, default_usd=1.0, window_s=3600))
    t.record("acme", 2.0)
    assert t.check("acme", None).allowed is False
    # force the window to have started long ago -> should reset on next check
    _, spent = t._state["acme"]
    t._state["acme"] = (time.monotonic() - 4000, spent)
    assert t.check("acme", None).allowed is True


def test_api_rejects_over_budget(monkeypatch):
    """End-to-end: an authed tenant over its cap gets HTTP 402."""
    from fastapi.testclient import TestClient

    from kvgate import create_app
    from kvgate.config import (
        ApiKey,
        AuthSettings,
        BudgetSettings,
        Deployment,
        ModelConfig,
        ProviderConfig,
        Settings,
    )

    settings = Settings(
        auth=AuthSettings(enabled=True, api_keys=[ApiKey(key="k1", tenant="acme", budget_usd=0.0)]),
        budget=BudgetSettings(enabled=True, default_usd=0.0),
        providers=[ProviderConfig(name="mock", type="mock")],
        models=[ModelConfig(name="demo", deployments=[Deployment(provider="mock", model="demo")])],
    )
    settings.cache.enabled = False
    app = create_app(settings)
    client = TestClient(app)
    headers = {"Authorization": "Bearer k1"}
    body = {"model": "demo", "messages": [{"role": "user", "content": "hi"}]}
    # cap is $0.00 -> the very first request is over budget and rejected with 402
    r = client.post("/v1/chat/completions", json=body, headers=headers)
    assert r.status_code == 402
    assert "cap" in r.json()["detail"].lower()
