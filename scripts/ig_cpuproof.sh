#!/bin/bash
# DIRECT evidence of WHERE the offloaded KV lives, on one GPU. Same multimodal workload,
# GPU KV capped, run across three LMCache configs (independent offload targets, not a forced chain):
#   control = vLLM prefix cache only (no offload)             -> CPU/Redis barely move
#   cpu     = LMCache -> CPU RAM        (local_cpu: true)     -> CPU RAM (free -m) rises by ~the KV
#   redis   = LMCache -> Redis DIRECT   (local_cpu: false)    -> Redis used_memory rises (cross-host KV)
# The "redis" config sets local_cpu:false, so there is NO persistent CPU cache tier — KV is
# stored straight to Redis (bytes only transit a transient host staging buffer, as any
# GPU->network copy must). Honest framing: redis is NOT a latency win over cpu (serde+network,
# and here Redis is on loopback so even that is optimistic); its value is capacity +
# cross-host/replica KV sharing -- the AWS-internship pattern. We show "where the KV lives", not a race.
# Captures per config: TTFT/throughput, CPU-RAM delta (free -m), Redis used_memory delta, and
# vLLM prefix-cache counters. All outputs -> /root/igout. Run via the launcher.
cd ~/infergate && source ~/venv/bin/activate
MODEL=llava-hf/llava-onevision-qwen2-7b-ov-hf
PORT=19001; W=/root/igout; BLOCKS=2560
IMAGES=40; SESSIONS=80; CONC=4
mkdir -p $W

pkill -9 -f "vllm serve" 2>/dev/null; pkill -9 -f EngineCore 2>/dev/null; sleep 3
fuser -k ${PORT}/tcp 2>/dev/null; sleep 2

# --- ensure a local Redis is up for the redis tier (best-effort install) ---
if ! command -v redis-server >/dev/null 2>&1; then
  echo "installing redis-server..."; apt-get update -qq 2>/dev/null && apt-get install -y -qq redis-server 2>/dev/null
fi
redis-server --daemonize yes --save "" --appendonly no 2>/dev/null
sleep 2
redis-cli ping 2>&1 | head -1

# LMCache configs: CPU-only vs remote-Redis
cat > $W/lmcache_cpu.yaml <<YAML
chunk_size: 256
local_cpu: true
max_local_cpu_size: 30
YAML
# redis tier: local_cpu:false => KV goes straight to Redis, no persistent CPU cache tier
cat > $W/lmcache_redis.yaml <<YAML
chunk_size: 256
local_cpu: false
remote_url: "redis://localhost:6379"
remote_serde: "naive"
YAML

KVCFG='--kv-transfer-config {"kv_connector":"LMCacheConnectorV1","kv_role":"kv_both"}'
wait_url(){ for i in $(seq 1 180); do curl -sf "$1" >/dev/null 2>&1 && return 0; sleep 2; done; return 1; }
free_mb(){ free -m | awk '/^Mem:/{print $3}'; }
redis_mb(){ redis-cli info memory 2>/dev/null | awk -F: '/used_memory:/{printf "%.0f", $2/1048576}'; }
metrics_hit(){ curl -s localhost:$PORT/metrics 2>/dev/null | grep -E 'prefix_cache' | grep -v '#' | tr '\n' ' '; }

run_one(){  # $1 label  $2 lmcache_cfg_or_empty
  echo "######## $1 ########"
  pkill -9 -f "vllm serve" 2>/dev/null; pkill -9 -f EngineCore 2>/dev/null; sleep 4
  fuser -k ${PORT}/tcp 2>/dev/null; sleep 2
  redis-cli flushall >/dev/null 2>&1
  local cpu_before=$(free_mb) redis_before=$(redis_mb)
  echo "$1 CPU_RAM_before_MB=$cpu_before REDIS_before_MB=$redis_before"
  local cfg_env=() flags=""
  if [ -n "$2" ]; then cfg_env=(LMCACHE_CONFIG_FILE="$2"); flags="$KVCFG"; fi
  # use `env` so VAR=val coming from variable/array expansion is treated as an assignment
  nohup env LMCACHE_LOG_LEVEL=DEBUG CUDA_VISIBLE_DEVICES=0 "${cfg_env[@]}" \
    vllm serve $MODEL --port $PORT --enforce-eager --gpu-memory-utilization 0.9 \
    --max-model-len 16384 --num-gpu-blocks-override $BLOCKS $flags > $W/$1.log 2>&1 &
  wait_url http://localhost:$PORT/health || { echo "!! $1 FAILED to start"; grep -iE 'error|address|memory|redis|lmcache' $W/$1.log | tail -10; return 1; }
  echo "$1 up."
  python loadtest/multimodal_bench.py --host http://localhost:$PORT --model $MODEL --images-dir images --images $IMAGES --sessions $SESSIONS --turns 1 --concurrency $CONC --seed 999 --out $W/${1}_warm.json >/dev/null 2>&1
  python loadtest/multimodal_bench.py --host http://localhost:$PORT --model $MODEL --images-dir images --images $IMAGES --sessions $SESSIONS --turns 1 --concurrency $CONC --out $W/${1}.json
  local cpu_after=$(free_mb) redis_after=$(redis_mb)
  echo "$1 CPU_RAM_after_MB=$cpu_after CPU_RAM_DELTA_MB=$((cpu_after-cpu_before))"
  echo "$1 REDIS_after_MB=$redis_after REDIS_DELTA_MB=$((redis_after-redis_before))"
  echo "$1 vllm_prefix_metrics: $(metrics_hit)"
  echo "$1 LMCache_loglines:"; grep -iE 'lmcache|offload|store|retriev|redis|remote' $W/$1.log | grep -iE 'store|retriev|cpu|offload|hit|miss|redis|remote' | tail -10
}

run_one control ""
run_one cpu   $W/lmcache_cpu.yaml
run_one redis $W/lmcache_redis.yaml

echo "######## SUMMARY (where does the KV live?) ########"
echo "Expect: cpu CPU_RAM_DELTA >> control (KV in CPU RAM); redis REDIS_DELTA > 0 (KV in Redis);"
echo "cpu TTFT < control TTFT under pressure. redis TTFT: loopback-optimistic — value is"
echo "capacity + cross-host sharing, not a latency win over cpu. Report numbers as measured."
python scripts/compare_results.py control=$W/control.json cpu=$W/cpu.json redis=$W/redis.json 2>&1
echo "ALLDONE_CPUPROOF"
