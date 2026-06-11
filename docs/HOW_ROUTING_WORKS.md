# How KVGate's KV/prefix-aware routing works

> Plain-language explanation of the `prefix_kv_aware` strategy: what it does, how
> it decides, what it does **not** know, and how it compares to the existing
> heavyweight systems (vLLM Production Stack, NVIDIA Dynamo, llm-d).

## The problem

When an LLM server (vLLM) processes a prompt, it builds a **KV cache** — the
model's working memory for that prompt. If a later request shares the same
*prefix* (e.g. the same long system prompt, or the same image), the server can
reuse that cached work instead of recomputing it — much lower time-to-first-token.

vLLM does this reuse **within a single server**. But production runs *many*
replicas behind a load balancer. A normal load balancer is **KV-blind**: it might
send a request to a replica that never saw that prefix, wasting the cache another
replica already holds. The job of KV-aware routing is to send each request to the
replica most likely to have its prefix **warm**.

## How KVGate decides (the mechanism)

**Key honesty: KVGate does not *know* each replica's true cache state. It
*predicts* it from the traffic it has routed.** It keeps its own "notebook" and
bets that a replica it recently sent a prefix to still has it warm.

```
Request ─▶ 1. fingerprint ─▶ 2. score replicas ─▶ 3. pick ─▶ 4. record ─▶ upstream
              the prompt        by longest warm        best        the choice
              (+ image hash)    matching prefix      (load-guarded)
```

1. **Fingerprint the request** (`routing/keying.py`)
   Chop the prompt into ~16-token blocks; compute a *running* hash per block so a
   shared prefix yields identical leading hashes. **Each image is replaced by a hash
   of the image itself** — so the same text with a different image diverges, and the
   same image collapses to the same key. Result: a chain `[h1, h2, h3, …]`.

2. **Score each replica by longest warm prefix** (`routing/affinity.py` + `router.py`)
   A per-replica table records which block hashes it has served recently (with
   timestamps). For the new request, count how many *leading* hashes each replica
   already has. Score = `weight_prefix × matched_blocks − weight_load × in_flight`.

3. **Pick — with a load guard** (`router.py`)
   Choose the highest-scoring replica, but only among replicas that aren't
   overloaded relative to the least-busy one (`max_inflight_skew`). This stops a
   universal prefix (e.g. a shared system prompt) from snowballing all traffic onto
   one replica. If nothing matches, fall back to least-busy.

4. **Record the choice**
   Register the request's hashes against the chosen replica (it's about to warm
   them). Entries expire via TTL + LRU, approximating the engine's real eviction.

**Tools used:** all standard-library Python — `hashlib` (hashing), `collections`
(`OrderedDict`/`defaultdict` for the table + LRU), `time` (TTL). No external
dependency, no GPU, no cooperation from the inference engine.

## What it does NOT know (the honest caveat)

KVGate's routing is a **best-effort prediction**, not ground truth. Its bet can
be wrong if a replica evicted the cache under memory pressure, restarted, or
received traffic from outside the gateway. Two things keep it honest:

- **`affinity hit rate`** (KVGate metric) — how often the notebook *believed* it
  found a warm replica.
- **`prefix_cache_hits`** (vLLM's own metric) — whether the bet *actually* landed on
  real cached memory. The GPU benchmark cross-checks these: a high affinity hit rate
  is only meaningful if vLLM's real prefix-cache-hit rate rises with it.

### A more precise mode we deliberately deferred

vLLM can *publish* KV-cache events (exactly what it holds). A gateway could consume
those for ground truth instead of inferring. KVGate keeps the inference-based
approach as the default because it needs **zero engine cooperation** and works with
heterogeneous backends; consuming real KV events is a planned "precise mode" behind
the same interface.

## How this compares to what already exists

KV/prefix-aware routing is **not a new invention** — it ships in three serious
systems as of 2025–2026:

| System | What it does | Trade-offs |
|---|---|---|
| **vLLM Production Stack** router | Prefix-aware + KV-aware routing; uses LMCache for cross-replica KV sharing | Tied to the vLLM Production Stack; Kubernetes-oriented |
| **NVIDIA Dynamo** | KV-cache-aware routing via engine **KV events** (NATS/ZMQ) | Heavy datacenter platform; Kubernetes |
| **llm-d** (Red Hat/IBM) | Precise prefix-cache-aware routing | Kubernetes-native |

**What KVGate contributes (the honest differentiators):**

1. **Lightweight & vendor-neutral** — a plain Docker, OpenAI-compatible gateway;
   no Kubernetes, no platform lock-in. Runs on a laptop or two GPUs.
2. **No engine cooperation required** — infers affinity from traffic, so it works in
   front of heterogeneous / unmodified backends.
3. **Multimodal-aware routing keys** — routing keyed on **image identity**, an
   under-explored angle at the cross-replica routing layer.
4. **A reproducible, honest multimodal benchmark** — none exists publicly; we ship one.

**How to describe it accurately (e.g. in interviews):**

> "KV-aware routing exists in heavyweight platforms like Dynamo and llm-d, but
> they're Kubernetes-bound and rely on engine cooperation. I built a lightweight,
> vendor-neutral, **multimodal-aware** gateway that infers cache affinity purely from
> traffic — no engine changes — and benchmarked it on vision-language models, since
> no honest public benchmark existed."

This is truthful and strong: it shows command of the state of the art, a real gap
(lightweight + multimodal + no-cooperation), and rigorous measurement — far better
than claiming to have invented the technique.
