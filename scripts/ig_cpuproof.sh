#!/bin/bash
# DIRECT proof that LMCache offloads KV to CPU memory. Single GPU.
# Runs the same multimodal workload twice with the GPU KV cache capped:
#   CONTROL = vLLM prefix cache only (no LMCache)  -> CPU RAM should barely move
#   LMCACHE = vLLM + LMCache CPU offload            -> CPU RAM should rise by ~the offloaded KV
# Captures: free -m before/after (CPU RAM delta), vLLM prefix-cache hit counters from /metrics,
# and LMCache store/retrieve log lines. All outputs to /root/igout. Run via the launcher.
cd ~/infergate && source ~/venv/bin/activate
MODEL=llava-hf/llava-onevision-qwen2-7b-ov-hf
PORT=19001; W=/root/igout; BLOCKS=2560
IMAGES=40; SESSIONS=80; CONC=4
mkdir -p $W

# free ports (avoid RunPod nginx on 8001) + kill orphans
pkill -9 -f "vllm serve" 2>/dev/null; pkill -9 -f EngineCore 2>/dev/null; sleep 3
fuser -k ${PORT}/tcp 2>/dev/null; sleep 2

cat > $W/lmcache.yaml <<YAML
chunk_size: 256
local_cpu: true
max_local_cpu_size: 30
YAML

wait_url(){ for i in $(seq 1 180); do curl -sf "$1" >/dev/null 2>&1 && return 0; sleep 2; done; return 1; }
free_mb(){ free -m | awk '/^Mem:/{print $3}'; }   # used MB
metrics_hit(){ curl -s localhost:$PORT/metrics 2>/dev/null | grep -E 'gpu_prefix_cache_(hits|queries)|prefix_cache' | grep -v '#' | tr '\n' ' '; }

run_one(){  # $1 label  $2 extra_vllm_flags
  echo "######## $1 ########"
  pkill -9 -f "vllm serve" 2>/dev/null; pkill -9 -f EngineCore 2>/dev/null; sleep 4
  fuser -k ${PORT}/tcp 2>/dev/null; sleep 2
  sync; echo 3 > /proc/sys/vm/drop_caches 2>/dev/null   # best-effort; ignore if not permitted
  local before=$(free_mb)
  echo "$1 CPU_RAM_used_before_MB=$before"
  LMCACHE_LOG_LEVEL=DEBUG CUDA_VISIBLE_DEVICES=0 LMCACHE_CONFIG_FILE=$W/lmcache.yaml \
    nohup vllm serve $MODEL --port $PORT --enforce-eager --gpu-memory-utilization 0.9 \
    --max-model-len 16384 --num-gpu-blocks-override $BLOCKS $2 > $W/$1.log 2>&1 &
  wait_url http://localhost:$PORT/health || { echo "!! $1 FAILED to start"; grep -iE 'error|address|memory' $W/$1.log | tail -8; return 1; }
  echo "$1 up. baseline CPU after model load: $(free_mb) MB"
  # warmup (fills CPU cache for the LMCache run) + measured run
  python loadtest/multimodal_bench.py --host http://localhost:$PORT --model $MODEL --images-dir images --images $IMAGES --sessions $SESSIONS --turns 1 --concurrency $CONC --seed 999 --out $W/${1}_warm.json >/dev/null 2>&1
  local mid=$(free_mb)
  python loadtest/multimodal_bench.py --host http://localhost:$PORT --model $MODEL --images-dir images --images $IMAGES --sessions $SESSIONS --turns 1 --concurrency $CONC --out $W/${1}.json
  local after=$(free_mb)
  echo "$1 CPU_RAM_used_after_MB=$after"
  echo "$1 CPU_RAM_DELTA_MB=$((after-before))  (after-warmup snapshot=$mid)"
  echo "$1 vllm_prefix_metrics: $(metrics_hit)"
  echo "$1 LMCache_store_retrieve_loglines:"; grep -iE 'lmcache|offload|cpu|store|retriev' $W/$1.log | grep -iE 'store|retriev|cpu|offload|hit|miss' | tail -8
}

run_one control ""
run_one lmcache "--kv-transfer-config {\"kv_connector\":\"LMCacheConnectorV1\",\"kv_role\":\"kv_both\"}"

echo "######## SUMMARY ########"
echo "If LMCache offloads to CPU, lmcache CPU_RAM_DELTA_MB >> control CPU_RAM_DELTA_MB,"
echo "and lmcache TTFT < control TTFT. Compare the two .json:"
python scripts/compare_results.py control=$W/control.json lmcache=$W/lmcache.json 2>&1
echo "ALLDONE_CPUPROOF"
