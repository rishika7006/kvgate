# Benchmark results & GPU run notes

Status as of the first GPU session (RunPod, 1× RTX A6000 48 GB, Llava-OneVision-7B).

## ✅ Captured: Scenario A vs B — prefix caching (single replica)

Fair comparison (both `--enforce-eager` to remove the compile confound, both warmed up
with a different-seed run, server restarted between configs). Workload: 240 requests,
40 sessions × 6 turns, 20 images, concurrency 8.

| Metric | A: caching OFF | B: caching ON | Improvement |
|---|---|---|---|
| TTFT p50 | 7,658 ms | **103 ms** | **~74× faster** |
| TTFT p95 | 10,312 ms | 2,020 ms | ~5× |
| Throughput | 0.95 req/s | **8.83 req/s** | **~9.3×** |
| E2E p50 | 10,250 ms | 405 ms | ~25× |

**Takeaway:** on a multimodal workload with a long shared prompt + repeated images,
vLLM prefix caching cut time-to-first-token ~74× and raised throughput ~9×.

## ✅ Captured: LMCache multimodal offload under GPU memory pressure (Scenario C)

**The headline LMCache result.** Single A40, Llava-OneVision-7B, 40 large (1024×1024)
images, 120 requests. We cap the GPU KV cache (`--num-gpu-blocks-override`) to simulate
memory pressure / a large working set — the regime LMCache exists for (this is the
multimodal KV-offload-to-CPU technique, the same idea as the AWS work). LMCache **0.3.7**
(multimodal-capable; `apply_mm_hashes_to_token_ids` confirmed present) vs vLLM's GPU-only
prefix cache.

| GPU KV cap | B: vLLM cache only (TTFT p50 / thr) | C: + LMCache (TTFT p50 / thr) | Gain |
|---|---|---|---|
| 3072 blocks | 855 ms / 1.18 req/s | **422 ms / 1.37 req/s** | **2.0× lower TTFT**, +16% thr |
| 2560 blocks | 1426 ms / 0.92 req/s | **902 ms / 1.52 req/s** | 1.6× lower TTFT, **+65% thr** |

At 2560 blocks B's vLLM prefix-cache hit rate fell to ~41% (thrashing); LMCache's CPU
offload kept the multimodal KV warm. **Honest framing:** ~1.5–2× — real and defensible,
NOT the inflated "3–10×" vendor claims (which our research refuted). When the working set
fits in GPU, vLLM's own cache suffices and C ≈ B; the gain appears under pressure.

Raw JSON: `results/Bp.json`,`Cp.json` (3072), `Bp2.json`,`Cp2.json` (2560).

## ✅ Captured: KV-offload hierarchy — CPU vs Redis (where the KV lives)

Single A40, 40 images, 80 reqs, GPU KV capped to 2560 blocks. Three LMCache configs:

| Config | KV destination | TTFT p50 | Throughput | Direct memory proof |
|---|---|---|---|---|
| control | GPU only | 1393 ms | 1.11 req/s | — |
| **+ LMCache → CPU** | CPU RAM | **249 ms** | **2.33 req/s** | **CPU RAM +35 GB** |
| + LMCache → Redis | Redis (direct, `local_cpu:false`) | 1424 ms | 1.08 req/s | **Redis +4.7 GB** |

CPU offload: **5.6× lower TTFT, 2.1× throughput**; LMCache logged store ~13 GB/s, retrieve
~22 GB/s. Redis: stored 4.7 GB of KV (1 MB→4740 MB) — cross-host tier works — but **not** a
latency win on loopback (its value is capacity + cross-host sharing, the AWS pattern). Raw:
`results/offload/{control,cpu,redis}.json`, `cpuproof.out`, `cpu.log`. Full report:
[`docs/BENCHMARK_REPORT.md`](BENCHMARK_REPORT.md).

## ✅ Captured: Smart routing (Scenario D vs E) on a 2-GPU fleet

**The headline routing result.** Two `Llava-OneVision-7B` replicas, **one per GPU** (2× A40),
each with its GPU KV cache capped (`--num-gpu-blocks-override 3000`) so the working set
(12 distinct 1024×1024 images) overflows a single replica. 120 requests, concurrency 8.
We compare the gateway's `round_robin` strategy (D) against `prefix_kv_aware` (E), which
hashes each request's prefix (incl. the image bytes) and routes it to the replica that
already holds that prefix warm — maximizing cross-replica KV reuse.

| Metric | D: round_robin | E: prefix_kv_aware | Improvement |
|---|---|---|---|
| TTFT p50 | 568 ms | **434 ms** | −24% |
| TTFT **p95** | 2,783 ms | **1,516 ms** | **1.84× lower (−45%)** |
| TTFT p99 | 3,642 ms | **2,662 ms** | −27% |
| Throughput | 2.69 req/s | **3.06 req/s** | **+14%** |
| Per-replica split | 72 / 72 | 73 / 71 | balanced (no snowball) |
| Routing-affinity hit rate | — | **98.6%** | — |

**Takeaway:** prefix-aware routing cut tail TTFT (p95) nearly in half versus round-robin
while keeping load **balanced** across both replicas — round-robin scatters each image
across both GPUs (so each replica re-prefills ~6.5k vision tokens on a miss), whereas
prefix-aware keeps each image's KV resident on one replica (98.6% warm hits). The load
guard (`max_inflight_skew: 2`) is what preserves the 73/71 balance — affinity-first routing
*without* it would snowball popular images onto one GPU.

Raw JSON: `results/routing/D.json`, `results/routing/E.json`; full run log
`results/routing/route2.out`.

> Earlier mock-fleet validation (kept for reference): `prefix_kv_aware` hit **99.2%**
> routing-affinity and balanced load 59/61 — consistent with the on-GPU result above.

---

## 🔧 Known-good environment (CUDA-12.8 driver pods, e.g. RunPod "PyTorch 2.8.0")

The latest `pip install vllm` pulls a CUDA-12.9+ build that the 12.8 driver rejects, and
drags in too-new `transformers`/`mistral_common`. This exact pinned set works:

```bash
pip install "vllm==0.11.0" "torch==2.8.0" "transformers==4.57.6" "mistral_common==1.8.2" hf_transfer
pip install -e .          # InferGate + its deps (httpx, fastapi, …) for the benchmark client
```
Verify the GPU is visible:
```bash
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
# expect: 2.8.0+cu128 12.8 True
```

### GPU cleanup (avoid orphaned memory between runs)
`pkill -f vllm` misses vLLM's worker subprocesses. Kill by GPU PID instead:
```bash
nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits | xargs -r kill -9
```
If memory is held by `[Not Found]` PIDs (orphaned, un-killable from the container),
**Restart the pod** to clear the GPU (Restart preserves the disk).

---

## ▶️ Resume checklist (next session)

1. Start the pod → reopen web terminal.
2. `cd ~/infergate && source ~/venv/bin/activate`
3. `nvidia-smi --query-gpu=memory.used --format=csv`  → should be ~0.
   (If the venv/model is gone because the pod was Terminated, re-run the
   "Known-good environment" install above; the model re-downloads in ~3 min.)
4. Start two replicas (ports 8001/8002, `--gpu-memory-utilization 0.42 --max-model-len 8192
   --enforce-eager`), confirm both log "Application startup complete".
5. Gateway round-robin → run D; flip `routing.strategy` to `prefix_kv_aware`, restart
   gateway → run E. Use `--enforce-eager`, a seed-999 warm-up, and `--out D.json` / `E.json`.
6. `python scripts/compare_results.py A=A.json B=B.json D=D.json E=E.json`.
