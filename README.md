<div align="center">

# 🚪 KVGate

**An OpenAI-compatible LLM inference gateway — smart routing, semantic caching, rate limiting, and full observability.**

[![CI](https://github.com/rishika7006/kvgate/actions/workflows/ci.yml/badge.svg)](https://github.com/rishika7006/kvgate/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/lint-ruff-orange.svg)](https://github.com/astral-sh/ruff)

</div>

KVGate sits in front of your LLM backends — self-hosted **vLLM**/**TGI** servers and hosted APIs like **OpenAI** and **Anthropic** — and gives you one OpenAI-compatible endpoint with the production concerns already handled: **routing across backends, exact + semantic caching, per-tenant rate limiting, circuit breaking, and Prometheus/Grafana observability.**

> It runs **out of the box with zero API keys** thanks to a built-in deterministic mock provider, so you can clone, start, stream, and load-test in under a minute.

---

## 📊 Results (real, measured on GPU)

Benchmarked on **Llava-OneVision-7B** (a vision-language model) on rented A40 GPUs. **Honest numbers — no inflated vendor claims.** Full methodology + caveats in [`docs/BENCHMARK_REPORT.md`](docs/BENCHMARK_REPORT.md).

| | Result | Setup |
|---|---|---|
| 🧠 **Prefix-aware routing** | **1.84× lower tail latency** (TTFT p95 2783 → 1516 ms), +14% throughput, **98.6%** affinity, load stays balanced | 2× A40, one replica per GPU, 12 images, KV capped |
| ⚡ **LMCache CPU KV offload** | **up to 2.0× lower TTFT**, **+65% throughput** under memory pressure | 1× A40, working set overflows GPU KV |
| 🪶 **Gateway overhead** | **~1 ms p50, 1.7 ms p99** added latency per request — negligible vs multimodal TTFT (250–2700 ms) | zero-latency mock backend, single worker |

<p align="center">
  <img src="docs/assets/routing_ttft.png" width="48%" alt="Smart routing TTFT before/after" />
  <img src="docs/assets/lmcache_ttft.png" width="48%" alt="LMCache TTFT + throughput before/after" />
</p>

**Why it works:** round-robin scatters each image across GPUs so replicas keep re-prefilling ~6.5k vision tokens; prefix-aware routing keeps each image's KV resident on one replica (with a load guard so popular prompts don't snowball). LMCache spills overflow KV to CPU RAM and recovers it faster than recomputing it — the win appears only under memory pressure (honest: when the working set fits in GPU, there's no gain). This extends my AWS-internship work on KV-offload, generalized into a routing-aware gateway.

### Interactive results dashboard

A Next.js dashboard renders these experiments as before/after charts (plus a live-ops tab):

<p align="center"><img src="docs/assets/dashboard.png" width="80%" alt="KVGate results dashboard" /></p>

```bash
cd dashboard && npm install && npm run dev   # http://localhost:3000
```

---

## Why KVGate?

Serving open-source LLMs in production means re-solving the same problems every time: which backend gets each request, how to avoid paying twice for identical prompts, how to stop one tenant starving the rest, and how to see latency/cost/throughput. KVGate packages those into one drop-in gateway.

| Capability | What it does |
|---|---|
| 🔌 **OpenAI-compatible API** | `POST /v1/chat/completions` (streaming + blocking) and `/v1/models`. Existing OpenAI SDKs work unchanged — just change the base URL. |
| 🧭 **Smart routing** | Route a logical model across many deployments by `latency` (EWMA), `least_busy`, `cost`, `weighted`, or `round_robin`. |
| 🧠 **KV/prefix-aware routing** | `prefix_kv_aware` routes requests sharing a prompt prefix — **and the same image** — to the replica that already has that prefix's KV cache warm, maximizing engine-side reuse. Multimodal-aware and needs no cooperation from the engine. |
| ♻️ **Failover + circuit breaking** | Retryable upstream errors automatically fail over to the next-best deployment; repeatedly-failing deployments are ejected and given cooldown. |
| ⚡ **Exact + semantic caching** | Identical requests hit an exact cache; *similar* prompts hit a semantic cache (cosine similarity). Redis backend enables **cross-replica reuse**. |
| 🚦 **Rate limiting** | Token-bucket limits per API key / tenant, in-memory or Redis (distributed). |
| 💰 **Per-tenant budgets** | Spend caps per tenant/API key; once a tenant's estimated spend exceeds its cap in the window, requests are rejected with HTTP 402 until reset. |
| 📊 **Observability** | Prometheus metrics at `/metrics`, a ready-made Grafana dashboard, and `/admin/stats` for live routing state. |
| 🧪 **Runs with no keys** | A deterministic mock provider + dependency-free hashing embedder mean everything works offline for demos, CI, and load tests. |

---

## How KVGate compares

Most "LLM gateways" are **provider-aggregation proxies**: one API in front of OpenAI/Anthropic/Gemini, with *response* caching and cost routing. KVGate operates one layer deeper — at the **KV-cache layer** of a self-hosted vLLM fleet.

| | Provider-aggregation gateways (LiteLLM, InferXgate, …) | vLLM scheduling sidecars | **KVGate** |
|---|---|---|---|
| Primary job | Fan out to many hosted providers | Admission control / scheduling | Maximize **KV-cache reuse** across a replica fleet |
| Caching | Response cache (exact/semantic) | — | Response cache **+ KV-cache offload** (GPU→CPU→Redis) |
| Routing | By cost / availability | — | **Prefix/KV-aware** (incl. per-image hash) to the warm replica |
| Multimodal | Text-focused | varies | **Vision-language first-class** (image-hash routing) |
| Evidence | Feature lists | research | **Measured GPU benchmarks** (this repo) |

KVGate also includes the table-stakes gateway features (OpenAI-compatible API, failover, rate limiting, per-tenant budgets, Prometheus/Grafana) — but its **differentiator is the KV-cache work**, which is where the measured wins come from. It's complementary to a provider proxy, not a replacement for one.

---

## Architecture

```
                       ┌─────────────────────────────────────────────────┐
   OpenAI SDK / curl   │                   KVGate                      │
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

## How KV/prefix-aware routing works (in brief)

When many LLM replicas sit behind a load balancer, a normal balancer is *KV-blind* —
it may send a request to a replica that never saw its prefix, wasting the KV cache
another replica already holds. `prefix_kv_aware` fixes this:

1. **Fingerprint** the prompt into a chain of block hashes; **each image is hashed**
   into the key, so same-text/different-image diverges and the same image collapses.
2. **Score** each replica by how long a *leading* prefix it has served recently
   (a per-replica affinity table with TTL + LRU), balanced against load.
3. **Route** to the best replica, with a **load guard** so a shared system prompt
   can't snowball all traffic onto one replica.

It **infers** affinity from traffic the gateway already sees — needing **zero
cooperation from the inference engine** (no KV-event feed), which is what keeps it
lightweight and vendor-neutral versus Kubernetes-bound systems (vLLM Production
Stack, NVIDIA Dynamo, llm-d). Full explanation + honest comparison:
[`docs/HOW_ROUTING_WORKS.md`](docs/HOW_ROUTING_WORKS.md).

## Quickstart (no API keys needed)

```bash
git clone https://github.com/rishika7006/kvgate.git
cd kvgate
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Start the gateway (uses the built-in mock providers)
kvgate run
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
    messages=[{"role": "user", "content": "What is KVGate?"}],
)
print(resp.choices[0].message.content)
print(resp.kvgate)  # gateway metadata: cache status, provider, latency, cost
```

Send the same request twice and the second response comes back from cache (`kvgate.cache == "exact"`); send a *reworded* version and watch it hit the semantic cache.

---

## Run the full stack (gateway + Redis + Prometheus + Grafana)

```bash
cp .env.example .env        # optional: add real API keys
docker compose up --build
```

| Service | URL |
|---|---|
| KVGate API | http://localhost:8080 (`/docs` for Swagger) |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin / admin) — **KVGate dashboard** pre-loaded |

---

## Connect real backends

Copy and edit the config, then point `--config` at it:

```bash
cp config/config.example.yaml config/config.yaml
export OPENAI_API_KEY=sk-...        # secrets via ${ENV} expansion, never in the file
kvgate run -c config/config.yaml
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
kvgate validate -c config/config.yaml
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
- [x] GPU benchmarks: routing (1.84× lower p95) + LMCache offload (up to 2× lower TTFT) ([`docs/BENCHMARK_REPORT.md`](docs/BENCHMARK_REPORT.md))
- [x] Next.js results dashboard — before/after charts + live-ops view ([`dashboard/`](dashboard/))
- [x] Redis-backed affinity index for cross-gateway-replica prefix routing (`affinity_backend: redis`)
- [ ] Redis-backed semantic index for cross-replica semantic cache
- [ ] Streaming failover mid-response
- [ ] Per-tenant budgets and spend caps

## License

[Apache 2.0](LICENSE)
