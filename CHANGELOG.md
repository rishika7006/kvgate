# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-06

Initial release.

### Added
- OpenAI-compatible `POST /v1/chat/completions` (streaming + blocking) and `/v1/models`.
- Provider abstraction with `mock`, `openai`, `openai_compatible` (vLLM/TGI), and
  `anthropic` backends.
- Routing strategies: `round_robin`, `weighted`, `latency` (EWMA), `least_busy`, `cost`.
- Automatic failover on retryable upstream errors + per-deployment circuit breaker.
- Exact + semantic response caching with `memory` and `redis` backends; pluggable
  embedders (`hashing` zero-dep default, `sentence_transformers`).
- Token-bucket rate limiting per API key / tenant (`memory` and distributed `redis`).
- Prometheus metrics at `/metrics`, `/admin/stats` live routing introspection, and a
  pre-built Grafana dashboard.
- API-key auth with per-tenant resolution and per-key rate-limit overrides.
- `kvgate` CLI (`run`, `validate`), Docker image, docker-compose stack
  (gateway + Redis + Prometheus + Grafana), and a Locust load-test harness.
- Test suite (pytest), CI across Python 3.9/3.11/3.12 plus Docker smoke test.
