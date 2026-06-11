# KVGate — resume & interview notes

Ready-to-adapt material for putting this project on your resume and talking about
it in interviews. Replace the bracketed numbers with real figures from your own
load-test run (`make loadtest` → read p99 / cache-hit-rate off Grafana).

## Resume bullets (metric-driven, same style as strong SWE bullets)

> **KVGate — OpenAI-compatible LLM inference gateway** · *Python, FastAPI, Redis, Prometheus/Grafana, Docker*
> - Built an open-source LLM inference gateway that fronts vLLM and hosted APIs behind one OpenAI-compatible endpoint, with latency-, cost-, and load-aware routing across heterogeneous backends and automatic failover + circuit breaking.
> - Designed an exact + semantic response cache with a Redis backend for cross-replica reuse, cutting redundant upstream calls by **[~60%]** on repeated/similar prompts and reducing p99 latency by **[~Nx]** under load.
> - Implemented per-tenant token-bucket rate limiting (Redis-distributed), streaming (SSE), and Prometheus metrics + a Grafana dashboard tracking tokens/sec, cache-hit rate, cost, and per-deployment latency.
> - Shipped as an installable package with **[85%]** test coverage, CI across Python 3.9–3.12, a Docker Compose stack, and a Locust load-test harness.

## Why it maps to your AWS internship

This project is the productized version of your AWS work (KV-cache transfer/reuse,
Redis cross-host cache, load testing vLLM under GPU pressure). In interviews,
connect them explicitly:
- *"At AWS I built the GPU-to-CPU KV-cache reuse layer for one vLLM deployment;
  KVGate generalizes that idea to a multi-backend gateway with response-level
  caching and cross-replica reuse via Redis."*

## System-design talking points

- **Routing:** strategies are pure functions over per-deployment state (EWMA
  latency, in-flight count, cost); the router stays backend-agnostic.
- **Resilience:** retryable upstream errors trigger failover to the next-best
  deployment; consecutive failures open a per-deployment circuit breaker with a
  cooldown, with a trial request allowed when all are ejected.
- **Caching:** exact match (canonical request hash) → semantic match (cosine
  similarity over embeddings). Redis backend makes exact hits replica-safe.
- **Observability:** every decision is a metric — you can answer "which backend
  served this, how long did it take, did it hit cache, what did it cost?"

## Good follow-up questions to anticipate

- How would you make the semantic index replica-safe? (Redis vector search / a
  vector DB instead of the in-process index — it's on the roadmap.)
- How do you cache streaming responses? (Reconstruct the full content, store it,
  and re-stream from cache on a later hit.)
- How would prefix-aware routing increase vLLM KV-cache hit rate? (Route requests
  sharing a long system prompt to the same replica.)
