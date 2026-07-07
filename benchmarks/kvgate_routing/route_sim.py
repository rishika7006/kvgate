#!/usr/bin/env python3
"""Measure KVGate's routing quality, KV-blind vs KV-aware, with no GPU, no deps.

KVGate's headline feature is `prefix_kv_aware` routing: send each request to the
replica that already holds the longest warm prefix, so the engine reuses KV
instead of recomputing it. Whether that *decision* is good is independent of the
model, it depends only on request content. So we replay a realistic multimodal
trace through the routing decision and measure, per strategy and replica count:

  locality hit rate = fraction of requests routed to a replica that ALREADY holds
                      a matching prefix block (i.e. a future engine KV hit).

This mirrors KVGate's real routing internals (src/kvgate/routing/keying.py +
affinity.py): a request is hashed into a cumulative chain of prefix blocks, and a
replica "matches" the leading blocks it has already served. Kept dependency-free
(stdlib only) so it runs anywhere; the production path uses the same algorithm.

    python3 benchmarks/kvgate_routing/route_sim.py
"""
import hashlib
import json
import os
import random

BLOCK_SIZE = 16
REPLICAS = [2, 4, 8]
STRATEGIES = ["round_robin", "prefix_kv_aware"]


# trace: realistic multimodal traffic (mirrors loadtest/multimodal_bench)
def build_trace(num_images=40, sessions=200, turns=3, revisit_ratio=0.7, seed=1234):
    rng = random.Random(seed)
    reqs = []
    seen, next_new = [], 0
    for _ in range(sessions):
        if seen and rng.random() < revisit_ratio:
            image_id = rng.choice(seen)            # reuse an image -> cross-session KV reuse
        else:
            image_id = next_new % num_images
            next_new += 1
            if image_id not in seen:
                seen.append(image_id)
        history = ["role:system|you are a helpful multimodal assistant"]
        for t in range(turns):
            # each turn appends a question + the image, growing the shared prefix
            history.append(f"role:user|describe aspect {t}|img:{image_id}")
            reqs.append({"image_id": image_id, "units": list(history)})
            history.append(f"role:assistant|answer {t} about image {image_id}")
    return reqs


# keying: cumulative prefix-block hash chain (mirrors keying.build_routing_key)
def block_chain(units, block_size=BLOCK_SIZE, seed="kvgate"):
    # expand each unit into whitespace tokens, exactly as the real keyer tokenizes text
    toks = []
    for u in units:
        toks.extend(u.split())
    chain, prev = [], hashlib.sha256(seed.encode()).hexdigest()
    for i in range(0, len(toks), block_size):
        block = toks[i:i + block_size]
        prev = hashlib.sha256((prev + "\x1e" + "\x1f".join(block)).encode()).hexdigest()
        chain.append(prev)
    return chain


def matched_blocks(holds, chain):
    # longest leading run of the chain that this replica already holds
    n = 0
    for h in chain:
        if h in holds:
            n += 1
        else:
            break
    return n


def run(strategy, n_replicas, trace):
    holds = {r: set() for r in range(n_replicas)}   # replica -> block hashes it has served
    counter = 0
    warm = cold = matched_total = 0
    for spec in trace:
        chain = block_chain(spec["units"])
        if strategy == "round_robin":
            chosen = counter % n_replicas
            counter += 1
        else:  # prefix_kv_aware: pick replica with the longest matching prefix
            best, best_m = None, 0
            for r in range(n_replicas):
                m = matched_blocks(holds[r], chain)
                if m > best_m:
                    best, best_m = r, m
            if best is None:                         # no warm prefix anywhere -> round-robin
                chosen = counter % n_replicas
                counter += 1
            else:
                chosen = best
        m_at = matched_blocks(holds[chosen], chain)
        if m_at > 0:
            warm += 1
            matched_total += m_at
        else:
            cold += 1
        holds[chosen].update(chain)
    total = warm + cold
    return {
        "strategy": strategy, "replicas": n_replicas, "requests": total,
        "locality_hit_rate": round(warm / total, 4) if total else 0.0,
        "warm": warm, "cold": cold,
        "avg_matched_blocks_on_hit": round(matched_total / warm, 2) if warm else 0.0,
    }


def main():
    trace = build_trace()
    results = []
    print(f"trace: {len(trace)} requests\n")
    print(f"{'strategy':<18}{'replicas':<10}{'locality hit rate':<20}{'avg matched blocks'}")
    for n in REPLICAS:
        for strat in STRATEGIES:
            r = run(strat, n, trace)
            results.append(r)
            print(f"{r['strategy']:<18}{r['replicas']:<10}"
                  f"{r['locality_hit_rate'] * 100:>6.1f}%{'':<13}{r['avg_matched_blocks_on_hit']}")
    out = os.path.join(os.path.dirname(__file__), "..", "..", "results", "kvgate_routing")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "route_sim.json"), "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {os.path.normpath(out)}/route_sim.json")


if __name__ == "__main__":
    main()
