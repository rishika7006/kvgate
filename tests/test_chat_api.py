from __future__ import annotations

import json


def _chat(client, content, **kw):
    body = {"model": "demo", "messages": [{"role": "user", "content": content}]}
    body.update(kw)
    return client.post("/v1/chat/completions", json=body)


def test_basic_completion(client):
    r = _chat(client, "hello world")
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert data["choices"][0]["message"]["content"]
    assert data["usage"]["total_tokens"] > 0
    assert data["infergate"]["cache"] == "miss"
    assert "estimated_cost_usd" in data["infergate"]


def test_exact_cache_hit(client):
    first = _chat(client, "cache me please").json()
    second = _chat(client, "cache me please").json()
    assert first["infergate"]["cache"] == "miss"
    assert second["infergate"]["cache"] == "exact"
    # Same content returned, but a fresh id each time.
    assert first["choices"][0]["message"]["content"] == second["choices"][0]["message"]["content"]
    assert first["id"] != second["id"]


def test_unknown_model_404(client):
    r = client.post(
        "/v1/chat/completions",
        json={"model": "nope", "messages": [{"role": "user", "content": "x"}]},
    )
    assert r.status_code == 404


def test_streaming(client):
    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={"model": "demo", "stream": True, "messages": [{"role": "user", "content": "stream"}]},
    ) as r:
        assert r.status_code == 200
        lines = [ln for ln in r.iter_lines() if ln]
    assert lines[-1] == "data: [DONE]"
    # first data chunk carries the assistant role
    payload = json.loads(lines[0][len("data: ") :])
    assert payload["choices"][0]["delta"].get("role") == "assistant"


def test_models_endpoint(client):
    r = client.get("/v1/models")
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()["data"]]
    assert "demo" in ids


def test_health_and_ready(client):
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/readyz").json()["status"] == "ready"


def test_metrics_endpoint(client):
    _chat(client, "metric check")
    body = client.get("/metrics").text
    assert "infergate_requests_total" in body
    assert "infergate_cache_events_total" in body


def test_admin_stats(client):
    _chat(client, "warm up routing state")
    data = client.get("/admin/stats").json()
    assert "demo" in data["models"]
    deployments = data["models"]["demo"]
    assert len(deployments) == 2
    assert {"provider", "in_flight", "ewma_latency_ms", "circuit_open"} <= set(deployments[0])


def test_streaming_served_from_cache(client):
    # Prime the cache with a blocking request, then stream the same prompt.
    _chat(client, "re-stream me")
    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "demo",
            "stream": True,
            "messages": [{"role": "user", "content": "re-stream me"}],
        },
    ) as r:
        lines = [ln for ln in r.iter_lines() if ln]
    first = json.loads(lines[0][len("data: ") :])
    assert first["infergate"]["cache"] == "exact"
    assert lines[-1] == "data: [DONE]"
