#!/usr/bin/env bash
# KVGate x LMCache MP-mode: the FULL analysis (curve + repeats + persistence).
#
# Part 1  PRESSURE CURVE + REPEATS
#   Sweep the multimodal working set (distinct images = 8 / 24 / 48) across three
#   cache configs (baseline / L1=2GB / L1=2GB+Redis). Each config is replayed
#   cold (populate) then WARM x3 (repeats -> mean +/- spread, kills the "is it
#   noise?" objection). Per-tier MP metrics captured around the warm phase.
#
# Part 2  PERSISTENCE / REDEPLOY  (L2's unique value, no p50 caveat)
#   Populate the cache, then REDEPLOY: kill BOTH vLLM and the MP server (drops
#   GPU cache + CPU L1) while KEEPING Redis. Restart and run warm x3.
#     l1l2 : Redis L2 survives -> warm served from L2, fast, high hit rate.
#     l1_only : nothing persists -> warm = full recompute (cold), ~0 hit rate.
#
# Run on the pod from the repo root, INSIDE tmux so the servers survive an SSH drop:
#   tmux new -d -s sweep "bash benchmarks/lmcache_mp/run.sh > ~/mpout/sweep.log 2>&1"
# Results land in $OUT; pull them to results/lmcache_mp/ and render with make_charts.py.
set -uo pipefail

MODEL="${MODEL:-llava-hf/llava-onevision-qwen2-7b-ov-hf}"
VPORT="${VPORT:-18001}"; MP_PORT="${MP_PORT:-5555}"
METRICS_URL="${METRICS_URL:-http://127.0.0.1:8080/metrics}"
REDIS_PORT="${REDIS_PORT:-6379}"
OUT="${OUT:-$HOME/mpout/sweep}"; IMAGES_DIR="${IMAGES_DIR:-images}"
SESSIONS="${SESSIONS:-40}"; TURNS="${TURNS:-2}"; REVISIT="${REVISIT:-0.6}"
CONC="${CONC:-4}"; GPU_UTIL="${GPU_UTIL:-0.5}"; REPEATS="${REPEATS:-3}"
CURVE_IMAGES=(8 24 48)
PERSIST_IMAGES="${PERSIST_IMAGES:-24}"

mkdir -p "$OUT"
SCRAPE="python benchmarks/lmcache_mp/scrape_metrics.py"
export LMCACHE_DISABLE_BANNER=1 LMCACHE_MP_HOST=127.0.0.1 LMCACHE_MP_PORT="$MP_PORT"
log(){ echo "[$(date +%H:%M:%S)] $*"; }

kill_servers(){ pkill -f "vllm serve" 2>/dev/null; pkill -f "lmcache server" 2>/dev/null; sleep 5; }

wait_health(){ local url="$1" label="$2" to="${3:-600}" i=0
  until curl -fsS "$url" >/dev/null 2>&1; do sleep 3; i=$((i+3))
    if [ "$i" -ge "$to" ]; then log "TIMEOUT $label ($url)"; return 1; fi; done
  log "$label UP ~${i}s"; }

start_mp(){ # $1=l1_gb $2=with_l2(yes/no) $3=flush(yes/no)
  local l1="$1" l2="$2" flush="${3:-yes}" adapter=""
  [ "$flush" = "yes" ] && redis-cli -p "$REDIS_PORT" flushall >/dev/null 2>&1
  [ "$l2" = "yes" ] && adapter="--l2-adapter {\"type\":\"resp\",\"host\":\"127.0.0.1\",\"port\":$REDIS_PORT}"
  log "MP server L1=${l1}GB L2=${l2} flush=${flush}"
  # shellcheck disable=SC2086
  lmcache server --host 127.0.0.1 --port "$MP_PORT" --l1-size-gb "$l1" \
    --eviction-policy LRU $adapter --prometheus-port 9090 >"$OUT/mpserver.log" 2>&1 &
  wait_health "$METRICS_URL" "MP-metrics" 60; }

start_vllm(){ # $1=use_lmcache(yes/no)
  local use="$1" kvcfg=""
  [ "$use" = "yes" ] && kvcfg="--kv-transfer-config {\"kv_connector\":\"LMCacheMPConnector\",\"kv_role\":\"kv_both\"}"
  log "vLLM (lmcache=$use)"
  # shellcheck disable=SC2086
  vllm serve "$MODEL" --port "$VPORT" --enforce-eager --gpu-memory-utilization "$GPU_UTIL" \
    --max-model-len 16384 $kvcfg >"$OUT/vllm.log" 2>&1 &
  wait_health "http://localhost:$VPORT/health" "vLLM" 600; }

bench(){ # $1=images $2=outjson
  python loadtest/multimodal_bench.py --host "http://localhost:$VPORT" --model "$MODEL" \
    --images-dir "$IMAGES_DIR" --images "$1" --sessions "$SESSIONS" --turns "$TURNS" \
    --revisit-ratio "$REVISIT" --concurrency "$CONC" --context-tokens 0 --out "$2" >"${2%.json}.txt" 2>&1; }

# cold once, then warm REPEATS times, tier-delta around the whole warm phase.
cold_warm(){ # $1=tag $2=images $3=lmcache(yes/no)
  local tag="$1" n="$2" use="$3"
  log "$tag: COLD (images=$n)"; bench "$n" "$OUT/${tag}_cold.json"
  [ "$use" = "yes" ] && $SCRAPE "$OUT/${tag}_before.json" --metrics-url "$METRICS_URL" --label "${tag}_before" 2>/dev/null
  for r in $(seq 1 "$REPEATS"); do
    log "$tag: WARM r$r"; bench "$n" "$OUT/${tag}_warm${r}.json"
    grep -E "throughput|TTFT" "$OUT/${tag}_warm${r}.txt" | sed "s/^/  [$tag r$r] /" || true
  done
  if [ "$use" = "yes" ]; then
    $SCRAPE "$OUT/${tag}_after.json" --metrics-url "$METRICS_URL" --label "${tag}_after" 2>/dev/null
    $SCRAPE --diff "$OUT/${tag}_before.json" "$OUT/${tag}_after.json" > "$OUT/${tag}_tierdelta.json"
    log "$tag tierdelta:"; cat "$OUT/${tag}_tierdelta.json"
  fi; }

# preflight
log "preflight"
redis-server --daemonize yes --save "" --appendonly no 2>/dev/null
redis-cli -p "$REDIS_PORT" ping >/dev/null || { log "redis down"; exit 1; }
[ -d "$IMAGES_DIR" ] && [ "$(ls "$IMAGES_DIR" | wc -l)" -ge 48 ] || python scripts/gen_images.py 60
python -c "import vllm,lmcache,torch;print('versions',vllm.__version__,lmcache.__version__,torch.__version__,torch.version.cuda)"

# Part 1: pressure curve + repeats
for n in "${CURVE_IMAGES[@]}"; do
  kill_servers; start_vllm no || continue
  cold_warm "baseline_n${n}" "$n" no
done
for spec in "l1_only 2 no" "l1l2 2 yes"; do
  set -- $spec; mode="$1" l1="$2" l2="$3"
  for n in "${CURVE_IMAGES[@]}"; do
    kill_servers; start_mp "$l1" "$l2" yes || continue
    start_vllm yes || continue
    cold_warm "${mode}_n${n}" "$n" yes
  done
done

# Part 2: persistence / redeploy
for spec in "l1_only no" "l1l2 yes"; do
  set -- $spec; mode="$1" l2="$2"
  log "===== PERSISTENCE $mode ====="
  kill_servers; start_mp 2 "$l2" yes || continue; start_vllm yes || continue
  log "persist $mode: COLD populate (images=$PERSIST_IMAGES)"
  bench "$PERSIST_IMAGES" "$OUT/persist_${mode}_populate.json"
  $SCRAPE "$OUT/persist_${mode}_populated.json" --metrics-url "$METRICS_URL" --label "${mode}_populated" 2>/dev/null
  log "persist $mode: REDEPLOY (kill vLLM+MP, KEEP redis)"
  kill_servers
  start_mp 2 "$l2" no || continue          # NO flush -> Redis L2 persists
  start_vllm yes || continue
  $SCRAPE "$OUT/persist_${mode}_before.json" --metrics-url "$METRICS_URL" --label "${mode}_redeploy_before" 2>/dev/null
  for r in $(seq 1 "$REPEATS"); do
    log "persist $mode: WARM r$r (post-redeploy)"
    bench "$PERSIST_IMAGES" "$OUT/persist_${mode}_warm${r}.json"
    grep -E "throughput|TTFT" "$OUT/persist_${mode}_warm${r}.txt" | sed "s/^/  [persist $mode r$r] /" || true
  done
  $SCRAPE "$OUT/persist_${mode}_after.json" --metrics-url "$METRICS_URL" --label "${mode}_redeploy_after" 2>/dev/null
  $SCRAPE --diff "$OUT/persist_${mode}_before.json" "$OUT/persist_${mode}_after.json" > "$OUT/persist_${mode}_tierdelta.json"
  log "persist $mode redeploy tierdelta:"; cat "$OUT/persist_${mode}_tierdelta.json"
done

kill_servers
log "STRONG SWEEP DONE -> $OUT"
ls -1 "$OUT"/*_warm1.json 2>/dev/null