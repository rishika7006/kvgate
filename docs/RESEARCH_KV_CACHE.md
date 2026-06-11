# Research: KV-cache offloading, reuse & routing for (multimodal) LLM serving — mid-2026

> Synthesized from a multi-source, adversarially-verified research pass (24 sources,
> 117 claims extracted, 25 verified). **Confidence labels are from 3-vote verification.**
> Performance numbers from vendors were mostly *refuted* — see "Numbers to distrust".

## TL;DR

- **Engine:** vLLM is the de-facto open serving engine. Multimodal automatic prefix
  caching is built in and default-on in vLLM V1 (PR #11187, Dec 2024).
- **KV layer:** **LMCache** (stable **v0.4.6**, 2026-05-29) is the most-adopted
  cross-instance KV offload/reuse library. It reuses KV for *any repeated text, not
  just prefixes* (CacheBlend), offloads tiered to CPU/Disk/NIXL/object storage, does
  P2P + cross-instance sharing, and integrates with vLLM V1 (`LMCacheConnectorV1`),
  the **vLLM Production Stack**, and **NVIDIA Dynamo 1.0**. In production at Google
  Cloud (GKE) and CoreWeave. *(high confidence)*
- **Multimodal:** naive prefix matching is **unsafe** (same text + different image
  would wrongly reuse image KV). Both vLLM-native APC and LMCache (**v0.3.1, PR #882**,
  Jun 2025) fix this by folding a per-image hash (`mm_hash`) into the block/token hash.
  LMCache documents audio / single-image / multi-image / video examples. *(high)*
- **KV-aware routing already exists** in the vLLM Production Stack router, NVIDIA Dynamo
  (event-driven via NATS/JetStream/ZMQ), and llm-d (Kubernetes). *(high)*
- **The gap KVGate fills:** a **vendor-neutral, multimodal-aware, KV/prefix-aware
  gateway** that does *not* require Kubernetes or buying into a full stack — plus an
  honest, reproducible multimodal benchmark, which currently does not exist publicly.

## Tool landscape (verified)

| Tool | What it is | KV reuse scope | Cross-instance | Multimodal | Notes |
|---|---|---|---|---|---|
| **vLLM APC** | Native automatic prefix caching | Prefix only, single instance | No | ✅ image-hash aware (default-on V1) | Baseline; free |
| **LMCache** v0.4.6 | KV offload + reuse layer for vLLM | **Any repeated text** (CacheBlend) | ✅ P2P + shared store | ✅ `mm_hash` (v0.3.1+) | Most adopted; GKE/CoreWeave prod |
| **vLLM Production Stack** | Router + LMCache + K8s | via LMCache | ✅ cache-server pod | inherits vLLM/LMCache | Router modes: round-robin, session, prefix-aware, KV-aware, disagg |
| **NVIDIA Dynamo 1.0** | Datacenter inference platform | engine + router + NIXL storage | ✅ event-driven | inherits engine | Heavy; K8s; KV events over NATS/ZMQ |
| **llm-d** | K8s-native disaggregated inference | precise prefix-cache-aware routing | ✅ | inherits engine | Red Hat/IBM; Kubernetes |
| **Mooncake Store** | Distributed KV pool | shared pool | ✅ larger aggregate capacity | inherits engine | Behind Moonshot Kimi; official vLLM connector |
| **VLCache** (research) | Vision-token selective recompute (2-5%) | vision-token reuse | n/a | ✅ (Qwen2.5-VL, SGLang) | arXiv 2512.12977, Dec 2025; single preprint, perf overstated |

## Multimodal specifics (verified)

- Problem: image/video tokens expand to thousands of KV entries; recomputing them on
  every request dominates TTFT. But you can only reuse them if **both** the text *and*
  the exact image match.
- vLLM solution: an "extra hashes" component encodes the image processor's per-image
  hash into the block hash, so different images → different block hashes.
- LMCache solution: each image gets a 16-byte `mm_hash`; `apply_mm_hashes_to_token_ids()`
  overwrites dummy vision-token IDs so identical images map to identical token sequences;
  works in storage + P2P modes. Config:
  `--kv-transfer-config '{"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'`.
- Documented models: Ultravox (audio), Llava-1.5-7b (image), Phi-3.5-vision (multi-image),
  Llava-OneVision-Qwen2-7b (video). **Not** a blanket "all multimodal models" guarantee.

## KV-aware routing (verified)

- vLLM Production Stack router "detects that the second request shares a prefix with the
  first and routes it to the same instance," routing by "where the KV cache of the
  longest prefix match is found" (round-robin fallback).
- Dynamo: workers publish KV cache events; router weighs prefill cost (KV overlap) vs
  decode cost.
- These are powerful but **coupled to their stacks and mostly Kubernetes-centric**.
  General gateways (LiteLLM/Portkey/Kong) are **KV-blind** — they route by load/cost only.

## Numbers to distrust (REFUTED in verification — re-measure, don't cite)

- LMCache "3–10× latency/TTFT" (1-2) ❌
- Mooncake "3.8× throughput / 46× P50 TTFT / 92% hit rate / 60-GPU linear scaling" (1-2) ❌
- VLCache "16.95× TTFT speedup" and "position-independent cross-context reuse" (0-3) ❌
- LMCache multimodal "~18s → ~1s cold/warm" demo (1-2) ❌

> Implication: **there is no trustworthy public multimodal KV-cache benchmark.** Producing
> one (reproducible, scripted, honest) is a genuine contribution and a strong portfolio artifact.

## Open questions the research could NOT fully resolve

1. Exact/stable vLLM **KV-event API** an external gateway can consume directly (vs depending
   on Dynamo/Production-Stack). Needs hands-on validation against the installed vLLM version.
2. Head-to-head **SGLang RadixAttention / llm-d vs LMCache** for multimodal — not directly compared.
3. Concrete, defensible **benchmark methodology** for multimodal — design it ourselves (below).

## Sources (primary)

- LMCache: https://github.com/LMCache/LMCache · releases API · blog.lmcache.ai
- CacheBlend (non-prefix reuse): https://arxiv.org/abs/2405.16444 (EuroSys'25)
- LMCache enterprise paper: https://arxiv.org/abs/2510.09665
- vLLM prefix caching design: https://docs.vllm.ai/en/stable/design/prefix_caching/
- vLLM multimodal prefix caching PR: https://github.com/vllm-project/vllm/pull/11187
- LMCache multimodal PR #882 + blog (2025-07-03) + docs/api_reference/multimodality.html
- Production Stack KV-aware routing + sharing-kv-cache docs (docs.vllm.ai/projects/production-stack)
- Dynamo KV-cache-aware routing: https://docs.nvidia.com/dynamo/latest/user-guides/kv-cache-aware-routing
- llm-d precise prefix-cache-aware routing: github.com/llm-d/llm-d/.../precise-prefix-cache-aware
- Mooncake Store: https://vllm.ai/blog/2026-05-06-mooncake-store
- VLCache: https://arxiv.org/abs/2512.12977
