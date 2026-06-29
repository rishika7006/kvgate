#!/usr/bin/env python3
"""Snapshot LMCache MP per-tier metrics + Redis L2 size into a JSON file.

The MP server exposes Prometheus metrics on its HTTP frontend (default :8080).
We pull the counters that matter for an L1(CPU)/L2(Redis) tiering analysis:

  overall  lmcache_mp_lookup_requested_tokens_total / _hit_tokens_total
  L1 (CPU) l1_read_chunks_total (hits) / l1_write_chunks_total (stores)
           l1_memory_usage_bytes / l1_usage_ratio / l1_eviction_loop_ticks_total
  L2 (RDS) l2_prefetch_hit_chunks_total (hits) / l2_store_completed_objects_chunks_total
           l2_usage_bytes

Histograms (l0_l1_load/store_throughput, l2_store_throughput) are summarized as
sum/count -> mean GB/s.

Usage:  scrape_metrics.py OUT.json [--metrics-url URL] [--redis-host H] [--redis-port P] [--label L]
Diff two snapshots:  scrape_metrics.py --diff BEFORE.json AFTER.json
"""
import argparse
import json
import sys
import urllib.request

# Plain counters/gauges we read directly (value of the bare metric line).
COUNTERS = [
    "lmcache_mp_lookup_requested_tokens_total",
    "lmcache_mp_lookup_hit_tokens_total",
    "lmcache_mp_l1_read_chunks_total",
    "lmcache_mp_l1_write_chunks_total",
    "lmcache_mp_l1_memory_usage_bytes",
    "lmcache_mp_l1_usage_ratio",
    "lmcache_mp_l1_eviction_loop_ticks_total",
    "lmcache_mp_l2_prefetch_hit_chunks_total",
    "lmcache_mp_l2_prefetch_lookup_objects_chunks_total",
    "lmcache_mp_l2_store_completed_objects_chunks_total",
    "lmcache_mp_l2_usage_bytes",
    "lmcache_mp_num_chunks_loaded_total",
]
# Histograms -> we keep _sum and _count to derive a mean.
HISTS = [
    "lmcache_mp_l0_l1_load_throughput_GB_per_second",
    "lmcache_mp_l0_l1_store_throughput_GB_per_second",
    "lmcache_mp_l2_store_throughput_GB_per_second",
]


def _parse_prom(text):
    out = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        # "name{labels} value"  or  "name value"
        name, _, rest = line.partition(" ")
        if "{" in name:
            name = name[: name.index("{")]
        try:
            val = float(rest.strip())
        except ValueError:
            continue
        # Accumulate (sum across label sets, e.g. per-worker) so the snapshot is
        # connector-instance agnostic.
        out[name] = out.get(name, 0.0) + val
    return out


def snapshot(metrics_url, redis_host, redis_port, label):
    snap = {"label": label}
    try:
        with urllib.request.urlopen(metrics_url, timeout=10) as r:
            prom = _parse_prom(r.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        prom = {}
        snap["metrics_error"] = str(e)
    for c in COUNTERS:
        snap[c] = prom.get(c, 0.0)
    for h in HISTS:
        s = prom.get(h + "_sum", 0.0)
        n = prom.get(h + "_count", 0.0)
        snap[h + "_mean_GBps"] = round(s / n, 4) if n else 0.0
    # Redis used_memory (independent L2-size proof, no MP server needed).
    try:
        import socket

        with socket.create_connection((redis_host, redis_port), timeout=5) as s:
            s.sendall(b"INFO memory\r\n")
            data = b""
            while b"used_memory:" not in data or b"\r\n\r\n" not in data:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
        for ln in data.decode("utf-8", "replace").splitlines():
            if ln.startswith("used_memory:"):
                snap["redis_used_memory_bytes"] = int(ln.split(":", 1)[1])
                break
    except Exception as e:  # noqa: BLE001
        snap["redis_error"] = str(e)
    return snap


def _hit_rate(s):
    req = s.get("lmcache_mp_lookup_requested_tokens_total", 0.0)
    hit = s.get("lmcache_mp_lookup_hit_tokens_total", 0.0)
    return round(hit / req, 4) if req else None


def diff(before_path, after_path):
    with open(before_path) as f:
        b = json.load(f)
    with open(after_path) as f:
        a = json.load(f)
    d = {"label": a.get("label")}
    for k in COUNTERS:
        d["d_" + k] = a.get(k, 0.0) - b.get(k, 0.0)
    d["d_redis_used_memory_bytes"] = a.get("redis_used_memory_bytes", 0) - b.get(
        "redis_used_memory_bytes", 0
    )
    # Per-tier hit accounting over the interval.
    req = d["d_lmcache_mp_lookup_requested_tokens_total"]
    hit = d["d_lmcache_mp_lookup_hit_tokens_total"]
    d["interval_token_hit_rate"] = round(hit / req, 4) if req else None
    d["l1_read_chunks"] = d["d_lmcache_mp_l1_read_chunks_total"]
    d["l2_hit_chunks"] = d["d_lmcache_mp_l2_prefetch_hit_chunks_total"]
    d["l2_store_chunks"] = d["d_lmcache_mp_l2_store_completed_objects_chunks_total"]
    return d


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", nargs="?")
    p.add_argument("--metrics-url", default="http://127.0.0.1:8080/metrics")
    p.add_argument("--redis-host", default="127.0.0.1")
    p.add_argument("--redis-port", type=int, default=6379)
    p.add_argument("--label", default="")
    p.add_argument("--diff", nargs=2, metavar=("BEFORE", "AFTER"))
    args = p.parse_args()
    if args.diff:
        print(json.dumps(diff(*args.diff), indent=2))
        return
    snap = snapshot(args.metrics_url, args.redis_host, args.redis_port, args.label)
    snap["token_hit_rate"] = _hit_rate(snap)
    txt = json.dumps(snap, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(txt)
    print(txt, file=sys.stderr)


if __name__ == "__main__":
    main()
