#!/usr/bin/env bash
# Regenerate docs/assets/dashboard.png — a live screenshot of the Next.js dashboard
# backed by a real (mock-fleet) gateway. No GPU needed.
#
# Notes / gotchas learned the hard way:
#   * The dashboard needs Node 18/20 (Next 14.2.5 hangs silently on Node 25).
#   * node_modules must be installed with the SAME Node major you run with (native
#     @next/swc ABI), else `next dev` hangs at "Starting...". Reinstall if you switch.
#   * Keep the dev server alive THROUGH the screenshot in one shell — backgrounding it
#     in a separate step can let process-group cleanup kill it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
PY="${PY:-python3}"

# 1) gateway (prefix_kv_aware, two mock replicas) + traffic
pkill -9 -f "kvgate run" 2>/dev/null || true; sleep 1
nohup kvgate run -c config/config.mock-kvaware.yaml --port 8080 >/tmp/ig_gw.log 2>&1 &
until curl -sf -m3 localhost:8080/readyz >/dev/null 2>&1; do sleep 1; done
"$PY" loadtest/multimodal_bench.py --host http://localhost:8080 --model demo \
  --sessions 90 --turns 3 --concurrency 6 --images 10 --seed 7 --out /tmp/dash.json >/dev/null 2>&1

# 2) dashboard dev server (kept alive until the screenshot)
pkill -9 -f "next dev" 2>/dev/null || true; sleep 1
( cd dashboard && exec node_modules/.bin/next dev -p 3000 ) >/tmp/nextlive.log 2>&1 &
NEXTPID=$!
until grep -q "Ready" /tmp/nextlive.log 2>/dev/null; do sleep 1; done
curl -s -m40 -o /dev/null localhost:3000   # trigger + finish first compile
sleep 2

# 3) headless screenshot -> docs/assets/dashboard.png
mkdir -p docs/assets; rm -f docs/assets/dashboard.png
"$CHROME" --headless=new --hide-scrollbars --disable-gpu --force-dark-mode \
  --window-size=1320,700 --virtual-time-budget=8000 \
  --screenshot="$ROOT/docs/assets/dashboard.png" "http://localhost:3000" >/dev/null 2>&1

kill -9 "$NEXTPID" 2>/dev/null || true; pkill -9 -f "next dev" 2>/dev/null || true
echo "wrote docs/assets/dashboard.png"
