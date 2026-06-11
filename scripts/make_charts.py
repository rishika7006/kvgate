#!/usr/bin/env python3
"""Generate benchmark charts (PNG) from the raw result JSONs into docs/assets/.

Produces:
  docs/assets/routing_ttft.png   round_robin vs prefix_kv_aware (TTFT p50/p95/p99)
  docs/assets/lmcache_ttft.png   vLLM-only vs +LMCache (TTFT p50 and throughput)

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
GREY = "#9aa4b2"
BLUE = "#2563eb"
GREEN = "#16a34a"

plt.rcParams.update(
    {
        "font.size": 13,
        "axes.titlesize": 14,
        "axes.labelsize": 12,
        "xtick.labelsize": 12,
        "ytick.labelsize": 11,
        "legend.fontsize": 11,
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "axes.edgecolor": "#cbd5e1",
    }
)


def load(path: str) -> dict:
    with open(os.path.join(ROOT, path)) as f:
        d = json.load(f)
    return d.get("summary", d)


def _style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#e6e9ef", linewidth=1.0)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def _bars(ax, groups, series, fmt):
    n = len(series)
    width = 0.8 / n
    x = range(len(groups))
    for i, s in enumerate(series):
        offs = [xi + (i - (n - 1) / 2) * width for xi in x]
        bars = ax.bar(offs, s["values"], width, label=s["name"], color=s["color"], zorder=3)
        ax.bar_label(bars, fmt=fmt, padding=3, fontsize=11, color=INK, fontweight="medium")
    ax.set_xticks(list(x))
    ax.set_xticklabels(groups)
    ax.margins(y=0.18)


def routing_chart():
    d, e = load("results/routing/D.json"), load("results/routing/E.json")
    labels = ["p50", "p95", "p99"]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    _bars(
        ax,
        labels,
        [
            {
                "name": "round_robin (KV-blind)",
                "color": GREY,
                "values": [d["ttft_ms"][k] for k in labels],
            },
            {
                "name": "prefix_kv_aware",
                "color": GREEN,
                "values": [e["ttft_ms"][k] for k in labels],
            },
        ],
        "%.0f",
    )
    ax.set_ylabel("TTFT (ms, lower is better)")
    ax.set_title(
        "Prefix-aware routing vs round-robin on a 2-GPU fleet\n"
        "tail latency (p95) cut 1.84x, load balanced at 98.6% affinity",
        fontweight="medium",
    )
    ax.legend(frameon=False, loc="upper left")
    _style(ax)
    fig.tight_layout()
    out = os.path.join(ASSETS, "routing_ttft.png")
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", out)


def lmcache_chart():
    b1, c1 = load("results/Bp.json"), load("results/Cp.json")
    b2, c2 = load("results/Bp2.json"), load("results/Cp2.json")
    groups = ["KV cap 3072", "KV cap 2560"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    _bars(
        ax1,
        groups,
        [
            {
                "name": "vLLM cache only",
                "color": GREY,
                "values": [b1["ttft_ms"]["p50"], b2["ttft_ms"]["p50"]],
            },
            {
                "name": "+ LMCache (CPU offload)",
                "color": BLUE,
                "values": [c1["ttft_ms"]["p50"], c2["ttft_ms"]["p50"]],
            },
        ],
        "%.0f",
    )
    ax1.set_ylabel("TTFT p50 (ms, lower is better)")
    ax1.set_title("Time to first token", fontweight="medium")
    ax1.legend(frameon=False, loc="upper left")
    _style(ax1)

    _bars(
        ax2,
        groups,
        [
            {
                "name": "vLLM cache only",
                "color": GREY,
                "values": [b1["throughput_rps"], b2["throughput_rps"]],
            },
            {
                "name": "+ LMCache",
                "color": BLUE,
                "values": [c1["throughput_rps"], c2["throughput_rps"]],
            },
        ],
        "%.2f",
    )
    ax2.set_ylabel("Throughput (req/s, higher is better)")
    ax2.set_title("Throughput", fontweight="medium")
    ax2.legend(frameon=False, loc="upper left")
    _style(ax2)

    fig.suptitle(
        "LMCache CPU KV offload under GPU memory pressure (single A40, Llava-OneVision-7B)",
        fontsize=14,
        fontweight="medium",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = os.path.join(ASSETS, "lmcache_ttft.png")
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    routing_chart()
    lmcache_chart()
