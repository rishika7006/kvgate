"""Multimodal KV/prefix-aware routing benchmark for InferGate.

Generates a deterministic multi-turn VQA / image-RAG workload: a pool of images,
each paired with a long shared system prompt, queried over multi-turn sessions
with a configurable image-revisit ratio (so the same image+prefix recurs and
creates cross-replica KV-reuse opportunities). Drives the requests through
InferGate and reports TTFT/throughput plus the gateway's routing-affinity hit
rate, so you can compare scenarios:

  Scenario D (baseline):  routing.strategy = round_robin     (KV-blind LB)
  Scenario E (headline):  routing.strategy = prefix_kv_aware

Runs against the mock fleet with no GPU for a dry run; point --host at a real
2-replica vLLM+LMCache deployment for the real numbers.

Examples
--------
    # Dry run against a locally-running mock gateway (infergate run):
    python loadtest/multimodal_bench.py --host http://localhost:8080 \
        --model demo --sessions 40 --turns 6 --concurrency 16 --out bench.json

    # Real benchmark (config/config.kvaware.example.yaml fleet):
    python loadtest/multimodal_bench.py --host http://localhost:8080 --model vlm \
        --images 50 --sessions 200 --turns 8 --concurrency 32
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import mimetypes
import os
import random
import re
import time
from typing import Any, Dict, List, Optional

import httpx

_SYSTEM_PROMPT = (
    "You are an expert visual-document analyst. Carefully examine the provided "
    "image and answer the user's questions precisely and concisely. Follow these "
    "rules at all times: cite only what is visible, never invent details, prefer "
    "exact figures over approximations, and when uncertain say so explicitly. "
) * 6  # ~1.5k+ tokens of shared prefix, the realistic long-system-prompt case

_QUESTIONS = [
    "What is the main subject of this image?",
    "List any text you can read in the image.",
    "What colors dominate the scene?",
    "Are there any people present, and what are they doing?",
    "Summarize the image in one sentence.",
    "What time of day does it appear to be?",
    "Describe the background in detail.",
    "What is unusual or notable about this image?",
]


def _synthetic_ref(image_id: int) -> str:
    # A placeholder reference used for GPU-free dry runs (the mock provider ignores
    # image content). Real vLLM would try to FETCH a URL, so for real runs pass
    # --images-dir to send actual images as base64 data URIs instead.
    return f"https://bench.infergate.local/images/img_{image_id:05d}.png"


def _data_uri(path: str) -> str:
    """Encode a local image file as an OpenAI-compatible base64 data URI."""
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def load_image_refs(images_dir: str, limit: int) -> List[str]:
    """Load up to `limit` real images from a directory as base64 data URIs."""
    exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
    files = sorted(
        os.path.join(images_dir, f)
        for f in os.listdir(images_dir)
        if os.path.splitext(f)[1].lower() in exts
    )
    if not files:
        raise SystemExit(f"No image files found in {images_dir}")
    return [_data_uri(p) for p in files[:limit]]


def build_trace(
    num_images: int = 50,
    sessions: int = 40,
    turns: int = 6,
    revisit_ratio: float = 0.7,
    seed: int = 1234,
    image_refs: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Build a deterministic list of request specs (each a chat payload body).

    Each session fixes one image and grows a multi-turn conversation (growing
    shared prefix). With probability `revisit_ratio` a session reuses an image
    already seen (inter-session reuse → cross-replica routing opportunity).
    """
    if image_refs:
        num_images = min(num_images, len(image_refs))
    rng = random.Random(seed)
    requests: List[Dict[str, Any]] = []
    seen: List[int] = []
    next_new = 0

    for s in range(sessions):
        if seen and rng.random() < revisit_ratio:
            image_id = rng.choice(seen)
        else:
            image_id = next_new % num_images
            next_new += 1
            if image_id not in seen:
                seen.append(image_id)

        img = image_refs[image_id % len(image_refs)] if image_refs else _synthetic_ref(image_id)
        history: List[Dict[str, Any]] = [{"role": "system", "content": _SYSTEM_PROMPT}]
        for t in range(turns):
            question = _QUESTIONS[t % len(_QUESTIONS)]
            user_turn = {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": img}},
                ],
            }
            # The request is the running history plus this turn's question.
            messages = history + [user_turn]
            requests.append(
                {
                    "session": s,
                    "image_id": image_id,
                    "turn": t,
                    "messages": messages,
                }
            )
            # Append a synthetic assistant answer to grow the prefix for next turn.
            history = messages + [
                {"role": "assistant", "content": f"Answer to turn {t} about image {image_id}."}
            ]

    return requests


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1)))))
    return s[k]


async def _one_request(
    client: httpx.AsyncClient, host: str, model: str, spec: Dict[str, Any]
) -> Dict[str, Any]:
    body = {
        "model": model,
        "stream": True,
        "messages": spec["messages"],
    }
    t0 = time.perf_counter()
    ttft: Optional[float] = None
    ok = False
    try:
        async with client.stream(
            "POST", f"{host}/v1/chat/completions", json=body, timeout=120.0
        ) as resp:
            if resp.status_code != 200:
                await resp.aread()
                return {"ok": False, "status": resp.status_code}
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                if ttft is None:
                    ttft = time.perf_counter() - t0
                if line.strip() == "data: [DONE]":
                    break
        ok = True
    except Exception as exc:  # pragma: no cover - network; benchmark client is best-effort
        return {"ok": False, "error": str(exc)}
    e2e = time.perf_counter() - t0
    return {"ok": ok, "ttft": ttft if ttft is not None else e2e, "e2e": e2e}


async def run_benchmark(
    host: str, model: str, trace: List[Dict[str, Any]], concurrency: int
) -> List[Dict[str, Any]]:
    host = host.rstrip("/")
    sem = asyncio.Semaphore(concurrency)
    results: List[Dict[str, Any]] = []

    async with httpx.AsyncClient() as client:

        async def worker(spec: Dict[str, Any]) -> None:
            async with sem:
                results.append(await _one_request(client, host, model, spec))

        wall0 = time.perf_counter()
        await asyncio.gather(*(worker(s) for s in trace))
        wall = time.perf_counter() - wall0

    results.append({"_wall": wall})
    return results


async def _scrape_affinity(host: str) -> Dict[str, float]:
    """Read the gateway's routing-affinity hit rate from /metrics."""
    out = {"warm": 0.0, "cold": 0.0}
    try:
        async with httpx.AsyncClient() as client:
            text = (await client.get(f"{host.rstrip('/')}/metrics", timeout=10.0)).text
    except httpx.HTTPError:  # pragma: no cover - network
        return out
    for outcome in ("warm", "cold"):
        m = re.search(
            r'infergate_routing_affinity_total\{[^}]*outcome="%s"[^}]*\}\s+([0-9.eE+]+)' % outcome,
            text,
        )
        if m:
            out[outcome] = float(m.group(1))
    return out


def summarize(results: List[Dict[str, Any]], affinity: Dict[str, float]) -> Dict[str, Any]:
    wall = next((r["_wall"] for r in results if "_wall" in r), 0.0)
    reqs = [r for r in results if "_wall" not in r]
    ok = [r for r in reqs if r.get("ok")]
    ttfts = [r["ttft"] * 1000 for r in ok]
    e2es = [r["e2e"] * 1000 for r in ok]
    total_aff = affinity["warm"] + affinity["cold"]
    return {
        "requests": len(reqs),
        "succeeded": len(ok),
        "failed": len(reqs) - len(ok),
        "wall_s": round(wall, 2),
        "throughput_rps": round(len(ok) / wall, 2) if wall > 0 else 0.0,
        "ttft_ms": {
            "p50": round(_percentile(ttfts, 50), 1),
            "p95": round(_percentile(ttfts, 95), 1),
            "p99": round(_percentile(ttfts, 99), 1),
        },
        "e2e_ms": {
            "p50": round(_percentile(e2es, 50), 1),
            "p95": round(_percentile(e2es, 95), 1),
        },
        "affinity_warm": int(affinity["warm"]),
        "affinity_cold": int(affinity["cold"]),
        "affinity_hit_rate": round(affinity["warm"] / total_aff, 4) if total_aff else None,
    }


def _print_summary(summary: Dict[str, Any]) -> None:
    print("\n===== InferGate multimodal benchmark =====")
    print(f"requests       : {summary['succeeded']}/{summary['requests']} ok "
          f"({summary['failed']} failed)")
    print(f"wall clock     : {summary['wall_s']}s")
    print(f"throughput     : {summary['throughput_rps']} req/s")
    print(f"TTFT  p50/p95/p99 (ms): "
          f"{summary['ttft_ms']['p50']} / {summary['ttft_ms']['p95']} / {summary['ttft_ms']['p99']}")
    print(f"E2E   p50/p95     (ms): {summary['e2e_ms']['p50']} / {summary['e2e_ms']['p95']}")
    if summary["affinity_hit_rate"] is not None:
        print(f"routing affinity: {summary['affinity_hit_rate'] * 100:.1f}% warm "
              f"(warm={summary['affinity_warm']}, cold={summary['affinity_cold']})")
    print("==========================================\n")


async def _amain(args: argparse.Namespace) -> None:
    image_refs = load_image_refs(args.images_dir, args.images) if args.images_dir else None
    trace = build_trace(
        num_images=args.images,
        sessions=args.sessions,
        turns=args.turns,
        revisit_ratio=args.revisit_ratio,
        seed=args.seed,
        image_refs=image_refs,
    )
    src = f"{len(image_refs)} real images from {args.images_dir}" if image_refs else \
        f"{args.images} synthetic image refs (dry-run only)"
    print(f"Generated {len(trace)} requests "
          f"({args.sessions} sessions x {args.turns} turns; {src}).")
    results = await run_benchmark(args.host, args.model, trace, args.concurrency)
    affinity = await _scrape_affinity(args.host)
    summary = summarize(results, affinity)
    _print_summary(summary)
    if args.out:
        with open(args.out, "w") as f:
            json.dump({"args": vars(args), "summary": summary}, f, indent=2)
        print(f"Wrote {args.out}")


def main() -> None:
    p = argparse.ArgumentParser(description="InferGate multimodal routing benchmark")
    p.add_argument("--host", default="http://localhost:8080")
    p.add_argument("--model", default="demo")
    p.add_argument("--images", type=int, default=50, help="Number of distinct images to use")
    p.add_argument("--images-dir", default=None, dest="images_dir",
                   help="Directory of REAL images (sent as base64). Required for real vLLM runs.")
    p.add_argument("--sessions", type=int, default=40)
    p.add_argument("--turns", type=int, default=6)
    p.add_argument("--revisit-ratio", type=float, default=0.7, dest="revisit_ratio")
    p.add_argument("--concurrency", type=int, default=16)
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--out", default=None, help="Write the JSON summary to this path")
    args = p.parse_args()
    asyncio.run(_amain(args))


if __name__ == "__main__":  # pragma: no cover
    main()
