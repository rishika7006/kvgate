# KVGate — Master Handoff & Status (resume-anywhere)

> **Purpose:** one self-contained file to continue this project in a fresh session with
> ZERO extra context. Read this top to bottom. Other docs referenced at the end.
> Last updated: after the GPU benchmarking sessions (LMCache done; routing GPU pending).

---

## 0. One-paragraph project

**KVGate** = an open-source, OpenAI-compatible **LLM inference gateway** (Python/FastAPI)
that sits in front of a fleet of vLLM replicas. Flagship feature: **multimodal KV/prefix-aware
routing** (`prefix_kv_aware`) — routes each request to the replica that already holds its
prefix (incl. the same image) warm, maximizing KV reuse. Also: response caching, rate
limiting, failover/circuit-breaking, Prometheus/Grafana, a Next.js dashboard, 59 tests.
Built by **Rishika Vaish** (new-grad SWE/ML target) to extend her AWS internship work
(LMCache KV-offload on multimodal LLMs) into a portfolio flagship + benchmark.

- **Private GitHub repo:** `github.com/rishika7006/kvgate` (push only-when-good rule).
- **Commits authored as `rishika7006` only** (no Claude co-author — history was rewritten).

---

## 1. STATUS: what's done vs pending

### ✅ DONE (committed)
- Core gateway v0.1.0; **M1** prefix_kv_aware routing; **M1.5** load guard; **M2** benchmark
  harness; **Next.js dashboard**; full docs; 59 tests pass; ruff+mypy clean (CI).
- **LMCache multimodal GPU win — REAL NUMBERS captured** (see §2). This is the headline,
  tied to the AWS work. Raw JSON in `results/`.
- Routing **logic validated on the mock fleet**: 99.2% routing-affinity hit rate, balanced
  59/61 load — proves the router works.

### ⏳ PENDING
- **Routing GPU TTFT-delta (D vs E on 2 real GPUs).** Repeatedly blocked by RunPod
  environment flakiness (see §4). Logic is proven; only the on-GPU latency number is missing.

### ▶️ AFTER routing number (or now, if finalizing)
- Write LinkedIn post + résumé bullets from results.
- Make the GitHub repo **public**.

---

## 2. RESULTS (real, measured on GPU)

### LMCache multimodal offload under GPU memory pressure (Scenario C vs B)
Single **A40**, **Llava-OneVision-7B**, 40×(1024×1024) images, 120 reqs, `--enforce-eager`,
GPU KV capped via `--num-gpu-blocks-override` to force the working set to overflow GPU.

| GPU KV cap | B: vLLM cache only (TTFT p50 / thr) | C: + LMCache (TTFT p50 / thr) | Gain |
|---|---|---|---|
| 3072 blocks | 855 ms / 1.18 req/s | **422 ms / 1.37 req/s** | **2.0× TTFT**, +16% thr |
| 2560 blocks | 1426 ms / 0.92 req/s | **902 ms / 1.52 req/s** | 1.6× TTFT, **+65% thr** |

At 2560 blocks, vLLM's prefix-cache hit rate fell to ~41% (thrashing); LMCache's CPU offload
kept multimodal KV warm. **Honest framing:** ~1.5–2× — real, NOT the inflated vendor "3–10×".
When the working set fits in GPU, C ≈ B (no pressure → no gain). Raw: `results/Bp.json`,
`Cp.json` (3072), `Bp2.json`,`Cp2.json` (2560).

### Routing (D vs E) — CAPTURED on 2× A40 (one replica per GPU)
12 distinct 1024² images, per-replica KV capped (`--num-gpu-blocks-override 3000`), 120 reqs, conc 8.

| Metric | D round_robin | E prefix_kv_aware | Gain |
|---|---|---|---|
| TTFT p95 | 2783 ms | **1516 ms** | **1.84× (−45%)** |
| TTFT p50 | 568 ms | **434 ms** | −24% |
| Throughput | 2.69 req/s | **3.06 req/s** | +14% |
| Load split | 72/72 | 73/71 | balanced |
| Affinity | — | **98.6%** | — |

Both scenarios balanced load → fair comparison. E cut tail TTFT ~half while staying balanced
(load guard `max_inflight_skew:2` prevents snowball). Raw: `results/routing/{D,E}.json`.
**Root cause of all earlier routing failures:** RunPod's **nginx squats on port 8001** →
vLLM can't bind → `/health` answered by nginx → gateway circuit-broke r1 → all traffic to
r2 → garbage comparison. Fixed by using ports **19001/19002/19080**, a per-replica smoke
chat test before benchmarking, and a self-daemonizing launcher writing to `/root/igout`
(NOT `/tmp` or `/workspace` — both misbehaved for detached writes).

---

## 3. KNOWN-GOOD ENVIRONMENT (this is gold — avoids days of dependency hell)

RunPod fleets are on **CUDA 12.8 driver (570.x)** → must use vLLM 0.11.0 (latest vLLM needs
a newer driver). Exact pinned set that WORKS (incl. multimodal LMCache):

```bash
python3 -m venv ~/venv && source ~/venv/bin/activate && pip install -U pip
pip install "vllm==0.11.0" "torch==2.8.0" "transformers==4.57.6" "mistral_common==1.8.2" hf_transfer
pip install -e .                 # KVGate + deps (httpx, fastapi…)
pip install "lmcache==0.3.7"     # ONLY for the LMCache (Scenario C) test; multimodal-capable
```
- LMCache 0.4.6 (latest) requires transformers≥5.4 → CONFLICTS with vLLM 0.11. Use **0.3.7**.
- LMCache 0.3.7 multimodal support confirmed (handles image KV). Config file `lmcache.yaml`:
  `chunk_size: 256` / `local_cpu: true` / `max_local_cpu_size: 30`.
- vLLM serve flags that work: `--enforce-eager` (avoids CUDA-graph compile spikes),
  `--max-model-len 16384`, `--gpu-memory-utilization 0.9` (single replica per GPU),
  `--num-gpu-blocks-override N` (cap KV to create memory pressure),
  LMCache: `--kv-transfer-config '{"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'`.
- Model: `llava-hf/llava-onevision-qwen2-7b-ov-hf` (LMCache-documented; ~15 GB; ~6.5k vision
  tokens/image at 1024×1024). Generate test images: `gen_images.py` (40×1024² → `images/`).

---

## 4. THE ROUTING GPU RUN — procedure + the flakiness wall

**Goal:** 2 vLLM replicas (ONE per GPU), gateway routes D (round_robin) vs E (prefix_kv_aware);
per-replica KV capped (`--num-gpu-blocks-override 3000`) + 12 distinct large images so
round-robin overflows each replica while prefix-aware stays local → E should win on TTFT.

**Correct setup:** 2-GPU pod (2× A40), `CUDA_VISIBLE_DEVICES=0`→port 8001, `=1`→port 8002,
each `--gpu-memory-utilization 0.9`. Gateway config `config/route.yaml` (model `vlm` → r1/r2),
`max_inflight_skew: 2` (prevents the shared-system-prompt snowball). Driver scripts staged on
pod: `~/ig_route2gpu.sh` (full), `~/ig_de.sh` (gateway+D/E only, replicas already up).

**What WORKS:** each replica starts & serves fine in the foreground (verified r2 reached
"Application startup complete"). The env install + Part-1 LMCache run worked.

**What's FLAKY on RunPod (the blocker):**
1. **Long-held SSH sessions drop** (~exit 255) before a ~15-min run finishes → kills foreground processes.
2. **`nohup &`-detached vLLM gets SIGHUP-killed** when the one-shot SSH closes (r2 kept dying; r1 sometimes survived — inconsistent).
3. **`/tmp` is unstable** — redirected log files vanish/stay empty; even the **tmux** socket (`/tmp/tmux-0`) disappeared.
4. **`nvidia-smi` reports 0 MiB** in-container (PID/accounting namespace) — GPU readings are USELESS here; trust `/health` & `/v1/models` endpoints only.
5. Two 7B replicas do NOT fit on ONE 48 GB GPU (weights+overhead leave ~0 KV) → must use 2 separate GPUs.

**Recommended fix for next attempt (to finally get the number):**
- Use a **more stable provider** (Lambda Cloud / Modal / Vast) OR a RunPod pod where `/tmp`
  + tmux persist. Run the whole thing **inside tmux** AND verify the tmux server stays up.
- OR run it as a single self-contained script with replicas + gateway + D/E, launched with
  `setsid`, writing results to the **persistent volume** (`/workspace`, not `/tmp`), and poll
  the `/workspace` JSON with short SSH connections.
- The KVGate code + `loadtest/multimodal_bench.py` + `scripts/compare_results.py` are all
  correct and ready — only the pod-orchestration needs a stable host.

**How Claude drives the pod (for the assistant resuming this):** user authorizes an SSH key
(`~/.ssh/kvgate_runpod.pub`) by pasting it into the pod's `~/.ssh/authorized_keys`; assistant
SSHes from the user's Mac (`Host igpod` in `~/.ssh/config`). Copy repo via
`tar + scp` (no GitHub token needed). Poll with SHORT ssh commands (long ones drop).

---

## 5. BENCHMARK HARNESS usage (`loadtest/multimodal_bench.py`)
Multi-turn / single-turn multimodal VQA trace; sends real images (base64) when `--images-dir`
given. Key flags: `--host --model --images-dir --images N --sessions N --turns N
--concurrency N --seed N --out file.json [--context-tokens N]`. Reports TTFT p50/p95/p99,
throughput, and (for prefix_kv_aware) routing-affinity hit rate. `scripts/compare_results.py
A=a.json B=b.json …` prints a Markdown comparison.

---

## 6. Repo map (key files)
```
src/kvgate/routing/{keying,affinity,router,strategies,state}.py   # the routing core
loadtest/multimodal_bench.py        scripts/compare_results.py
config/{gpu.yaml, config.mock-kvaware.yaml, ...}                      # configs
dashboard/                          # Next.js live dashboard
results/                            # raw LMCache result JSONs
docs/: RESULTS.md  KV_AWARE_PLAN.md  DECISION_GATES.md  HOW_ROUTING_WORKS.md
       RUNPOD_GUIDE.md  RESEARCH_KV_CACHE.md
PROJECT_CONTEXT.md                  # broader brief (Cowork handoff)
```

## 7. Résumé-bullet template (fill from §2 once routing GPU number exists)
> Built **KVGate**, an open-source OpenAI-compatible LLM gateway with multimodal
> KV/prefix-aware routing. Benchmarked on Llava-OneVision-7B: **LMCache CPU KV-offload cut
> TTFT ~2× and raised throughput up to 1.65×** under GPU memory pressure (extends my AWS
> KV-offload work). Designed prefix-aware routing that keeps per-image KV local across a
> replica fleet (validated at 99% routing-affinity hit rate).

## 8. Immediate next action
Routing GPU run is blocked on RunPod env stability — either retry on a stabler host using §4,
or **finalize now** (LMCache GPU win + routing-validated) and write the post/résumé + go public.
**STOP/terminate the running pod to halt billing when pausing.**
