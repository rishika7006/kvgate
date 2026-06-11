# KVGate — Master Plan & Pending Checklist

> The single source of truth for scope & progress. We tick these off one-by-one.
> Pairs with `HANDOFF.md` (resume context) and `docs/` (detail). Last reviewed against
> the original goals, `docs/KV_AWARE_PLAN.md`, `docs/DECISION_GATES.md`, and the README roadmap.

Legend: ✅ done · �︎ in progress · ⬜ pending · ⭐ current focus

---

## Status snapshot (updated 2026-06-10, late)
**Project renamed InferGate → KVGate** (InferGate collided with a PyPI package, useinfergate.com,
an exact-name GitHub repo, and the near-homophone InferXgate). Repo: github.com/rishika7006/kvgate.

**Done + pushed (CI green):**
- All 3 GPU experiments captured (real numbers): B2 routing (1.84× p95), LMCache CPU offload
  (up to 2×; the 3-tier run shows 5.6× under pressure), KV-offload hierarchy CPU vs Redis
  (direct memory proof: CPU RAM +35 GB, Redis +4.7 GB).
- Dashboard rebuilt as recruiter-facing **Results showcase + Live tab**, professional polish
  (logo, no emojis/em-dashes, contact header+footer, fixed charts), static-export (Vercel-ready).
- **D1** Redis distributed routing (+tests). **D4** per-tenant spend caps (+tests, config, metrics).
- **Tier-1 pre-deploy items DONE:** gateway-overhead benchmark (~1 ms p50, negligible vs
  inference), README "How KVGate compares" table, spend caps.
- README/report/RESULTS/HANDOFF all updated; F1/F2/F3 done; 71 tests + mypy + ruff green.

**Blocked on user / gated:** Vercel deploy (connect repo, root dir `dashboard`) · F4 go public ·
G1/G2 LinkedIn post + résumé (LAST).
**Deferred (post-launch, see Future Scope below):** B4 docker+Grafana shot · C1 vs Dynamo ·
C2 OSS PR · D2/D3/D5 · E-series · frontend v2 redesign.

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

## Note for routing GPU runs — the orchestration fixes (learned the hard way)
- RunPod's **nginx squats on port 8001** → vLLM can't bind, traffic collapses to one replica.
  Use high ports (19001/19002/19080). Smoke-test each replica with a real chat request before benchmarking.
- Long SSH sessions drop (exit 255); `nohup`/`setsid`-detach + write outputs to **`/root/igout`**
  (NOT `/tmp` or `/workspace` — both misbehaved for detached writes). Poll with SHORT ssh.
- Kill ALL leftover driver scripts before relaunching (zombie old scripts overwrite logs).
- `nvidia-smi` reports 0 MiB in-container — trust `/health` endpoints, not GPU readouts.
- SSH key onboarding: paste pubkey into the **pod's** `~/.ssh/authorized_keys` via the web/Jupyter
  terminal (RunPod doesn't inject keys into an already-running pod).
- Pinned env: `vllm==0.11.0 torch==2.8.0 transformers==4.57.6 mistral_common==1.8.2 hf_transfer`,
  `lmcache==0.3.7`; model `llava-hf/llava-onevision-qwen2-7b-ov-hf`. Single A40 (~$0.44/hr) is enough.

---

## Competitive landscape & differentiation (researched 2026-06-10)
"LLM gateway" splits into two crowded camps; **KVGate is neither**:
- **Provider-aggregation proxies** (LiteLLM, InferXgate/inferxgate.com, useinfergate.com, the
  `infergate` PyPI lib): one API in front of many hosted providers, **response** caching, cost
  routing. Commoditized.
- **vLLM scheduling sidecars** (e.g. GaussGeorge/InferGate): admission control / scheduling.

**KVGate's moat = the KV-cache layer:** prefix/KV-aware routing to the warm replica (incl.
per-image hash) + LMCache KV offload (CPU/Redis), with **measured GPU benchmarks** on a
multimodal model. Rule for any new feature: does it **deepen the KV-cache story** (do it) or
**chase provider-proxy parity** (skip)?

## Future scope — tiered (so we can resume anytime)
**Tier 1 — pre-deploy, no GPU — ✅ DONE:** gateway-overhead benchmark · README vs-alternatives
table · per-tenant spend caps (D4).

**Tier 2 — strong, post-launch (deepen the moat):**
- **C1** Benchmark KVGate routing vs **NVIDIA Dynamo / vLLM Production Stack** (~1 day, GPU).
  The serious comparison; high résumé value.
- **D5** "Precise mode" routing from real vLLM **KV-cache events** (ZMQ/NATS) vs inferred (~1–2 days).
- **D3** Streaming failover mid-response (~half day). · **D2** Redis-backed semantic cache index.

**Tier 3 — lower ROI for job search (much later / optional):** E1 K8s/Helm · E2 OpenTelemetry ·
E4 security review · E5 ≥90% coverage + integration test · E6 one-command benchmark automation ·
C2 OSS PR to vLLM/LMCache · PyPI publish · mkdocs site · demo GIF/Colab.

## Frontend v2 redesign plan (inspired by inferxgate.com — do AFTER current improvements)
User likes inferxgate.com's layout: strong **top hero panel** and **bottom panel**, and the
**top tabs**. Plan when we do frontend v2:
- Keep the bold top hero (headline + key stats) and add a strong closing/CTA bottom panel
  (contact + "open to collaboration" + links), styled like inferxgate's bookends.
- Reconsider tabs: currently Results / Live demo. Candidate tabs to consider: **Results**,
  **Live demo**, **Architecture**, **How it works / Docs**. Decide which earn a tab vs stay inline.
- Tighten spacing/typography to match that polished SaaS feel; keep it honest (no fake metrics).

## Pending reminders (user-captured, do after the improvements)
1. **Live demo tab needs an intro.** At the top of the Live tab, explain in plain language what
   it is, who it's for, how to use it, and what the metrics tell you. Right now it's vague and
   doesn't convey its purpose. (Add a short "What is this?" header + 1–2 sentence guide.)
2. **GitHub changes** (user will specify the full list). Likely includes: repo description +
   topics/tags, README emoji/header cleanup for consistency, social-preview image, pin/links,
   release/tag, and anything else for a polished public repo. Capture the user's list when given.

## Definition of "ready to deploy + go public"
Dashboard polished ✅ · rename done ✅ · Tier-1 done ✅ · CI green ✅ · then: Vercel deploy →
README live-demo link → make repo public (F4) → LinkedIn post + résumé (G1/G2, LAST).
