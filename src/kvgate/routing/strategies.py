"""Deployment-selection strategies.

Each strategy receives the list of currently-available DeploymentState objects
for a model and returns the one to use. Strategies are pure given their inputs
(the round-robin counter is supplied by the router) which keeps them testable.
"""

from __future__ import annotations

import random
from typing import List

from .state import DeploymentState


def round_robin(states: List[DeploymentState], counter: int) -> DeploymentState:
    return states[counter % len(states)]


def weighted(states: List[DeploymentState], counter: int) -> DeploymentState:
    weights = [max(0.0, s.dep.weight) for s in states]
    total = sum(weights)
    if total <= 0:
        return states[counter % len(states)]
    return random.choices(states, weights=weights, k=1)[0]


def least_latency(states: List[DeploymentState], counter: int) -> DeploymentState:
    # Unmeasured deployments (ewma 0) are treated as fastest to give them a try.
    return min(states, key=lambda s: s.ewma_latency_ms if s.ewma_latency_ms > 0 else -1.0)


def least_busy(states: List[DeploymentState], counter: int) -> DeploymentState:
    return min(states, key=lambda s: s.in_flight)


def cheapest(states: List[DeploymentState], counter: int) -> DeploymentState:
    return min(states, key=lambda s: s.cost_per_1k)


STRATEGIES = {
    "round_robin": round_robin,
    "weighted": weighted,
    "latency": least_latency,
    "least_busy": least_busy,
    "cost": cheapest,
}
