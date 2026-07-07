#!/usr/bin/env bash
# End-to-end GPU confirmation of KVGate's routing contribution.
#
# Two real vLLM + LMCache(MP) replicas of the SAME multimodal model, each with
# its OWN L1 (CPU) cache and a SHARED Redis L2, fronted by the KVGate gateway.
# We replay the SAME multimodal trace through the gateway under two routing
# strategies and compare TTFT / throughput / routing-affinity:
#
#   Scenario D (baseline):  routing.strategy = round_robin     (KV-blind LB)
#   Scenario E (headline):  routing.strategy = prefix_kv_aware (KVGate)
#
# Fairness: each scenario runs on a FRESH, FLUSHED fleet (Redis flushed + MP
# servers + vLLM restarted -> empty L1 + empty GPU cache), so the routing
# strategy is the ONLY independent variable. Per-replica L1 means routing to the
# warm replica yields an engine/L1 KV hit that round-robin would miss; the shared
# Redis L2 is the cross-replica safety net so even a routing miss can hit Redis.
#
# Run on the pod from the repo root, INSIDE tmux:
#   tmux new -d -s gpu2 "bash benchmarks/kvgate_routing/run_gpu_2replica.sh > ~/mpout/gpu2.log 2>&1"
set -uo pipefail

MODEL="${MODEL:-llava-hf/llava-onevision-qwen2-7b-ov-hf}"
GPU_UTIL="${GPU_UTIL:-0.40}"; MAXLEN="${MAXLEN:-16384}"
IMAGES_DIR="${IMAGES_DIR:-images}"; IMAGES="${IMAGES:-24}"
SESSIONS="${SESSIONS:-60}"; TURNS="${TURNS:-3}"; REVISIT="${REVISIT:-0.7}"; CONC="${CONC:-8}"
OUT="${OUT:-$HOME/mpout/gpu2}"; mkdir -p "$OUT"
log(){ echo "[$(date +%H:%M:%S)] $*"; }

export LMCACHE_DISABLE_BANNER=1

# NB: match "kvgate run" (the gateway), NOT bare "kvgate"; this script's own
# path contains "kvgate_routing" and a bare pattern would pkill the script itself.
# vLLM spawns a "VLLM::EngineCore" subprocess that holds the GPU and is NOT matched
# by "vllm serve"; kill it explicitly and WAIT for GPU memory to actually drain,
# else the next scenario's replicas OOM on a GPU still held by the previous fleet.
kill_all(){
  pkill -9 -if "vllm" 2>/dev/null; pkill -9 -f "EngineCore" 2>/dev/null
  pkill -9 -if "lmcache" 2>/dev/null; pkill -9 -f "kvgate run" 2>/dev/null
  for i in $(seq 1 20); do
    used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
    [ "${used:-9999}" -lt 1000 ] && break
    sleep 2
  done
  sleep 3; }

wait_health(){ local url="$1" label="$2" to="${3:-900}" i=0
  until curl -fsS "$url" >/dev/null 2>&1; do sleep 3; i=$((i+3))
    if [ "$i" -ge "$to" ]; then log "TIMEOUT $label ($url)"; return 1; fi; done
  log "$label UP ~${i}s"; }

start_mp(){ # $1=zmq_port $2=http_port $3=logtag
  log "MP server zmq=$1 http=$2 (L1=2GB + Redis L2)"
  lmcache server --host 127.0.0.1 --port "$1" --l1-size-gb 2 --eviction-policy LRU \
    --l2-adapter "{\"type\":\"resp\",\"host\":\"127.0.0.1\",\"port\":6379}" \
    --http-host 127.0.0.1 --http-port "$2" >"$OUT/mp_$3.log" 2>&1 &
  wait_health "http://127.0.0.1:$2/metrics" "MP-$3" 90; }

start_vllm(){ # $1=vport $2=mp_zmq_port $3=logtag
  log "vLLM :$1 -> MP :$2"
  LMCACHE_MP_HOST=127.0.0.1 LMCACHE_MP_PORT="$2" \
  vllm serve "$MODEL" --port "$1" --enforce-eager --gpu-memory-utilization "$GPU_UTIL" \
    --max-model-len "$MAXLEN" \
    --kv-transfer-config "{\"kv_connector\":\"LMCacheMPConnector\",\"kv_role\":\"kv_both\"}" \
    >"$OUT/vllm_$3.log" 2>&1 &
  wait_health "http://localhost:$1/health" "vLLM-$3" 900; }

start_gateway(){ # $1=strategy
  sed "s/^  strategy: .*/  strategy: $1/" config/gpu.runpod.yaml > "$OUT/gw_$1.yaml"
  log "gateway :8080 strategy=$1"
  kvgate run -c "$OUT/gw_$1.yaml" --port 8080 >"$OUT/gw_$1.log" 2>&1 &
  GW_PID=$!
  wait_health "http://localhost:8080/healthz" "gateway-$1" 60; }

bench(){ # $1=strategy
  log "BENCH strategy=$1 (images=$IMAGES sessions=$SESSIONS turns=$TURNS conc=$CONC)"
  python loadtest/multimodal_bench.py --host http://localhost:8080 --model vlm \
    --images-dir "$IMAGES_DIR" --images "$IMAGES" --sessions "$SESSIONS" --turns "$TURNS" \
    --revisit-ratio "$REVISIT" --concurrency "$CONC" --context-tokens 0 \
    --out "$OUT/scenario_$1.json" >"$OUT/scenario_$1.txt" 2>&1
  tail -30 "$OUT/scenario_$1.txt"; }

run_scenario(){ # $1=strategy: fresh flushed fleet, then bench
  log "===== SCENARIO $1 (fresh fleet) ====="
  kill_all
  redis-cli flushall >/dev/null
  start_mp 5555 18091 r1 || return 1
  start_mp 5556 18092 r2 || return 1
  start_vllm 18001 5555 r1 || { log "vLLM r1 failed (OOM?)"; nvidia-smi; return 1; }
  start_vllm 18002 5556 r2 || { log "vLLM r2 failed (OOM?)"; nvidia-smi; return 1; }
  log "fleet up:"; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
  start_gateway "$1" || return 1
  bench "$1"
  # capture gateway routing metrics + per-replica L2 metrics
  curl -fsS http://localhost:8080/metrics 2>/dev/null | grep -E "kvgate_routing_affinity" > "$OUT/gwmetrics_$1.txt" || true
  curl -fsS http://127.0.0.1:18091/metrics 2>/dev/null > "$OUT/mpmetrics_${1}_r1.txt" || true
  curl -fsS http://127.0.0.1:18092/metrics 2>/dev/null > "$OUT/mpmetrics_${1}_r2.txt" || true
  kill "$GW_PID" 2>/dev/null; sleep 3
}

# preflight
log "preflight"
redis-server --daemonize yes --save "" --appendonly no 2>/dev/null
redis-cli ping >/dev/null || { log "redis down"; exit 1; }
[ -d "$IMAGES_DIR" ] && [ "$(ls "$IMAGES_DIR" 2>/dev/null | wc -l)" -ge "$IMAGES" ] || python scripts/gen_images.py "$((IMAGES+8))"
python -c "import vllm,lmcache,torch;print('versions',vllm.__version__,lmcache.__version__,torch.__version__,torch.version.cuda)"

run_scenario round_robin     || { log "scenario D failed"; exit 1; }
run_scenario prefix_kv_aware || { log "scenario E failed"; exit 1; }

kill_all
log "DONE -> $OUT"; ls -1 "$OUT"/scenario_*.json
