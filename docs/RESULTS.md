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

## ⏳ Routing (Scenario D vs E): logic validated, GPU TTFT-delta deferred

- **Routing logic validated on the mock fleet:** `prefix_kv_aware` achieved **99.2%
  routing-affinity hit rate** and **balanced load (59/61)** across replicas — proving the
  router sticks sessions to warm replicas without snowballing.
- **GPU TTFT-delta not yet captured.** Two 7B replicas don't fit on one 48 GB A40 (weights
  + activation leave no KV), and after many vLLM start/kill cycles the pod accumulated
  un-killable orphan processes (zombie ports, vanishing /tmp files). **The right setup is a
  fresh 2-GPU pod (one replica per GPU)** — clean, realistic for cross-replica routing, and
  free of single-GPU cramming. Deferred to that environment.

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
