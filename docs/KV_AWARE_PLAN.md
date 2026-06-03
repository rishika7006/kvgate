# InferGate — Multimodal KV/Prefix-Aware Routing: Implementation & Benchmark Plan

**Status:** proposal for review (no code written yet)
**Target model:** `llava-hf/llava-onevision-qwen2-7b-ov-hf` (primary, LMCache-documented) —
`Qwen/Qwen2.5-VL-7B-Instruct` as an optional stretch second model
**Goal:** make InferGate a *lightweight, vendor-neutral, multimodal-aware, KV/prefix-aware
gateway* in front of a fleet of vLLM+LMCache replicas, and produce an honest,
reproducible "with vs without" benchmark on a multimodal model.

> Grounding: see `docs/RESEARCH_KV_CACHE.md`. Key facts: vLLM + **LMCache v0.4.6** is the
> adopted stack; multimodal needs **image-hash-aware** keys; KV-aware routing exists but is
> heavy/K8s-coupled; **all vendor performance numbers were refuted** → we measure our own.

---

## 0. Positioning (why this is not a re-implementation)

| Existing | Limitation | InferGate's angle |
|---|---|---|
| vLLM Production Stack router | K8s-coupled, tied to the full stack | Plain Docker, OpenAI-compatible, drop-in |
| NVIDIA Dynamo / llm-d | Heavy, datacenter/K8s, vendor-aligned | Vendor-neutral, runs on a laptop or 2 GPUs |
| LiteLLM / Portkey / Kong | **KV-blind** (route by cost/load only) | KV/prefix-aware **+ image-hash-aware** routing |
| All of the above | KV-aware routing is **text-prefix** centric | First-class **multimodal** affinity (route by image identity) |

**The one-line novelty:** *the gateway infers KV affinity from the traffic it already sees —
no dependency on the engine publishing KV events — and keys that affinity on image identity,
so the same image+prompt is routed to the replica that already has its (large) vision KV warm.*

---

## 1. Architecture

### 1.1 Where it plugs in

InferGate already maps a **logical model → N deployments**. For KV-aware routing we point
those N deployments at **N replicas of the same vLLM model** (different `base_url`s):

```yaml
models:
  - name: qwen-vl
    deployments:
      - { provider: vllm-r1, model: Qwen/Qwen2.5-VL-7B-Instruct }
      - { provider: vllm-r2, model: Qwen/Qwen2.5-VL-7B-Instruct }
providers:
  - { name: vllm-r1, type: openai_compatible, base_url: http://gpu1:8001/v1 }
  - { name: vllm-r2, type: openai_compatible, base_url: http://gpu2:8001/v1 }
```

The new strategy chooses **which replica** serves each request to maximize that replica's
engine-side prefix-cache hit.

### 1.2 The core idea: a gateway-side prefix-affinity index

For each incoming request we compute a **routing-key chain** and decide which replica has
seen the longest matching prefix recently.

**Step 1 — build the key sequence (multimodal-aware).**
Flatten the prompt into a token-ish sequence; for each image, replace its placeholder span
with a single synthetic marker = `image_hash`. This mirrors LMCache's
`apply_mm_hashes_to_token_ids` so *identical images collapse to identical keys and different
images diverge* — the safety property the research flagged as essential.

```
key_units = [t0, t1, ..., <IMG:sha256(img_bytes)>, ..., tN]
```

- `image_hash` default = `sha256` of the decoded image bytes (handles base64 `data:` URLs);
  for plain URLs, hash the URL string (configurable: `bytes_sha256 | url`).
- Tokenization is **pluggable**: `approx` (whitespace/char blocks, zero-dep, vendor-neutral)
  or `hf` (exact `transformers` tokenizer for the target model). *Routing only needs
  consistency, not byte-identical vLLM block hashes* — so `approx` is the default and `hf`
  is an optional fidelity upgrade.

**Step 2 — block-chunk and chain-hash (vLLM-style).**
Chunk `key_units` into blocks of `block_size` (default 16, matching vLLM) and compute a
cumulative chain hash so a shared prefix yields identical leading block hashes:

```
h_i = sha256(h_{i-1} || block_i)      # h_0 = seed
chain = [h_1, h_2, ..., h_k]
```

**Step 3 — score replicas by longest warm prefix.**
The affinity index stores, per replica, the block hashes it has served recently (with
timestamps). For the request's `chain`:

```
matched_blocks(r) = length of leading run of chain present & unexpired in replica r
score(r) = w_prefix * matched_blocks(r) - w_load * inflight(r)
pick r* = argmax score ; if max matched_blocks == 0 -> cold_fallback (least_busy)
```

**Step 4 — register.** After choosing `r*`, insert all of `chain` into `r*`'s index with
`now` (the engine will now have these blocks warm). Hot prefixes get re-pinned on every use.

**Eviction modeling.** We can't see the engine's real KV eviction, so we approximate it with
a per-replica **TTL + LRU cap** (`affinity_ttl_s`, `max_blocks_per_replica`) tuned to the
replica's KV capacity. This is "best-effort affinity," documented honestly — and it still
works because frequently-used prefixes are continually refreshed.

### 1.3 Cross-gateway scaling

- Single InferGate instance → in-memory index.
- Multiple InferGate instances → shared index in **Redis** (reuse the existing cache backend
  choice): block hashes in a Redis hash/ZSET keyed by replica, with TTL. Mirrors the
  existing `cache.backend: memory|redis` pattern.

### 1.4 Optional "precise mode" (future, not in v1)

Consume vLLM's native KV-cache events (published over ZMQ/NATS, the same stream Dynamo/llm-d
use) to get exact block locations instead of inferring them. **Deferred** — the research could
not confirm the event API is stable across vLLM versions, and the inferred approach needs no
engine cooperation. We'll design the index behind an interface so precise mode is a drop-in
backend later.

### 1.5 New/changed code (for when we build)

```
src/infergate/routing/
  affinity.py        # NEW: PrefixAffinityIndex (memory + redis), block-chain hashing
  keying.py          # NEW: routing-key builder (text + image-hash), approx/hf tokenizer
  strategies.py      # +prefix_kv_aware (request-aware)
  router.py          # pick(model, exclude, request=None) — thread request to strategy
src/infergate/config.py        # +PrefixKvAwareSettings under RoutingSettings
src/infergate/service.py       # pass request into router.pick(...)
src/infergate/observability/metrics.py
                     # +routing_affinity_matched_blocks (histogram),
                     # +routing_affinity_hits_total{outcome=warm|cold}
tests/test_affinity.py, tests/test_prefix_routing.py   # NEW
```

### 1.6 Config additions

```yaml
routing:
  strategy: prefix_kv_aware
  prefix_kv_aware:
    block_size: 16
    affinity_backend: memory      # memory | redis
    affinity_ttl_s: 300
    max_blocks_per_replica: 200000
    weight_prefix: 1.0
    weight_load: 0.5
    tokenizer: approx             # approx | hf
    hf_model: llava-hf/llava-onevision-qwen2-7b-ov-hf
    image_key: bytes_sha256       # bytes_sha256 | url
    cold_fallback: least_busy
```

### 1.7 New metrics (the proof)

- `infergate_routing_affinity_hits_total{outcome="warm|cold"}` — % of requests routed to a
  replica that already had a matching prefix.
- `infergate_routing_affinity_matched_blocks` (histogram) — how much prefix we reused.
- Plus scrape each vLLM's `vllm:prefix_cache_hits_total` / `vllm:prefix_cache_queries_total`
  and `vllm:time_to_first_token_seconds` to correlate gateway routing with *engine* hit rate.

---

## 2. Backend deployment runbook (vLLM + LMCache, Llava-OneVision-7B)

> ✅ **Primary model chosen for de-risking:** `llava-hf/llava-onevision-qwen2-7b-ov-hf` is in
> LMCache's documented multimodal example set (image + video), so the KV-reuse path is proven.
> **Stretch goal:** after clean numbers on Llava-OneVision, *if it verifies at M3*, add
> `Qwen/Qwen2.5-VL-7B-Instruct` as a second column (more recognizable, but not LMCache-documented).
> The routing layer is model-agnostic, so this choice only affects the backend benchmark.

### 2.1 Install (pin versions)

```bash
pip install "vllm==<pin-current>" "lmcache==0.4.6" transformers accelerate
```

### 2.2 LMCache config (`lmcache.yaml`)

```yaml
chunk_size: 256
local_cpu: true
max_local_cpu_size: 30        # GiB of CPU RAM for offloaded KV
# Optional shared store for CROSS-INSTANCE KV (scenario E variant):
# remote_url: "lm://lmcache-server:65432"
# remote_serde: "naive"
```

### 2.3 Launch one replica (per GPU)

```bash
LMCACHE_CONFIG_FILE=./lmcache.yaml \
CUDA_VISIBLE_DEVICES=0 \
vllm serve llava-hf/llava-onevision-qwen2-7b-ov-hf \
  --port 8001 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768 \
  --limit-mm-per-prompt image=4 \
  --kv-transfer-config '{"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'
```

Replica 2: `CUDA_VISIBLE_DEVICES=1 ... --port 8002`.

### 2.4 Scenario toggles

| Scenario | Replicas | vLLM prefix cache | LMCache | InferGate strategy |
|---|---|---|---|---|
| **A** baseline | 1 | `--no-enable-prefix-caching` | off (no kv-transfer-config) | n/a (direct) |
| **B** APC | 1 | on (default) | off | n/a (direct) |
| **C** offload | 1 | on | on (`kv_both`) | n/a (direct) |
| **D** fleet RR | 2 | on | on | `round_robin` |
| **E** fleet KV-aware | 2 | on | on | `prefix_kv_aware` |

**A→C** = single-instance offloading gains. **D→E** = *the headline*: cross-replica KV-aware
routing vs a KV-blind load balancer.

---

## 3. Benchmark methodology

### 3.1 Workload — multimodal multi-turn VQA / image-RAG

Generator (`loadtest/multimodal_bench.py`, to build) produces a **deterministic request
trace** so all 5 scenarios see identical input:

- Pool of **K=50 images** from a public set (e.g. DocVQA / TextVQA / COCO).
- Each image paired with a **long shared system prompt (~1–2k tokens)** → big shared prefix.
- A "session" = one image + **5–8 follow-up turns** (growing prefix → strong intra-session reuse).
- Sessions interleaved; **~70% of sessions revisit a previously-seen image** (inter-session,
  cross-replica reuse opportunity).
- Configurable concurrency sweep (e.g. 1, 4, 16, 32 concurrent).

### 3.2 Metrics

| Metric | Source | Why |
|---|---|---|
| **TTFT** p50/p95/p99 | client (time to first SSE chunk) | headline — prefix caching's main win |
| ITL / TPOT | client | decode speed |
| End-to-end latency | client | user-perceived |
| Throughput (req/s, output tok/s) | client | capacity |
| **Engine prefix-cache hit rate** | vLLM `/metrics` | proves KV reuse happened |
| **Routing-affinity hit rate** | InferGate `/metrics` | proves the *router* sent it to the warm replica |
| GPU KV-cache utilization / headroom | vLLM `/metrics` | offload's memory benefit |
| Cost / 1k requests | derived (GPU $/hr ÷ throughput) | the business case |

### 3.3 Tools

- **Primary:** custom async client (httpx) driving InferGate — only way to capture the
  *routing-affinity* metric and control the reuse pattern. Emits per-request JSON + summary.
- **Cross-check:** `vllm bench serve` (has multimodal support) and/or **GuideLLM** for
  standard throughput/latency sweeps against a single replica (validates our client's numbers).
- Dashboards: extend the existing Grafana board with a "KV-aware routing" row.

### 3.4 Hardware & cost

- **2× 24 GB GPUs** (L4 or A10G) on RunPod/Lambda — Llava-OneVision-7B (bf16 ≈ 15 GB) fits with
  KV headroom; two replicas prove cross-replica routing.
- Est. cost: ~$0.8–1.2/GPU/hr → ~**$1.6–2.4/hr**; a full 5-scenario sweep w/ warmups ≈ 3–4 hrs
  → **~$6–10 total**. (Use L40S 48 GB if you want longer context / bigger batch.)

### 3.5 Results template

```
Single-replica (A→C), 50 images, 8 turns, conc=16:
  Scenario        TTFT p50  TTFT p95  Tok/s   PrefixHit%  KV-mem peak
  A no-cache       ____      ____      ____      0%          ____
  B vLLM APC       ____      ____      ____      __%         ____
  C +LMCache       ____      ____      ____      __%         ____   (offload headroom)

Fleet (D→E), 2 replicas, conc=32, 70% image revisit:
  Scenario              TTFT p50  TTFT p95  Tok/s   AffinityHit%  EnginePrefixHit%
  D round-robin (blind)  ____      ____      ____       ~50%          __%
  E prefix_kv_aware      ____      ____      ____       __%           __%   ← headline
```

---

## 4. Milestones

1. **M1 — Routing core (no GPU):** `keying.py` + `affinity.py` + `prefix_kv_aware` strategy +
   request-aware `router.pick` + config + metrics + unit tests. Demonstrable on the mock
   provider (route same prefix to same mock replica). *Largest code chunk.*
2. **M2 — Benchmark harness (no GPU):** `multimodal_bench.py` trace generator + metrics
   collector + results writer; dry-run against mock replicas.
3. **M3 — Backend bring-up (GPU):** stand up 2× vLLM+LMCache Qwen2.5-VL replicas; verify
   multimodal KV reuse works (or fall back model). Smoke test through InferGate.
4. **M4 — Run sweep + write-up (GPU):** run A–E, collect metrics, fill tables, Grafana
   screenshots, short report + blog draft. Update resume bullets with *measured* numbers.

---

## 5. Risks & verify-before-you-run checklist

- [x] **Model choice (decided):** primary = `llava-hf/llava-onevision-qwen2-7b-ov-hf`
      (LMCache-documented → proven KV-reuse path). Stretch = `Qwen/Qwen2.5-VL-7B-Instruct`,
      added only if it verifies at M3. Still confirm multimodal KV reuse actually *fires* on
      the primary before the full sweep (quick warm-vs-cold sanity check).
- [ ] **vLLM flags**: confirm `--no-enable-prefix-caching` and the `--kv-transfer-config` JSON
      shape against the installed vLLM version (flag names drift).
- [ ] **Version pins**: LMCache `0.4.6` (0.4.7 in nightly) + a matching vLLM release; pin both.
- [ ] **`approx` vs `hf` keying**: start with `approx`; if affinity hit-rate looks weak, switch
      to `hf` for tokenizer-faithful blocks.
- [ ] **Honesty**: report *our measured* numbers only. Do **not** cite the refuted vendor figures
      (LMCache 3–10×, Mooncake 46×, VLCache 16.95×).
- [ ] **GPU budget**: set a spend cap; tear down replicas after the sweep.

---

## 6. Resume / blog framing (after M4)

> *Extended an open-source LLM gateway with multimodal KV/prefix-aware routing: a gateway-side
> affinity index keyed on prompt prefix + image identity routes requests to the vLLM+LMCache
> replica holding the warm KV, raising engine prefix-cache hit rate from **[X%]** to **[Y%]**
> and cutting multimodal TTFT p95 by **[Z%]** vs a KV-blind load balancer (Llava-OneVision-7B, 2×L4).*

Fill brackets from M4. This ties directly to your AWS LMCache KV-transfer work — the gateway
is the fleet-level generalization of the single-deployment reuse you built there.
