#!/usr/bin/env python3
"""Render a Markdown comparison table from multiple benchmark JSON outputs.

Each input is a JSON file written by `loadtest/multimodal_bench.py --out`.
Use the filename (or a label:file pair) as the scenario name.

    python scripts/compare_results.py \
        A=baseline.json B=apc.json C=lmcache.json \
        D=fleet_rr.json E=fleet_kvaware.json
"""

from __future__ import annotations

import json
import sys
from typing import Dict, List, Tuple


def _load(arg: str) -> Tuple[str, dict]:
    label, _, path = arg.partition("=")
    if not path:
        label, path = arg, arg
    with open(path) as f:
        data = json.load(f)
    return label, data.get("summary", data)


def render(rows: List[Tuple[str, dict]]) -> str:
    header = (
        "| Scenario | TTFT p50 (ms) | TTFT p95 | TTFT p99 | Throughput (req/s) | "
        "Affinity hit % | OK/Total |"
    )
    sep = "|" + "|".join(["---"] * 6) + "|"
    lines = [header, sep]
    for label, s in rows:
        ttft = s.get("ttft_ms", {})
        hit = s.get("affinity_hit_rate")
        hit_str = f"{hit * 100:.1f}%" if isinstance(hit, (int, float)) else "—"
        lines.append(
            f"| {label} | {ttft.get('p50', '—')} | {ttft.get('p95', '—')} | "
            f"{ttft.get('p99', '—')} | {s.get('throughput_rps', '—')} | {hit_str} | "
            f"{s.get('succeeded', '—')}/{s.get('requests', '—')} |"
        )
    return "\n".join(lines)


def deltas(rows: Dict[str, dict]) -> str:
    """If both fleet scenarios (D, E) are present, report the headline deltas."""
    if "D" not in rows or "E" not in rows:
        return ""
    d, e = rows["D"], rows["E"]
    out = ["", "**Headline (D round-robin → E prefix_kv_aware):**"]
    dp95 = d.get("ttft_ms", {}).get("p95")
    ep95 = e.get("ttft_ms", {}).get("p95")
    if isinstance(dp95, (int, float)) and isinstance(ep95, (int, float)) and dp95:
        out.append(f"- TTFT p95: {dp95} ms → {ep95} ms ({(1 - ep95 / dp95) * 100:+.1f}%)")
    eh = e.get("affinity_hit_rate")
    if isinstance(eh, (int, float)):
        out.append(f"- Routing affinity hit rate (E): {eh * 100:.1f}%")
    return "\n".join(out)


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rows = [_load(a) for a in sys.argv[1:]]
    print(render(rows))
    print(deltas(dict(rows)))


if __name__ == "__main__":
    main()
