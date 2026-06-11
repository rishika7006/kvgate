# KVGate Benchmark Report

Reproducible measurements of KVGate's headline features on real GPUs with a multimodal
vision-language model. Where a technique does not help, that is stated explicitly.

- **Model:** `llava-hf/llava-onevision-qwen2-7b-ov-hf` (Llava-OneVision-7B, about 6.5k vision
  tokens per 1024x1024 image)
- **Serving engine:** vLLM 0.11.0 with `--enforce-eager` (removes CUDA-graph compile spikes, so
  latency reflects steady-state serving rather than warmup)
- **Hardware:** RunPod, single A40 (offload) and two A40s (routing)
- **Client:** `loadtest/multimodal_bench.py` (multimodal VQA trace, real base64 images),
  percentiles over all requests; a separate different-seed warm-up precedes each measured run

---

## 1. Smart routing: prefix_kv_aware vs round_robin (2-GPU fleet)

**Setup.** Two vLLM replicas, one per GPU. Each replica's GPU KV cache is capped
(`--num-gpu-blocks-override 3000`) so the working set (12 distinct 1024x1024 images) cannot all
stay resident on a single replica. 120 requests, concurrency 8. The gateway routes with
`round_robin` (KV-blind baseline) vs `prefix_kv_aware`, which hashes each request's prefix,
including the image bytes, and sends it to the replica that already holds that prefix warm.

![Routing TTFT](assets/routing_ttft.png)

| Metric | round_robin | prefix_kv_aware | Improvement |
|---|---|---|---|
| TTFT p50 | 568 ms | **434 ms** | 24% lower |
| TTFT p95 | 2,783 ms | **1,516 ms** | **1.84x lower** |
| TTFT p99 | 3,642 ms | **2,662 ms** | 27% lower |
| Throughput | 2.69 req/s | **3.06 req/s** | **+14%** |
| Per-replica split | 72 / 72 | 73 / 71 | balanced |
| Routing-affinity hit rate | n/a | **98.6%** | n/a |

**Takeaway.** Prefix-aware routing cut tail latency nearly in half while keeping load balanced
across both GPUs. Round-robin scatters each image across both replicas, so each one keeps
re-prefilling about 6.5k vision tokens on a miss; prefix-aware keeps each image's KV resident on
one replica (98.6% warm hits). The 73/71 split shows the load guard working; affinity-first
routing without it would pile popular images onto one GPU and regress p95.

Raw data: [`results/routing/D.json`](../results/routing/D.json),
[`results/routing/E.json`](../results/routing/E.json).

---

## 2. LMCache CPU KV offload under GPU memory pressure

**Setup.** Single A40, 40 distinct 1024x1024 images, 80 requests, concurrency 4. The GPU KV cache
is capped (`--num-gpu-blocks-override`) to force the working set to overflow GPU memory, the
regime CPU offload is built for. Baseline is vLLM's GPU-only prefix cache; the treatment adds
LMCache 0.3.7 offloading KV to CPU.

![LMCache TTFT and throughput](assets/lmcache_ttft.png)

| GPU KV cap | vLLM cache only (TTFT p50 / thr) | + LMCache (TTFT p50 / thr) | Gain |
|---|---|---|---|
| 3072 blocks | 855 ms / 1.18 req/s | **422 ms / 1.37 req/s** | **2.0x lower TTFT**, +16% thr |
| 2560 blocks | 1426 ms / 0.92 req/s | **902 ms / 1.52 req/s** | 1.6x lower TTFT, **+65% thr** |

**Takeaway.** Under memory pressure, vLLM's GPU prefix cache thrashes (its hit rate fell to about
41% at 2560 blocks); LMCache's CPU offload keeps the multimodal KV warm and recovers it faster
than recomputing it. The gain is about 1.5x to 2x. When the working set fits in GPU, vLLM's own
cache suffices and there is no gain; the win only appears under pressure.

Raw data: `results/Bp.json`, `results/Cp.json` (3072 blocks); `results/Bp2.json`,
`results/Cp2.json` (2560 blocks).

---

## 3. KV-offload hierarchy: where does the KV live? (CPU vs Redis)

**Setup.** Single A40, same model, 40 distinct 1024x1024 images, 80 requests, GPU KV capped.
Three LMCache configs run back-to-back, with KV offloaded to nowhere (baseline), to CPU RAM
(`local_cpu: true`), or directly to Redis (`local_cpu: false`, `remote_url: redis://...`).
LMCache's tiers are independent, so Redis is a direct GPU-to-Redis target, not a forced
GPU-to-CPU-to-Redis chain.

| Config | KV destination | TTFT p50 | Throughput | Memory used (direct proof) |
|---|---|---|---|---|
| control | GPU only (recompute) | 1393 ms | 1.11 req/s | none |
| **+ LMCache to CPU** | CPU RAM | **249 ms** | **2.33 req/s** | **CPU RAM +35 GB** |
| + LMCache to Redis | Redis (direct) | 1424 ms | 1.08 req/s | **Redis used_memory +4.7 GB** |

**Direct evidence the offload happened** (not just faster numbers):
- CPU tier: system RAM rose about 35 GB during the run, and LMCache logged every transfer
  (`Stored 2048 tokens ... 12.7 GB/s; Retrieved 4151 tokens ... 22.1 GB/s`).
- Redis tier: Redis `used_memory` went from 1 MB to 4740 MB; the KV is provably living in Redis.

**Takeaway.** CPU offload is the latency win (5.6x lower TTFT, 2.1x throughput) because recovering
KV from pinned CPU RAM (about 22 GB/s) beats recomputing about 6.5k vision tokens. Redis is not a
latency win here (1424 ms is close to baseline): on loopback, serialization plus transfer roughly
cancels the recompute saving. Its value is capacity and cross-host KV sharing, not speed. Reported
as measured.

Raw: `results/offload/{control,cpu,redis}.json`, full run log `results/offload/cpuproof.out`,
LMCache transfer logs `results/offload/lmcache_transfers.log`.

---

## 4. Gateway overhead

**Setup.** `loadtest/overhead_bench.py` fires unique (cache-busting) requests at KVGate in front
of a zero-latency mock backend (`config/config.overhead.yaml`), so the measured latency is the
gateway's own work (auth, routing decision, metrics, serialization) plus loopback HTTP, not any
model compute.

| Concurrency | Added latency p50 / p95 / p99 | Throughput |
|---|---|---|
| 1 (intrinsic per-request) | **1.07 / 1.52 / 1.72 ms** | 866 req/s single-stream |
| 16 (single worker, saturated) | 27 / 76 / 119 ms | about 460 req/s |

**Takeaway.** KVGate adds about 1 ms per request, negligible next to multimodal TTFT (250 to 2700
ms measured above), well under 1% of inference time. Throughput here is a single Python/uvicorn
worker; the gateway is stateless, so it scales horizontally with more workers and replicas. For an
LLM fleet the gateway is not the bottleneck, the GPU is, which is what the KV-cache work above
optimizes. Raw: `results/overhead.json`, `results/overhead_peak.json`.

---

## 5. Reproducing

```bash
# charts (from the raw JSONs already in results/)
python scripts/make_charts.py            # writes docs/assets/{routing_ttft,lmcache_ttft}.png

# comparison tables
python scripts/compare_results.py D=results/routing/D.json E=results/routing/E.json

# gateway overhead (no GPU needed)
kvgate run -c config/config.overhead.yaml --port 8085 &
python loadtest/overhead_bench.py --host http://localhost:8085 --requests 1000 --concurrency 1
```

The GPU runs (routing and offload) use vLLM 0.11.0 + LMCache 0.3.7 on a CUDA 12.8 host. Routing
uses two replicas (one per GPU) with the gateway flipping `routing.strategy`; offload uses a
single replica with `--kv-transfer-config LMCacheConnectorV1` and a KV-cap sweep.

---

## 6. Methodology notes and caveats

- `--enforce-eager` on every run, otherwise the first requests pay CUDA-graph compile time and
  pollute the TTFT percentiles.
- A different-seed warm-up precedes each measured run, and the server is restarted between configs
  so no state leaks across runs.
- Memory pressure is the point of both offload experiments. With ample GPU memory and a small
  working set, neither offload nor prefix-aware routing helps, and that is reported as-is.
- `nvidia-smi` is unreliable inside the container (PID namespace reports 0 MiB), so replica health
  was verified via vLLM `/health` and a real chat request, not GPU memory readouts.
- Numbers are single-run point estimates on rented GPUs, intended to show direction and magnitude.
