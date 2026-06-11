# Beginner's guide: running the KVGate GPU benchmark on RunPod

This is a click-by-click guide for someone who has **never rented a GPU**. Follow it
top to bottom. You'll end with real numbers: time-to-first-token (TTFT), throughput,
and KV-cache hit rate — for both the **offloading** test and the **smart-routing** test.

> 💸 **Cost:** ~$3 for Phase 1 (one GPU), ~$5–7 for Phase 2 (two GPUs). You pay only
> while a pod is *running*. **Always STOP or TERMINATE the pod when done.**

> ⚠️ **Verify-as-you-go:** vLLM/LMCache flags change between versions. If a command
> errors, run `vllm serve --help` and check the flag name, or ping me with the error.

---

## Phase 0 — Account setup (5 min, once)

1. Go to **runpod.io** → **Sign Up**.
2. Left menu → **Billing** → add **$15** (covers everything with margin).
3. Left menu → **Settings** → **SSH Public Keys**: optional. The **web terminal** is
   enough for this guide, so you can skip SSH.

---

## Getting KVGate onto the pod

The pod is a fresh Linux machine — it needs our code. Two options:

- **Option A (recommended):** I push KVGate to a **private** GitHub repo. On the
  pod you run `git clone <url>`. It stays private until results are good, then we flip
  it public. (This satisfies your "push only when results are good" rule — private ≠
  published.)
- **Option B:** Upload the few needed files manually via the RunPod web file browser:
  `loadtest/multimodal_bench.py`, `scripts/compare_results.py`,
  `config/config.kvaware.example.yaml`, and the `kvgate` package.

Tell me which you prefer and I'll set it up. The commands below assume the repo is at
`~/kvgate`.

---

## Phase 1 — Offloading test (ONE GPU) — your AWS theme

This measures the benefit of **LMCache KV-cache offloading** on a single server:
**A** (no cache) → **B** (vLLM's built-in prefix cache) → **C** (+ LMCache offload).

### 1.1 Deploy a 1-GPU pod
1. Console → **Pods** → **Deploy** → **GPU Cloud**.
2. **GPU:** pick any **24 GB** card — `RTX 4090`, `L4`, or `A5000` (cheapest available).
3. **Template:** `RunPod PyTorch 2.x` (comes with CUDA + Python).
4. **Container disk:** 40 GB. **Expose HTTP port:** `8000`.
5. **Deploy On-Demand** → wait ~1 min → **Connect** → **Start Web Terminal**.

### 1.2 Install everything (paste into the web terminal)
```bash
pip install -q vllm lmcache transformers
cd ~ && git clone <your-private-repo-url> kvgate && cd kvgate
pip install -q -e .
```

### 1.3 Make 20 test images (no downloads needed)
```bash
mkdir -p images && python - <<'PY'
from PIL import Image, ImageDraw
import random
random.seed(0)
for i in range(20):
    im = Image.new("RGB", (512, 512), (random.randint(0,255),)*3)
    d = ImageDraw.Draw(im)
    for _ in range(8):
        x,y = random.randint(0,460), random.randint(0,460)
        d.rectangle([x,y,x+random.randint(10,50),y+random.randint(10,50)],
                    fill=(random.randint(0,255),random.randint(0,255),random.randint(0,255)))
    d.text((20,20), f"image {i}", fill=(255,255,255))
    im.save(f"images/img_{i:02d}.png")
print("wrote 20 images")
PY
```
*(You can swap in real photos later — just drop them in `images/`.)*

### 1.4 Set the model
```bash
export MODEL=llava-hf/llava-onevision-qwen2-7b-ov-hf
```

### 1.5 Run the three scenarios
For **each** scenario: start vLLM, wait until it prints `Application startup complete`,
then in a **second web terminal tab** run the benchmark, then `Ctrl-C` vLLM.

**A — no caching (baseline):**
```bash
# tab 1:
vllm serve $MODEL --port 8000 --no-enable-prefix-caching --gpu-memory-utilization 0.9 --max-model-len 16384
# tab 2:
python loadtest/multimodal_bench.py --host http://localhost:8000 --model $MODEL \
  --images-dir images --images 20 --sessions 40 --turns 6 --concurrency 8 --out A.json
curl -s localhost:8000/metrics | grep -E "prefix_cache_(hits|queries)"   # record these
```

**B — vLLM prefix caching (default on):**
```bash
# tab 1:
vllm serve $MODEL --port 8000 --gpu-memory-utilization 0.9 --max-model-len 16384
# tab 2:
python loadtest/multimodal_bench.py --host http://localhost:8000 --model $MODEL \
  --images-dir images --images 20 --sessions 40 --turns 6 --concurrency 8 --out B.json
curl -s localhost:8000/metrics | grep -E "prefix_cache_(hits|queries)"
```

**C — + LMCache offloading:**
```bash
# tab 1:
cat > lmcache.yaml <<'YAML'
chunk_size: 256
local_cpu: true
max_local_cpu_size: 20
YAML
LMCACHE_CONFIG_FILE=lmcache.yaml vllm serve $MODEL --port 8000 \
  --gpu-memory-utilization 0.9 --max-model-len 16384 \
  --kv-transfer-config '{"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'
# tab 2:
python loadtest/multimodal_bench.py --host http://localhost:8000 --model $MODEL \
  --images-dir images --images 20 --sessions 40 --turns 6 --concurrency 8 --out C.json
```

### 1.6 See the offloading result
```bash
python scripts/compare_results.py A=A.json B=B.json C=C.json
```
You should see TTFT drop from A → B → C. **Stop the pod now** (Console → pod → **Stop**)
if you're not continuing immediately.

---

## Phase 2 — Smart-routing test (TWO GPUs) — the headline

This measures **our gateway's** benefit: **D** (random routing) → **E** (`prefix_kv_aware`),
with offloading ON in both. The D→E gap is the original contribution.

### 2.1 Deploy a 2-GPU pod (same steps, choose **2× GPU**), then:
```bash
cd ~/kvgate
export MODEL=llava-hf/llava-onevision-qwen2-7b-ov-hf
cat > lmcache.yaml <<'YAML'
chunk_size: 256
local_cpu: true
max_local_cpu_size: 20
YAML
# Replica 1 on GPU 0 (tab 1):
CUDA_VISIBLE_DEVICES=0 LMCACHE_CONFIG_FILE=lmcache.yaml vllm serve $MODEL --port 8001 \
  --gpu-memory-utilization 0.9 --max-model-len 16384 \
  --kv-transfer-config '{"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'
# Replica 2 on GPU 1 (tab 2):
CUDA_VISIBLE_DEVICES=1 LMCACHE_CONFIG_FILE=lmcache.yaml vllm serve $MODEL --port 8002 \
  --gpu-memory-utilization 0.9 --max-model-len 16384 \
  --kv-transfer-config '{"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'
```

### 2.2 Point KVGate at both replicas
Create `config/gpu.yaml` (I'll generate this exactly for you):
```yaml
providers:
  - { name: r1, type: openai_compatible, base_url: http://localhost:8001/v1 }
  - { name: r2, type: openai_compatible, base_url: http://localhost:8002/v1 }
models:
  - name: vlm
    deployments:
      - { provider: r1, model: llava-hf/llava-onevision-qwen2-7b-ov-hf }
      - { provider: r2, model: llava-hf/llava-onevision-qwen2-7b-ov-hf }
cache: { enabled: false }
ratelimit: { enabled: false }
routing: { strategy: round_robin }   # we flip this between D and E
```

### 2.3 Run D (baseline) then E (smart)
```bash
# tab 3 — D: round_robin
kvgate run -c config/gpu.yaml --port 8080 &
python loadtest/multimodal_bench.py --host http://localhost:8080 --model vlm \
  --images-dir images --images 20 --sessions 80 --turns 6 --concurrency 16 --out D.json
kill %1

# edit config/gpu.yaml: routing.strategy: prefix_kv_aware  (set max_inflight_skew: 8)
# tab 3 — E: prefix_kv_aware
kvgate run -c config/gpu.yaml --port 8080 &
python loadtest/multimodal_bench.py --host http://localhost:8080 --model vlm \
  --images-dir images --images 20 --sessions 80 --turns 6 --concurrency 16 --out E.json
kill %1
```

### 2.4 The headline comparison
```bash
python scripts/compare_results.py D=D.json E=E.json
```
This prints the **TTFT p95 reduction** and **affinity hit rate** for E vs D — your result.

### 2.5 ⛔ STOP THE POD
Console → pod → **Stop** (keeps disk, cheap) or **Terminate** (deletes everything).
Forgetting this is the only way to overspend.

---

## What we do with the numbers
Send me `A.json … E.json` (and the `prefix_cache` lines). I'll generate the final
comparison tables, a short write-up/blog draft, your résumé bullets — and **then** we
make the GitHub repo public.

## If something breaks
- vLLM out-of-memory → lower `--gpu-memory-utilization` to `0.85` or `--max-model-len 8192`.
- `--no-enable-prefix-caching` rejected → run `vllm serve --help | grep prefix` for the
  current flag name.
- Model won't load → try the proven fallback model and tell me; we adjust.
- Anything else → copy the error to me.

## A gentler start
You don't have to do Phase 2 immediately. **Phase 1 alone** (one GPU, ~$3) already
proves the offloading result tied to your AWS work. Do that first, get comfortable,
then come back for Phase 2.
