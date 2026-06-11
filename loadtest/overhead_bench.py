#!/usr/bin/env python3
"""Measure KVGate's own request-handling overhead.

Fires many unique requests (cache-busting) at the gateway in front of a zero-latency
mock backend, so the measured latency is essentially the gateway's own work (auth,
routing decision, metrics, serialization) plus loopback HTTP. Reports added-latency
percentiles and sustained throughput.

    python loadtest/overhead_bench.py --host http://localhost:8085 --requests 4000 --concurrency 32
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time

import httpx


async def worker(client, host, model, idx, out):
    t0 = time.perf_counter()
    try:
        r = await client.post(
            f"{host}/v1/chat/completions",
            json={
                "model": model,
                "max_tokens": 1,
                # unique content per request so the response cache never hits
                "messages": [{"role": "user", "content": f"overhead probe {idx}"}],
            },
        )
        ok = r.status_code == 200
    except Exception:
        ok = False
    out.append((time.perf_counter() - t0, ok))


async def main_async(args):
    limits = httpx.Limits(
        max_connections=args.concurrency, max_keepalive_connections=args.concurrency
    )
    async with httpx.AsyncClient(timeout=30, limits=limits) as client:
        # warmup
        await worker(client, args.host, args.model, -1, [])
        results: list = []
        sem = asyncio.Semaphore(args.concurrency)

        async def guarded(i):
            async with sem:
                await worker(client, args.host, args.model, i, results)

        t_start = time.perf_counter()
        await asyncio.gather(*(guarded(i) for i in range(args.requests)))
        wall = time.perf_counter() - t_start

    lat = sorted(s * 1000 for s, ok in results if ok)
    n_ok = len(lat)
    failed = len(results) - n_ok

    def pct(p):
        return round(lat[min(len(lat) - 1, int(len(lat) * p))], 3) if lat else None

    summary = {
        "requests": args.requests,
        "succeeded": n_ok,
        "failed": failed,
        "concurrency": args.concurrency,
        "wall_s": round(wall, 3),
        "throughput_rps": round(n_ok / wall, 1) if wall else None,
        "overhead_ms": {
            "p50": pct(0.50),
            "p95": pct(0.95),
            "p99": pct(0.99),
            "mean": round(sum(lat) / n_ok, 3) if n_ok else None,
        },
    }
    print("\n===== KVGate gateway overhead (zero-latency mock backend) =====")
    print(f"requests   : {n_ok}/{args.requests} ok ({failed} failed)")
    print(f"concurrency: {args.concurrency}")
    print(f"throughput : {summary['throughput_rps']} req/s")
    o = summary["overhead_ms"]
    print(f"overhead   p50/p95/p99 (ms): {o['p50']} / {o['p95']} / {o['p99']}  (mean {o['mean']})")
    print("===============================================================")
    if args.out:
        with open(args.out, "w") as f:
            json.dump({"args": vars(args), "summary": summary}, f, indent=2)
        print(f"wrote {args.out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:8085")
    ap.add_argument("--model", default="demo")
    ap.add_argument("--requests", type=int, default=4000)
    ap.add_argument("--concurrency", type=int, default=32)
    ap.add_argument("--out", default=None)
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
