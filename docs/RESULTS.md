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

## ⏳ Pending: Scenario D vs E — KV/prefix-aware routing (2 replicas)

Not yet completed (GPU ran out of memory from orphaned workers; pod restart needed).
Early signal from a partial run: `prefix_kv_aware` showed **99.2% routing-affinity hit
rate** vs round-robin's none — routing logic works; need a clean 2-replica run for the
TTFT payoff. Plan: two vLLM replicas on the one 48 GB GPU (`--gpu-memory-utilization
0.42` each), gateway round-robin (D) vs prefix_kv_aware (E).

## 🛑 Skipped: Scenario C — LMCache offloading

LMCache 0.4.6 requires `transformers>=5.4`, which conflicts with the `transformers 4.x`
that vLLM 0.11.0 (the version matching this pod's CUDA-12.8 driver) needs. On a small
20-image workload that fits in GPU memory it would ≈ B anyway. Revisit with a
vLLM-0.11-compatible LMCache version if we want the explicit offloading column.

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
