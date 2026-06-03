<div align="center">

# 🚪 InferGate

**An OpenAI-compatible LLM inference gateway — smart routing, semantic caching, rate limiting, and full observability.**

[![CI](https://github.com/rishabhvaish/infergate/actions/workflows/ci.yml/badge.svg)](https://github.com/rishabhvaish/infergate/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/lint-ruff-orange.svg)](https://github.com/astral-sh/ruff)

</div>

InferGate sits in front of your LLM backends — self-hosted **vLLM**/**TGI** servers and hosted APIs like **OpenAI** and **Anthropic** — and gives you one OpenAI-compatible endpoint with the production concerns already handled: **routing across backends, exact + semantic caching, per-tenant rate limiting, circuit breaking, and Prometheus/Grafana observability.**

> It runs **out of the box with zero API keys** thanks to a built-in deterministic mock provider, so you can clone, start, stream, and load-test in under a minute.

---

## Why InferGate?

Serving open-source LLMs in production means re-solving the same problems every time: which backend gets each request, how to avoid paying twice for identical prompts, how to stop one tenant starving the rest, and how to see latency/cost/throughput. InferGate packages those into one drop-in gateway.

| Capability | What it does |
|---|---|
| 🔌 **OpenAI-compatible API** | `POST /v1/chat/completions` (streaming + blocking) and `/v1/models`. Existing OpenAI SDKs work unchanged — just change the base URL. |
| 🧭 **Smart routing** | Route a logical model across many deployments by `latency` (EWMA), `least_busy`, `cost`, `weighted`, or `round_robin`. |
| 🧠 **KV/prefix-aware routing** | `prefix_kv_aware` routes requests sharing a prompt prefix — **and the same image** — to the replica that already has that prefix's KV cache warm, maximizing engine-side reuse. Multimodal-aware and needs no cooperation from the engine. |
| ♻️ **Failover + circuit breaking** | Retryable upstream errors automatically fail over to the next-best deployment; repeatedly-failing deployments are ejected and given cooldown. |
| ⚡ **Exact + semantic caching** | Identical requests hit an exact cache; *similar* prompts hit a semantic cache (cosine similarity). Redis backend enables **cross-replica reuse**. |
| 🚦 **Rate limiting** | Token-bucket limits per API key / tenant, in-memory or Redis (distributed). |
| 📊 **Observability** | Prometheus metrics at `/metrics`, a ready-made Grafana dashboard, and `/admin/stats` for live routing state. |
| 🧪 **Runs with no keys** | A deterministic mock provider + dependency-free hashing embedder mean everything works offline for demos, CI, and load tests. |

---

## Architecture

```
                       ┌─────────────────────────────────────────────────┐
   OpenAI SDK / curl   │                   InferGate                      │
        │              │                                                  │
        ▼              │   Auth ─▶ Rate limit ─▶ Cache ─▶ Router ─▶ ...    │
  POST /v1/chat/────────▶ (tenant)   (token      (exact +   (latency /     │
      completions      │             bucket)     semantic)  cost / busy)   │
                       │                            │           │          │
                       │                       hit ◀┘           ▼          │
                       │                                 ┌──────────────┐  │
                       │   /metrics  /admin/stats        │  failover +  │  │
                       │   (Prometheus)                  │ circuit break│  │
                       └─────────────────────────────────┴──────┬───────┘  │
                                                                 │
                          ┌──────────────────┬───────────────────┼───────────────┐
                          ▼                  ▼                    ▼               ▼
                     mock provider     vLLM / TGI            OpenAI API     Anthropic API
                    (zero-dep demo)  (self-hosted GPU)        (hosted)        (hosted)
```

---

## Quickstart (no API keys needed)

```bash
git clone https://github.com/rishabhvaish/infergate.git
cd infergate
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Start the gateway (uses the built-in mock providers)
infergate run
```

In another terminal:

```bash
# Blocking request
curl -s localhost:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"demo","messages":[{"role":"user","content":"Hello!"}]}' | jq

# Streaming (Server-Sent Events)
curl -N localhost:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"demo","stream":true,"messages":[{"role":"user","content":"Stream this"}]}'
```

Use it from the **OpenAI Python SDK** unchanged:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8080/v1", api_key="not-needed")
resp = client.chat.completions.create(
    model="demo",
    messages=[{"role": "user", "content": "What is InferGate?"}],
)
print(resp.choices[0].message.content)
print(resp.infergate)  # gateway metadata: cache status, provider, latency, cost
```

Send the same request twice and the second response comes back from cache (`infergate.cache == "exact"`); send a *reworded* version and watch it hit the semantic cache.

---

## Run the full stack (gateway + Redis + Prometheus + Grafana)

```bash
cp .env.example .env        # optional: add real API keys
docker compose up --build
```

| Service | URL |
|---|---|
| InferGate API | http://localhost:8080 (`/docs` for Swagger) |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin / admin) — **InferGate dashboard** pre-loaded |

---

## Connect real backends

Copy and edit the config, then point `--config` at it:

```bash
cp config/config.example.yaml config/config.yaml
export OPENAI_API_KEY=sk-...        # secrets via ${ENV} expansion, never in the file
infergate run -c config/config.yaml
```

A **model** is a logical name clients request; it fans out to one or more **deployments** (provider + upstream model). Example — serve a logical `gpt-4o` mostly from your own vLLM box and overflow to hosted OpenAI:

```yaml
routing:
  strategy: cost            # prefer the cheapest healthy deployment
models:
  - name: gpt-4o
    deployments:
      - { provider: vllm-local, model: meta-llama/Llama-3.1-8B-Instruct, cost_per_1k_input: 0.0,   cost_per_1k_output: 0.0 }
      - { provider: openai,     model: gpt-4o,                           cost_per_1k_input: 0.005, cost_per_1k_output: 0.015 }
```

Supported provider types: `mock`, `openai`, `openai_compatible` (vLLM/TGI/Ollama/LocalAI), `anthropic`.

---

## Load testing

A [Locust](https://locust.io) harness is included. It hammers the gateway through the mock providers so you can benchmark routing/caching with no upstream cost:

```bash
locust -f loadtest/locustfile.py --host http://localhost:8080
# headless: locust -f loadtest/locustfile.py --host http://localhost:8080 -u 50 -r 10 -t 60s --headless
```

Watch the cache hit rate and p99 latency move in Grafana as concurrency climbs.

---

## API reference

| Endpoint | Description |
|---|---|
| `POST /v1/chat/completions` | Chat completions, `stream: true\|false`. OpenAI-compatible. |
| `GET /v1/models` | List logical models the gateway serves. |
| `GET /healthz` / `GET /readyz` | Liveness / readiness probes. |
| `GET /metrics` | Prometheus exposition format. |
| `GET /admin/stats` | Live routing state: per-deployment latency, in-flight, circuit status, cost. |
| `GET /docs` | Swagger UI. |

---

## Configuration reference

See [`config/config.example.yaml`](config/config.example.yaml) for the full, commented schema. Highlights:

- `routing.strategy`: `round_robin` · `weighted` · `latency` · `least_busy` · `cost` · `prefix_kv_aware`
- `cache.backend`: `memory` · `redis`; `cache.semantic.embedder`: `hashing` · `sentence_transformers` · `openai`
- `ratelimit.backend`: `memory` · `redis`; `default_rpm`, `burst`
- `routing.failure_threshold` / `routing.cooldown_s`: circuit breaker tuning

Validate any config:

```bash
infergate validate -c config/config.yaml
```

---

## Development

```bash
pip install -e ".[dev]"
pytest                 # run the test suite
ruff check .           # lint
ruff format .          # format
mypy src               # type-check
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Roadmap

- [x] Multimodal KV/prefix-aware routing (`prefix_kv_aware`) — image-hash-aware affinity
- [ ] Next.js dashboard (live tokens/sec, p99, cache hit rate, cost per model)
- [ ] Redis-backed affinity index for cross-gateway-replica prefix routing
- [ ] Redis-backed semantic index for cross-replica semantic cache
- [ ] Streaming failover mid-response
- [ ] Per-tenant budgets and spend caps

## License

[Apache 2.0](LICENSE)
