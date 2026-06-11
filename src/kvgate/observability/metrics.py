"""Prometheus metrics.

Exposed at ``/metrics``. The Grafana dashboard in ``deploy/`` is wired to these
series: request rate, latency percentiles, cache hit rate, token throughput,
estimated cost, and per-deployment routing decisions.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

# A dedicated registry keeps test runs isolated and avoids duplicate-timeseries
# errors when the app is constructed more than once in a process.
REGISTRY = CollectorRegistry()

REQUESTS = Counter(
    "kvgate_requests_total",
    "Total chat completion requests.",
    ["model", "status", "stream"],
    registry=REGISTRY,
)

REQUEST_LATENCY = Histogram(
    "kvgate_request_latency_seconds",
    "End-to-end request latency (gateway perspective).",
    ["model"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

UPSTREAM_LATENCY = Histogram(
    "kvgate_upstream_latency_seconds",
    "Latency of the upstream provider call.",
    ["provider", "model"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

CACHE_EVENTS = Counter(
    "kvgate_cache_events_total",
    "Cache lookups by outcome.",
    ["outcome"],  # exact_hit | semantic_hit | miss
    registry=REGISTRY,
)

TOKENS = Counter(
    "kvgate_tokens_total",
    "Tokens processed.",
    ["model", "direction"],  # prompt | completion
    registry=REGISTRY,
)

COST = Counter(
    "kvgate_estimated_cost_usd_total",
    "Estimated upstream cost in USD.",
    ["model", "provider"],
    registry=REGISTRY,
)

ROUTING_DECISIONS = Counter(
    "kvgate_routing_decisions_total",
    "Deployment chosen per request.",
    ["model", "provider", "upstream_model"],
    registry=REGISTRY,
)

ROUTING_FAILOVERS = Counter(
    "kvgate_routing_failovers_total",
    "Retryable upstream failures that triggered failover.",
    ["model", "provider"],
    registry=REGISTRY,
)

ROUTING_AFFINITY_HITS = Counter(
    "kvgate_routing_affinity_total",
    "prefix_kv_aware routing decisions by affinity outcome.",
    ["model", "outcome"],  # warm | cold
    registry=REGISTRY,
)

ROUTING_AFFINITY_MATCHED_BLOCKS = Histogram(
    "kvgate_routing_affinity_matched_blocks",
    "Number of warm prefix blocks matched on the chosen replica.",
    ["model"],
    buckets=(0, 1, 2, 4, 8, 16, 32, 64, 128, 256),
    registry=REGISTRY,
)

RATE_LIMITED = Counter(
    "kvgate_rate_limited_total",
    "Requests rejected by the rate limiter.",
    ["tenant"],
    registry=REGISTRY,
)

INFLIGHT = Gauge(
    "kvgate_inflight_requests",
    "In-flight requests per deployment.",
    ["provider", "upstream_model"],
    registry=REGISTRY,
)


def record_cache(outcome: str) -> None:
    CACHE_EVENTS.labels(outcome=outcome).inc()
