# Reproducing the GPU benchmarks

This folder holds everything needed to reproduce the GPU results in
[`docs/BENCHMARK_REPORT.md`](../docs/BENCHMARK_REPORT.md). The local-only benchmarks
(gateway overhead, charts, comparison tables) need no GPU and are covered in the report's
Reproducing section.

- **Model:** `llava-hf/llava-onevision-qwen2-7b-ov-hf`
- **Hardware used:** RunPod, CUDA 12.8 host. Single A40 for offload, two A40s for routing.
- **Engines:** vLLM 0.11.0 and LMCache 0.3.7 (pinned for multimodal support and mutual
  compatibility; newer LMCache requires a newer transformers than vLLM 0.11 allows).

## 0. Environment

vLLM and LMCache run on the inference backend, not inside KVGate, so they are installed
separately from the gateway. This exact pinned set is known to work on a CUDA 12.8 host:

```bash
python3 -m venv ~/venv && source ~/venv/bin/activate && pip install -U pip
pip install "vllm==0.11.0" "torch==2.8.0" "transformers==4.57.6" "mistral_common==1.8.2" hf_transfer
pip install "lmcache==0.3.7"
pip install -e ".[dev]"        # KVGate + the benchmark client (httpx, etc.)

export MODEL=llava-hf/llava-onevision-qwen2-7b-ov-hf
python scripts/gen_images.py 40   # writes 40 distinct 1024x1024 images to ./images
```

## 1. Smart routing (two GPUs, one replica each)

Start one vLLM replica per GPU. The KV cache is capped so the working set cannot all stay
resident, which is what makes routing matter.

```bash
CUDA_VISIBLE_DEVICES=0 vllm serve $MODEL --port 8001 --enforce-eager \
  --gpu-memory-utilization 0.9 --max-model-len 16384 --num-gpu-blocks-override 3000 &
CUDA_VISIBLE_DEVICES=1 vllm serve $MODEL --port 8002 --enforce-eager \
  --gpu-memory-utilization 0.9 --max-model-len 16384 --num-gpu-blocks-override 3000 &
```

Point the gateway at them and run both strategies. The logical model is `vlm`
(see [`config/config.kvaware.example.yaml`](../config/config.kvaware.example.yaml)).

```bash
export VLLM_R1_URL=http://localhost:8001/v1 VLLM_R2_URL=http://localhost:8002/v1

# Baseline: set routing.strategy: round_robin in the config, then
kvgate run -c config/config.kvaware.example.yaml --port 8080 &
python loadtest/multimodal_bench.py --host http://localhost:8080 --model vlm \
  --images-dir images --images 12 --sessions 120 --turns 1 --concurrency 8 --out D.json

# Headline: set routing.strategy: prefix_kv_aware, restart the gateway, rerun
python loadtest/multimodal_bench.py --host http://localhost:8080 --model vlm \
  --images-dir images --images 12 --sessions 120 --turns 1 --concurrency 8 --out E.json

python scripts/compare_results.py D=D.json E=E.json
```

## 2 and 3. LMCache offload (one GPU): CPU and Redis

Run the same workload against a single replica with different KV destinations. The baseline
is the same `vllm serve` command **without** the `--kv-transfer-config` flag; the offload
runs add it and select a tier via `LMCACHE_CONFIG_FILE`.

```bash
KV='{"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'

# Baseline (GPU only, no offload)
vllm serve $MODEL --port 8001 --enforce-eager --gpu-memory-utilization 0.9 \
  --max-model-len 16384 --num-gpu-blocks-override 2560 &

# CPU offload
LMCACHE_CONFIG_FILE=benchmarks/lmcache_cpu.yaml \
  vllm serve $MODEL --port 8001 --enforce-eager --gpu-memory-utilization 0.9 \
  --max-model-len 16384 --num-gpu-blocks-override 2560 --kv-transfer-config "$KV" &

# Redis offload (start redis first: redis-server --daemonize yes)
LMCACHE_CONFIG_FILE=benchmarks/lmcache_redis.yaml \
  vllm serve $MODEL --port 8001 --enforce-eager --gpu-memory-utilization 0.9 \
  --max-model-len 16384 --num-gpu-blocks-override 2560 --kv-transfer-config "$KV" &
```

For each config, run the benchmark directly against the replica and save a separate file:

```bash
python loadtest/multimodal_bench.py --host http://localhost:8001 --model $MODEL \
  --images-dir images --images 40 --sessions 80 --turns 1 --concurrency 4 --out cpu.json
```

The Section 2 sweep (vLLM cache only vs CPU offload) repeats this at two caps:
`--num-gpu-blocks-override 3072` and `2560`. Restart the server between every config so no
state leaks. Configs: [`lmcache_cpu.yaml`](lmcache_cpu.yaml), [`lmcache_redis.yaml`](lmcache_redis.yaml).

## Notes

- `--enforce-eager` is required so the first requests do not pay CUDA-graph compile time and
  skew the TTFT percentiles.
- `nvidia-smi` reports 0 MiB inside RunPod containers (PID namespace), so verify replicas via
  the vLLM `/health` endpoint and a real chat request, not GPU memory readouts.
- Two 7B replicas do not fit on one 48 GB GPU; routing needs two separate GPUs.
