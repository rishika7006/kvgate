#!/usr/bin/env python3
"""Generate benchmark charts (PNG) from the raw result JSONs into docs/assets/.

Produces:
  docs/assets/routing_ttft.png   — D round_robin vs E prefix_kv_aware (TTFT p50/p95/p99)
  docs/assets/lmcache_ttft.png   — vLLM-only vs +LMCache TTFT p50 + throughput under
                                   GPU memory pressure (two KV-cap settings)

Run: python scripts/make_charts.py
"""
from __future__ import annotations

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "docs", "assets")
os.makedirs(ASSETS, exist_ok=True)

INK = "#0f172a"
GREY = "#94a3b8"
BLUE = "#3b82f6"
GREEN = "#10b981"


def load(path: str) -> dict:
    with open(os.path.join(ROOT, path)) as f:
        d = json.load(f)
    return d.get("summary", d)


def _style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#e2e8f0", linewidth=0.8)
    ax.set_axisbelow(True)


def routing_chart() -> None:
    d, e = load("results/routing/D.json"), load("results/routing/E.json")
    labels = ["p50", "p95", "p99"]
    dv = [d["ttft_ms"][k] for k in labels]
    ev = [e["ttft_ms"][k] for k in labels]
    x = range(len(labels))
    w = 0.38
    fig, ax = plt.subplots(figsize=(7, 4.2))
    b1 = ax.bar([i - w / 2 for i in x], dv, w, label="round_robin (KV-blind)", color=GREY)
    b2 = ax.bar([i + w / 2 for i in x], ev, w, label="prefix_kv_aware", color=GREEN)
    ax.bar_label(b1, fmt="%.0f", padding=2, fontsize=9, color=INK)
    ax.bar_label(b2, fmt="%.0f", padding=2, fontsize=9, color=INK)
    ax.set_ylabel("TTFT (ms) — lower is better")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_title(
        "Smart routing on a 2-GPU fleet (Llava-OneVision-7B)\n"
        "prefix_kv_aware cuts tail TTFT ~1.84x while keeping load balanced (98.6% affinity)",
        fontsize=10.5,
    )
    ax.legend(frameon=False, fontsize=9)
    _style(ax)
    fig.tight_layout()
    out = os.path.join(ASSETS, "routing_ttft.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print("wrote", out)


def lmcache_chart() -> None:
    b1, c1 = load("results/Bp.json"), load("results/Cp.json")   # 3072 blocks
    b2, c2 = load("results/Bp2.json"), load("results/Cp2.json")  # 2560 blocks
    groups = ["KV cap 3072", "KV cap 2560"]
    b_ttft = [b1["ttft_ms"]["p50"], b2["ttft_ms"]["p50"]]
    c_ttft = [c1["ttft_ms"]["p50"], c2["ttft_ms"]["p50"]]
    b_thr = [b1["throughput_rps"], b2["throughput_rps"]]
    c_thr = [c1["throughput_rps"], c2["throughput_rps"]]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2))
    x = range(len(groups))
    w = 0.38
    bb = ax1.bar([i - w / 2 for i in x], b_ttft, w, label="vLLM prefix cache only", color=GREY)
    cb = ax1.bar([i + w / 2 for i in x], c_ttft, w, label="+ LMCache (CPU KV offload)", color=BLUE)
    ax1.bar_label(bb, fmt="%.0f", padding=2, fontsize=9, color=INK)
    ax1.bar_label(cb, fmt="%.0f", padding=2, fontsize=9, color=INK)
    ax1.set_ylabel("TTFT p50 (ms) — lower is better")
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(groups)
    ax1.set_title("Time-to-first-token", fontsize=10.5)
    ax1.legend(frameon=False, fontsize=8.5)
    _style(ax1)

    bb2 = ax2.bar([i - w / 2 for i in x], b_thr, w, label="vLLM prefix cache only", color=GREY)
    cb2 = ax2.bar([i + w / 2 for i in x], c_thr, w, label="+ LMCache", color=BLUE)
    ax2.bar_label(bb2, fmt="%.2f", padding=2, fontsize=9, color=INK)
    ax2.bar_label(cb2, fmt="%.2f", padding=2, fontsize=9, color=INK)
    ax2.set_ylabel("Throughput (req/s) — higher is better")
    ax2.set_xticks(list(x))
    ax2.set_xticklabels(groups)
    ax2.set_title("Throughput", fontsize=10.5)
    ax2.legend(frameon=False, fontsize=8.5)
    _style(ax2)

    fig.suptitle(
        "LMCache multimodal KV offload under GPU memory pressure (single A40, Llava-OneVision-7B)",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out = os.path.join(ASSETS, "lmcache_ttft.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    routing_chart()
    lmcache_chart()
