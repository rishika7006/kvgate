# Contributing to KVGate

Thanks for your interest in improving KVGate! Contributions of all kinds are
welcome — bug reports, docs, new providers, routing strategies, and tests.

## Development setup

```bash
git clone https://github.com/rishika7006/kvgate.git
cd kvgate
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,redis]"
```

## Before opening a PR

```bash
make lint        # ruff check
make typecheck   # mypy src
make test        # pytest (keep or improve coverage)
make fmt         # ruff format
```

All of the above run in CI across Python 3.9 / 3.11 / 3.12, plus a Docker build
and container smoke test.

## Project layout

```
src/kvgate/
  config.py        # YAML config models + env expansion
  models.py        # OpenAI-compatible request/response schemas
  service.py       # request orchestration (cache → route → failover → metrics)
  app.py           # FastAPI factory + lifespan
  providers/       # mock, openai, openai_compatible (vLLM), anthropic
  routing/         # strategies, per-deployment state, circuit breaker
  cache/           # exact + semantic cache, embedders, memory/redis stores
  ratelimit/       # token-bucket limiter (memory/redis)
  observability/   # Prometheus metrics
  api/             # chat, models, health/metrics, admin routes
```

## Adding a provider

1. Subclass `providers.base.Provider` and implement `complete()` + `stream()`.
2. Map upstream errors to `ProviderError` with the right `retryable` flag — this
   is what drives router failover.
3. Register it in `providers/__init__.py._REGISTRY`.
4. Add a test (mock the HTTP layer with `respx`).

## Adding a routing strategy

Add a pure function to `routing/strategies.py`, register it in `STRATEGIES`, and
allow it in the `RoutingSettings.strategy` `Literal` in `config.py`.

## Code style

- Type hints everywhere; `from __future__ import annotations` at the top.
- Keep modules focused and small; prefer composition over inheritance.
- Public behavior change ⇒ a test that covers it.

By contributing you agree your contributions are licensed under Apache 2.0.
