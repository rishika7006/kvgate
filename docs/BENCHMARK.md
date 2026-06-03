# InferGate multimodal KV-aware routing — benchmark runbook (M3/M4)

A step-by-step, copy-paste runbook to reproduce the "with vs without" comparison on
**2× 24 GB GPUs** (L4 / A10G) using **Llava-OneVision-7B** + **vLLM** + **LMCache**.
Mock dry-run instructions (no GPU) are at the end.

> Report only **your measured** numbers. Do not cite vendor figures (LMCache 3–10×,
> Mooncake 46×, VLCache 16.95×) — verification flagged them as unaudited. See
> `docs/RESEARCH_KV_CACHE.md`.

---

## 0. Provision

- 2× L4 or A10G (24 GB), same host or same low-latency network.
- Python 3.10+, CUDA drivers. Cost ≈ $1.6–2.4/hr total; full sweep ≈ 3–4 hrs (~$6–10).

```bash
pip install "vllm==<pin-current>" "lmcache==0.4.6" transformers accelerate
pip install "infergate @ git+https://github.com/<you>/infergate"   # or: pip install -e .
```

## 1. LMCache config (`lmcache.yaml`)

```yaml
chunk_size: 256
local_cpu: true
max_local_cpu_size: 30   # GiB of CPU RAM for offloaded KV
```

## 2. Bring up the 2-replica fleet

Replica 1 (GPU 0, port 8001):
```bash
LMCACHE_CONFIG_FILE=./lmcache.yaml CUDA_VISIBLE_DEVICES=0 \
vllm serve llava-hf/llava-onevision-qwen2-7b-ov-hf \
  --port 8001 --gpu-memory-utilization 0.90 --max-model-len 32768 \
  --limit-mm-per-prompt image=4 \
  --kv-transfer-config '{"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'
```
Replica 2: `CUDA_VISIBLE_DEVICES=1 ... --port 8002`.

**Sanity check (do this before the full sweep):** confirm multimodal KV reuse actually
fires — send the same image+prompt twice and check vLLM's `vllm:prefix_cache_hits_total`
rises and TTFT drops on the 2nd call. If it doesn't, fall back to a documented model and
re-confirm.

## 3. Point InferGate at the fleet

```bash
cp config/config.kvaware.example.yaml config/config.kvaware.yaml
export VLLM_R1_URL=http://localhost:8001/v1
export VLLM_R2_URL=http://localhost:8002/v1
# (edit hf_model in the file if you changed the model)
```

## 4. Run the scenario sweep

Toggle vLLM flags / InferGate strategy per scenario; run the benchmark each time and
save a JSON. Use a long shared system prompt + image revisits (defaults do this).

| Scenario | vLLM replicas | APC | LMCache | InferGate strategy | Output |
|---|---|---|---|---|---|
| A baseline | 1 | `--no-enable-prefix-caching` | off | direct to :8001 | `A.json` |
| B APC | 1 | on (default) | off | direct to :8001 | `B.json` |
| C +LMCache | 1 | on | on | direct to :8001 | `C.json` |
| D fleet RR | 2 | on | on | `round_robin` | `D.json` |
| E fleet KV-aware | 2 | on | on | `prefix_kv_aware` | `E.json` |

For **A–C** point the bench `--host` straight at a single vLLM replica (it's
OpenAI-compatible). For **D/E** point it at InferGate; set `routing.strategy` in the
config accordingly and restart InferGate between the two runs.

```bash
# D: baseline KV-blind load balancer
#   (set routing.strategy: round_robin in config.kvaware.yaml, then:)
infergate run -c config/config.kvaware.yaml --port 8080 &
python loadtest/multimodal_bench.py --host http://localhost:8080 --model vlm \
    --images 50 --sessions 200 --turns 8 --concurrency 32 --out D.json
kill %1

# E: prefix/KV-aware routing
#   (set routing.strategy: prefix_kv_aware, restart, same bench:)
infergate run -c config/config.kvaware.yaml --port 8080 &
python loadtest/multimodal_bench.py --host http://localhost:8080 --model vlm \
    --images 50 --sessions 200 --turns 8 --concurrency 32 --out E.json
kill %1
```

## 5. Build the comparison

```bash
python scripts/compare_results.py A=A.json B=B.json C=C.json D=D.json E=E.json
```

This prints a Markdown table plus the **D→E headline** (TTFT p95 reduction and affinity
hit rate). Grab Grafana screenshots (the dashboard has request rate, latency percentiles,
cache events, routing decisions) for the write-up.

**Metrics to read straight from the engines** (correlate with the gateway numbers):
- `vllm:prefix_cache_hits_total` / `vllm:prefix_cache_queries_total` → engine hit rate
- `vllm:time_to_first_token_seconds` → TTFT distribution
- `infergate_routing_affinity_total{outcome="warm|cold"}` → the gateway's routing quality

## 6. Tear down

```bash
# stop vLLM replicas + InferGate; destroy the GPU instances to stop billing
```

---

## Dry run (no GPU)

Proves the routing + harness work end-to-end against the mock fleet:

```bash
infergate run -c config/config.mock-kvaware.yaml --port 8088 &
python loadtest/multimodal_bench.py --host http://localhost:8088 --model demo \
    --sessions 30 --turns 6 --concurrency 8
kill %1
```

The mock backends return fixed-latency responses, so this validates **routing behavior**
(watch the affinity hit rate climb with `prefix_kv_aware`), not latency gains — those
require the real vLLM+LMCache fleet above.

### Dry-run results (mock fleet, 2 replicas, 120 requests, no GPU)

| Config | Replica split (r1 / r2) | Routing affinity (warm) | OK |
|---|---|---|---|
| `prefix_kv_aware`, no load guard | **120 / 0** (snowball) | 99.2% | 120/120 |
| `prefix_kv_aware`, `max_inflight_skew: 4` | **59 / 61** (balanced) | 98.3% | 120/120 |

This is the headline behavioral result the harness verifies *without a GPU*: prefix
affinity keeps ~98% of requests on a replica that already holds their prefix, while the
load guard prevents a shared system-prompt prefix from snowballing all traffic onto one
replica. On the real fleet (§4), this affinity is what converts into TTFT/throughput gains.
