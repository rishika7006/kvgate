# InferGate — Full Project Context (handoff for discussion)

> **Purpose of this file:** a single, self-contained brief so a fresh assistant (e.g.
> Cowork) has the *entire* context of this project. **Workflow split:** strategy /
> discussion happens in **Cowork**; hands-on **development** happens in **Claude Code**
> (this repo lives at `~/Documents/Projects/infergate`). Keep this file updated as the
> source of truth.

---

## 1. Who this is for & the goal

- **Person:** Master's in CS (UT Dallas, May 2026), targeting **new-grad SWE / ML Engineer /
  Data Engineer / AI roles**.
- **Goal:** build **one flagship, production-grade open-source project** that stands out to
  top tech recruiters and is fully defensible in interviews.
- **Key background to leverage (this is the differentiator):** AWS SDE intern who integrated
  **LMCache** with a **multimodal LLM** on **Triton + vLLM**, built a **gRPC layer for
  GPU→CPU KV-cache transfer/reuse**, and a **Redis-backed cross-host KV store**. Also: Data
  Engineer (SageMaker, Athena, PySpark), applied NLP. Skills: Python, ML/NLP, AWS, FastAPI,
  React, LangChain/LangGraph/MCP, vLLM, Docker, K8s, Redis, Kafka.
- **Resume rule from the user:** *only publish/push the repo publicly once it runs and shows
  good results.* (A private repo for development is fine — private ≠ published.)

---

## 2. The project in one paragraph

**InferGate** is an open-source, **OpenAI-compatible LLM inference gateway** — a smart
"receptionist" that sits in front of a fleet of LLM servers. Its flagship feature is
**multimodal KV/prefix-aware routing**: it sends each request to the replica that already
has that request's prefix (**including the same image**) warm in its KV cache, maximizing
reuse. It also does response caching, rate limiting, failover/circuit-breaking, and
Prometheus/Grafana observability. It runs with **zero API keys / no GPU** via a built-in
mock provider, so anyone can clone and try it instantly.

This directly extends the user's AWS KV-cache work, from a single deployment to a routed fleet.

---

## 3. CRITICAL clarification: two different optimizations, two layers

A recurring point of confusion — keep these separate:

| | **Offloading** | **Smart routing** |
|---|---|---|
| What | Save/reuse the AI's **KV cache** (its working memory); spill GPU→CPU/SSD | Decide **which server** gets each request so it lands where the cache is warm |
| Where | **Inside each GPU server** | **In our gateway, in front** |
| Tool | **LMCache** (the user's AWS tool) | **InferGate** (what we built) |
| Storage | CPU RAM / SSD (NOT our Redis) | an in-memory affinity table (Redis planned) |
| Status | ⏳ needs a GPU to run | ✅ built; ⏳ needs GPU to prove speed gain |

They **stack**: offloading makes reuse *possible*; routing makes reuse *actually happen*
across replicas. **Our gateway's Redis** (optional) is for the *response cache + rate
limiting* — **not** the KV cache. The KV cache is offloaded by **LMCache to CPU/SSD**.

**The benchmark compares BOTH, separately:** `A→C` isolates the offloading benefit
(no cache → vLLM prefix cache → +LMCache); `D→E` isolates the routing benefit
(round-robin → prefix_kv_aware). `D→E` is the headline.

---

## 4. Architecture

```
        ┌─────────────────────────────────────────────┐
        │            InferGate (our gateway)          │   ← ✅ DONE (no GPU)
        │   • OpenAI-compatible API (FastAPI)         │
        │   • Response cache (whole answers)          │
        │   • SMART ROUTING (prefix_kv_aware)         │      hashlib + collections
        │   • Rate limit, failover, circuit breaker   │
        │   • Metrics → Prometheus / Grafana          │
        └───────────────┬─────────────────┬───────────┘
                        │                 │
                        ▼                 ▼
              ┌──────────────┐    ┌──────────────┐
              │  GPU Server 1│    │ GPU Server 2 │     ← ⏳ TO DO (rented GPUs)
              │  vLLM        │    │  vLLM        │        the real AI engine
              │  + LMCache   │    │  + LMCache   │     ← OFFLOADING (CPU/SSD)
              └──────────────┘    └──────────────┘
```

---

## 5. How the smart routing works (and honest novelty)

**Mechanism** (it *predicts* cache state from traffic — it does NOT query the engine):
1. **Fingerprint** the prompt into block hashes; each image → a hash marker (so same-text/
   different-image diverges, same image collapses). *(`keying.py`, `hashlib`)*
2. **Score** each replica by longest *warm* matching prefix, from a per-replica affinity
   table with TTL + LRU. *(`affinity.py`, `collections`, `time`)*
3. **Pick** the best — with a **load guard** (`max_inflight_skew`) so a shared system-prompt
   prefix can't snowball all traffic onto one replica. *(`router.py`)*
4. **Record** the choice (that replica is now warm); entries expire over time.

**Is it novel?** The *idea* of KV-aware routing already exists in **vLLM Production Stack**,
**NVIDIA Dynamo**, and **llm-d** — so we do NOT claim to have invented it. **What's genuinely
ours:** (a) lightweight & vendor-neutral (plain Docker, no Kubernetes), (b) **needs no engine
cooperation** (infers from traffic, vs consuming KV events), (c) **multimodal-aware routing
keys**, (d) an **honest reproducible multimodal benchmark** (none exists publicly).

**Honest interview framing:** *"KV-aware routing exists in heavyweight K8s platforms; I built
a lightweight, vendor-neutral, multimodal-aware gateway that infers cache affinity from
traffic with no engine changes, and benchmarked it on vision-language models."*

---

## 6. Research findings (verified mid-2026, adversarially fact-checked)

- **vLLM** = the standard engine; **LMCache v0.4.6** = the most-adopted KV offload/reuse layer
  (reuses any repeated text via CacheBlend; offloads to CPU/Disk/NIXL/object store; integrated
  into vLLM v1, vLLM Production Stack, NVIDIA Dynamo 1.0; in prod at Google Cloud, CoreWeave).
- **Multimodal:** naive prefix matching is unsafe (same text + different image). vLLM (PR
  #11187) and LMCache (v0.3.1, PR #882) fix it via a per-image hash (`mm_hash`). Documented
  models incl. Llava-OneVision, Phi-3.5-vision, Ultravox.
- **KV-aware routing** ships in vLLM Production Stack router, Dynamo (KV events over NATS/ZMQ),
  llm-d — all heavy / Kubernetes-oriented.
- ⚠️ **Nearly all vendor performance numbers were REFUTED** (LMCache "3–10×", Mooncake "46×",
  VLCache "16.95×"). **→ We must measure our own numbers; do not cite vendor figures.**
- Full detail: `docs/RESEARCH_KV_CACHE.md`.

---

## 7. Current state — DONE vs TODO

### ✅ Done (all committed locally on `main`, NOT pushed anywhere yet)
- Core gateway v0.1.0 (API, response cache, rate limit, failover, observability, Docker, CI).
- **M1**: multimodal KV/prefix-aware routing (`keying.py`, `affinity.py`, `router.py`).
- **M1.5**: load guard (fixed a real 120/0 snowball → balanced 59/61 in the live dry run).
- **M2**: benchmark harness (`loadtest/multimodal_bench.py`) + real-image support (`--images-dir`).
- **59 tests passing**; ruff clean; mypy clean (runs in CI).
- **Next.js + TypeScript + Tailwind live dashboard** (`dashboard/`) — polls /admin/stats and
  /metrics; shows routing strategy, per-replica state, cache + KV-affinity hit rates, tokens.
  Builds and serves cleanly (verified). This covers the "modern React/Next.js frontend" goal.
- **Proven running (no GPU):** live dry run = 120/120 OK, **98.3% routing-affinity hit rate**,
  balanced across replicas.
- Docs: research, plan, decision gates, routing explainer, RunPod runbook, benchmark runbook.

### ⏳ To do (needs rented GPUs)
- **Stage 1:** run the A→E sweep on GPUs (RunPod, Llava-OneVision-7B). See `docs/RUNPOD_GUIDE.md`.
- **Stage 2 (if Stage 1 passes):** add vLLM Production Stack / Dynamo as comparison baselines.
- **Stage 3 (if Stage 2 passes):** a small OSS PR to vLLM/LMCache.
- Then: write-up + résumé bullets → **make GitHub repo public**.

---

## 8. The sequenced plan + go/no-go gates (`docs/DECISION_GATES.md`)

1. **Finish + benchmark.** GATE: offloading A→C cuts TTFT p95 ≥25%; routing D→E gives ≥2×
   cache-hit rate and ≥20% lower TTFT p95. ✅→ Stage 2.
2. **Compare vs real tools.** GATE: InferGate within ~10–20% of Dynamo/Prod-Stack hit rate
   with far less setup. ✅→ Stage 3.
3. **OSS PR.** GATE: a clean, minimal PR opened to vLLM/LMCache.

Decision: **escalate only if numbers justify it** (user chose all 3, sequenced).

---

## 9. Open decisions needed to start the GPU run

1. **Get code onto the pod:** private GitHub repo to `git clone` (recommended) **or** manual
   file upload via RunPod's browser?
2. **Scope of first run:** Phase 1 only (1 GPU, ~$3, proves offloading/AWS theme) **or** full
   A→E sweep (2 GPUs, ~$6–10)?
3. Confirm primary model = **Llava-OneVision-7B** (LMCache-documented; lowest risk), with
   Qwen2.5-VL-7B as an optional stretch.

---

## 10. Repo map (key files)

```
infergate/
├── README.md                      # project overview + quickstart
├── PROJECT_CONTEXT.md             # THIS FILE (handoff brief)
├── pyproject.toml                 # deps & packaging
├── src/infergate/
│   ├── app.py  server.py  cli.py  config.py  models.py  service.py
│   ├── api/        # chat, models, health/metrics, admin endpoints
│   ├── providers/  # mock, openai, openai_compatible (vLLM), anthropic
│   ├── routing/    # keying.py, affinity.py, router.py, strategies.py, state.py  ← the novel part
│   ├── cache/      # exact + semantic response cache (memory/redis)
│   ├── ratelimit/  # token-bucket limiter
│   └── observability/metrics.py
├── dashboard/                     # Next.js + TS + Tailwind live dashboard
├── loadtest/multimodal_bench.py   # the benchmark client
├── scripts/compare_results.py     # turns run JSONs into a comparison table
├── config/                        # example + mock + gpu.yaml configs
├── deploy/                        # Dockerfile bits, prometheus, grafana dashboard
├── tests/                         # 59 tests
└── docs/
    ├── RESEARCH_KV_CACHE.md       # verified 2026 landscape
    ├── KV_AWARE_PLAN.md           # implementation + benchmark plan
    ├── DECISION_GATES.md          # the sequenced gates + résumé bullet template
    ├── HOW_ROUTING_WORKS.md       # mechanism + comparison vs Dynamo/llm-d
    ├── BENCHMARK.md               # GPU benchmark runbook
    └── RUNPOD_GUIDE.md            # beginner click-by-click GPU guide
```

---

## 11. Tech stack (complete)

- **Language/packaging:** Python 3.9+, hatchling, Git, GitHub Actions (CI).
- **Frontend:** Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS (`dashboard/`).
- **Gateway runtime:** FastAPI, Uvicorn, Pydantic v2, httpx, click, PyYAML.
- **Routing internals:** stdlib only — hashlib, collections, time, math, random, asyncio.
- **Storage (optional):** Redis (response cache + rate limit); sentence-transformers (optional
  semantic cache; default is a dependency-free hashing embedder).
- **Observability:** prometheus-client → Prometheus → Grafana.
- **Testing/quality:** pytest, pytest-asyncio, pytest-cov, ruff, mypy, respx, Locust.
- **Ops:** Docker, docker-compose.
- **Benchmark phase (GPU):** vLLM (serving), LMCache (KV offloading), Hugging Face transformers,
  Llava-OneVision-7B (model), RunPod (rented GPUs).

---

## 12. Suggested next discussion topics for Cowork

- Confirm the 3 open decisions in §9 (repo method, run scope, model).
- Sanity-check the gate thresholds in §8 — are they the right bar for a strong résumé claim?
- Plan the write-up/blog + exact résumé bullet once Stage 1 numbers exist.
- Decide if/when to make the GitHub repo public, and the launch (README polish, demo GIF).

*(Development tasks — running benchmarks, code changes, pushing — are executed in Claude Code.)*
