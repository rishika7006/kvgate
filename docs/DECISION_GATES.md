# Decision gates — the sequenced "prove it, then escalate" plan

We escalate ambition only when the numbers justify it. Three stages, each with an
explicit go/no-go gate, so we never sink GPU time or effort into a path the data
doesn't support.

## Stage 1 — Finish InferGate + benchmark it (own the result)

**Do:** Run the A→E sweep on real GPUs (`docs/RUNPOD_GUIDE.md`), Llava-OneVision-7B.

**GATE 1 — proceed only if BOTH hold (measured, not assumed):**
- **Offloading works (A→C):** scenario C (vLLM + LMCache) shows materially lower
  TTFT p95 than A (no cache) on the repeated-prefix workload — target **≥ 25% lower**,
  and vLLM's `prefix_cache_hits` clearly rises.
- **Smart routing works (D→E):** `prefix_kv_aware` (E) beats round-robin (D) on
  **engine prefix-cache hit rate** (target **≥ 2×** D's rate) and on **TTFT p95**
  (target **≥ 20% lower**), while keeping replicas reasonably balanced.

✅ Pass → Stage 2.  ❌ Fail → we tune (block size, skew, TTL, workload) and re-measure
before escalating; the project still stands on the offloading result + the honest
"here's what didn't move and why" analysis.

## Stage 2 — Benchmark against the real tools (context for the result)

**Do:** Stand up the **vLLM Production Stack router** (and/or **NVIDIA Dynamo**) on the
same fleet/workload, as comparison baselines.

**GATE 2 — the claim we want to be able to make truthfully:**
- InferGate lands **within ~10–20%** of the Production-Stack/Dynamo router's
  prefix-cache hit rate **with far less setup** (no Kubernetes, no engine changes).

✅ Pass → we have the headline: *"a lightweight, vendor-neutral, multimodal gateway
that gets within X% of the heavyweight systems."* Proceed to Stage 3.
⚠️ If InferGate is notably worse → that's still a publishable, honest finding
("inference-based routing trades Y accuracy for Z simplicity"), and points us at the
"precise mode" (consume real KV events) as future work.

## Stage 3 — Open-source contribution (external validation)

**Do:** While deep in vLLM/LMCache for Stages 1–2, find one **small, real** improvement
and submit a PR — a doc fix, a multimodal example, a small bug, a benchmark-script
nit. (Scope kept tiny on purpose; maintainer review timing is out of our control.)

**GATE 3:** a PR opened with a clean, minimal, tested change. A merge is a bonus;
"opened a well-scoped PR to vLLM/LMCache" is already strong résumé signal.

## Why this order
Each stage de-risks the next: Stage 1 proves the idea is worth comparing; Stage 2
proves the comparison is worth publishing; Stage 3 converts the work into external
credibility. We stop or pivot at any failed gate instead of forcing it.

## Résumé bullet (fill brackets after Stage 1, strengthen after Stage 2)
> Built **InferGate**, an open-source OpenAI-compatible LLM gateway with multimodal
> KV/prefix-aware routing; on a 2×GPU Llava-OneVision-7B fleet it raised engine
> prefix-cache hit rate from **[D%]→[E%]** and cut TTFT p95 by **[Z%]** vs a KV-blind
> load balancer — within **[N%]** of NVIDIA Dynamo's router with no Kubernetes or
> engine modification.
