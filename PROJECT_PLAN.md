# KVGate — Master Plan & Pending Checklist

> The single source of truth for scope & progress. We tick these off one-by-one.
> Pairs with `HANDOFF.md` (resume context) and `docs/` (detail). Last reviewed against
> the original goals, `docs/KV_AWARE_PLAN.md`, `docs/DECISION_GATES.md`, and the README roadmap.

Legend: ✅ done · �︎ in progress · ⬜ pending · ⭐ current focus

---

## Status snapshot (2026-06-10)
**Done + pushed (CI green):** B2 routing GPU win · B3 dashboard · B5 report+charts ·
**dashboard rebuilt as Results showcase + Live tab** · README leads with results ·
Vercel static-export + deploy docs · **D1 Redis distributed routing** (+tests) ·
F1 README · F2 OSS templates · F3 CI green · repo URLs fixed to rishika7006.
**Blocked on user:** CPU-offload proof GPU run (needs pod SSH) · Vercel deploy (connect repo) ·
F4 go public (gate) · G1/G2 post+résumé (LAST).
**Optional/deferred:** B4 docker+Grafana shot · C1 vs Dynamo · C2 OSS PR · D2–D5 · E-series.

---

## A. Core build (original scope) — DONE
- ✅ A1. Core OpenAI-compatible gateway (FastAPI): `/v1/chat/completions` (stream+block), `/v1/models`, health, `/metrics`, `/admin/stats`
- ✅ A2. Providers: mock, openai, openai_compatible (vLLM), anthropic
- ✅ A3. Response cache (exact + semantic), in-memory + Redis backends
- ✅ A4. Rate limiting (token bucket), failover + circuit breaker
- ✅ A5. Observability: Prometheus metrics + Grafana dashboard JSON
- ✅ A6. Multimodal **KV/prefix-aware routing** (`prefix_kv_aware`) — keying, affinity index, router
- ✅ A7. Load guard (anti-snowball)
- ✅ A8. Benchmark harness (`loadtest/multimodal_bench.py`) + real-image support
- ✅ A9. **Next.js dashboard** (builds + serves)
- ✅ A10. Packaging, Docker/compose, GitHub Actions CI, 59 tests, ruff/mypy
- ✅ A11. Research + planning docs

## B. Experiments / results
- ✅ B1. LMCache **multimodal** offload GPU win (A40): ~2× TTFT, +65% throughput under memory pressure (`results/`, `RESULTS.md`)
- ✅ B2. **Smart routing GPU benchmark (D round-robin vs E prefix_kv_aware)** on 2× A40 (one replica/GPU): **TTFT p95 2783 → 1516 ms (1.84×, −45%)**, throughput +14%, **98.6% affinity**, load balanced 73/71. Raw in `results/routing/`. *(root cause of earlier failures: RunPod's nginx squats on port 8001 → vLLM couldn't bind → traffic collapsed to one replica. Fixed by using ports 19001/19002/19080 + per-replica smoke test + self-daemonizing launcher writing to `/root/igout`.)*
- ⬜ B3. Verify Next.js dashboard live against a running gateway w/ traffic → screenshot/GIF for README
- ⬜ B4. Verify full `docker compose` stack (gateway+Redis+Prometheus+Grafana) → Grafana shows live KVGate panels → screenshot
- ⬜ B5. Benchmark report doc with tables, methodology, honest caveats, and charts (matplotlib) generated from `results/`

## C. Planned escalation (from DECISION_GATES.md)
- ⬜ C1. **Stage 2:** Benchmark KVGate routing vs **vLLM Production Stack router** and/or **NVIDIA Dynamo** (the "within X% of Dynamo, far less setup" claim)
- ⬜ C2. **Stage 3:** Land a small **OSS PR** to vLLM or LMCache (doc/example/small fix) while we're in their code

## D. Roadmap features (engineering depth — README roadmap)
- ⬜ D1. **Redis-backed prefix-affinity index** (cross-gateway-replica routing) + tests *(today only in-memory)*
- ⬜ D2. **Redis-backed semantic-cache index** (cross-replica) + tests
- ⬜ D3. **Streaming failover mid-response** (today failover only before first token)
- ⬜ D4. **Per-tenant budgets / spend caps**
- ⬜ D5. **"Precise mode" routing:** consume vLLM KV-cache events (ZMQ/NATS) for ground-truth routing (vs inference)

## E. Production hardening / scope-of-improvement
- ⬜ E1. **Kubernetes / Helm** deploy manifests (counters "lightweight-only"; shows K8s skill)
- ⬜ E2. **OpenTelemetry tracing** + structured request logging
- ⬜ E3. Richer **Grafana** panels + Prometheus alert rules
- ⬜ E4. **Security review** pass (API-key auth, per-tenant limits, input validation)
- ⬜ E5. **Test coverage → ≥90%** (Redis paths, streaming, anthropic, admin) + a docker-compose integration test
- ⬜ E6. **Benchmark automation:** one-command sweep + auto-generated comparison report
- ⬜ E7. **Publish to PyPI** (`pip install kvgate`) *(optional)*
- ⬜ E8. **mkdocs documentation site** *(optional)*
- ⬜ E9. Demo asset: asciinema/GIF + a quickstart notebook/Colab

## F. Open-source launch
- ⬜ F1. README polish (badges, architecture image, demo GIF, results table)
- ⬜ F2. CONTRIBUTING (have) + issue/PR templates + CODE_OF_CONDUCT
- ⬜ F3. Verify GitHub Actions CI is green on the repo
- ⬜ F4. **Make the GitHub repo public**

## G. FINAL (only after everything above)
- ⬜ G1. **LinkedIn post** (real numbers, honest framing)
- ⬜ G2. **Résumé bullets** update

---

## Execution order (one-by-one)
1. ~~B2 routing GPU~~ ✅ → 2. **B3 + B4 (dashboard/Grafana live + screenshots)** ⭐ → 3. B5 report →
4. D1–D5 features → 5. C1 (vs Dynamo/Prod-Stack) → 6. C2 (OSS PR) → 7. E1–E9 hardening →
8. F1–F4 launch → 9. **G1–G2 (post + résumé) LAST.**

## Note for B2 (routing GPU) — the orchestration fix
The RunPod flakiness was: long SSH sessions drop; `nohup`-detached procs die; `/tmp` (incl.
tmux socket) is unstable; `nvidia-smi` blind in-container. **Fix:** run inside tmux with
`TMUX_TMPDIR=/workspace` (persistent volume, stable) and write all outputs/logs to
`/workspace`, then poll with SHORT ssh connections; trust `/health` endpoints not `nvidia-smi`.
Use a higher-availability GPU (2× A6000 "7 max", or 2× A100/H100) so we don't get reclaimed.
