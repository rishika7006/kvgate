# KVGate Dashboard

A modern **Next.js (App Router) + TypeScript + Tailwind** live dashboard for the KVGate
gateway. It polls the gateway's `/admin/stats` and `/metrics` endpoints and visualizes:

- Routing strategy, cache backend, and rate-limit status
- Total requests, **cache hit rate**, **KV routing-affinity (warm) hit rate**, token throughput
- Per-replica table: in-flight, EWMA latency, request distribution, failures, circuit state

> The interesting bit for `prefix_kv_aware`: watch the **routing-affinity warm %** climb and the
> request bars stay **balanced** across replicas (thanks to the load guard).

## Run it

```bash
# 1. Start the gateway (in the repo root), e.g. the mock KV-aware fleet:
kvgate run -c config/config.mock-kvaware.yaml --port 8080

# 2. Start the dashboard:
cd dashboard
npm install
npm run dev          # http://localhost:3000

# 3. (optional) generate live traffic:
python ../loadtest/multimodal_bench.py --host http://localhost:8080 --model demo \
  --sessions 40 --turns 6 --concurrency 16
```

Point at a different gateway with `NEXT_PUBLIC_GATEWAY_URL`:

```bash
NEXT_PUBLIC_GATEWAY_URL=http://my-gateway:8080 npm run dev
```

## Build

```bash
npm run build && npm start
```

CORS is open on the gateway, so the browser can read `/admin/stats` and `/metrics` directly.
