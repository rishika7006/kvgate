from __future__ import annotations

import sys
from pathlib import Path

# loadtest/ is not a package; add it to the path for import.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "loadtest"))

from multimodal_bench import build_trace, summarize  # noqa: E402


def test_trace_is_deterministic():
    a = build_trace(num_images=10, sessions=20, turns=4, seed=42)
    b = build_trace(num_images=10, sessions=20, turns=4, seed=42)
    assert [r["image_id"] for r in a] == [r["image_id"] for r in b]
    assert len(a) == 20 * 4


def test_each_request_has_system_and_image():
    trace = build_trace(num_images=5, sessions=10, turns=3, seed=1)
    for r in trace:
        assert r["messages"][0]["role"] == "system"
        # the final (current) user turn carries an image part
        last_user = r["messages"][-1]
        assert last_user["role"] == "user"
        assert any(part.get("type") == "image_url" for part in last_user["content"])


def test_multiturn_prefix_grows():
    trace = build_trace(num_images=1, sessions=1, turns=4, seed=7)
    lengths = [len(r["messages"]) for r in trace]
    # Each turn adds the prior (user, assistant) pair -> strictly growing prefix.
    assert lengths == sorted(lengths)
    assert lengths[0] < lengths[-1]


def test_revisit_ratio_drives_reuse():
    # High revisit ratio with few images -> far fewer distinct images than sessions.
    trace = build_trace(num_images=50, sessions=100, turns=1, revisit_ratio=0.9, seed=3)
    distinct = len({r["image_id"] for r in trace})
    assert distinct < 60  # heavy reuse, not 100 distinct


def test_summarize_computes_percentiles_and_hit_rate():
    results = [
        {"ok": True, "ttft": 0.010, "e2e": 0.100},
        {"ok": True, "ttft": 0.020, "e2e": 0.200},
        {"ok": False, "status": 500},
        {"_wall": 1.0},
    ]
    summary = summarize(results, {"warm": 7.0, "cold": 3.0})
    assert summary["requests"] == 3
    assert summary["succeeded"] == 2
    assert summary["failed"] == 1
    assert summary["ttft_ms"]["p50"] > 0
    assert summary["affinity_hit_rate"] == 0.7
