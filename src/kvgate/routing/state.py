"""Per-deployment runtime state: latency EWMA, in-flight load, circuit breaker."""

from __future__ import annotations

import time

from ..config import Deployment


def deployment_key(dep: Deployment) -> str:
    return f"{dep.provider}::{dep.model}"


class DeploymentState:
    def __init__(
        self, dep: Deployment, ewma_alpha: float, failure_threshold: int, cooldown_s: float
    ):
        self.dep = dep
        self.key = deployment_key(dep)
        self._alpha = ewma_alpha
        self._failure_threshold = failure_threshold
        self._cooldown_s = cooldown_s

        self.ewma_latency_ms: float = 0.0
        self.in_flight: int = 0
        self.consecutive_failures: int = 0
        self.total_requests: int = 0
        self.total_failures: int = 0
        self.ejected_until: float = 0.0

    def is_available(self, now: float) -> bool:
        return now >= self.ejected_until

    def on_start(self) -> None:
        self.in_flight += 1
        self.total_requests += 1

    def on_success(self, latency_ms: float) -> None:
        self.in_flight = max(0, self.in_flight - 1)
        self.consecutive_failures = 0
        if self.ewma_latency_ms == 0.0:
            self.ewma_latency_ms = latency_ms
        else:
            self.ewma_latency_ms = (
                self._alpha * latency_ms + (1 - self._alpha) * self.ewma_latency_ms
            )

    def on_failure(self) -> None:
        self.in_flight = max(0, self.in_flight - 1)
        self.consecutive_failures += 1
        self.total_failures += 1
        if self.consecutive_failures >= self._failure_threshold:
            # Open the circuit: eject this deployment for a cooldown window.
            self.ejected_until = time.monotonic() + self._cooldown_s

    @property
    def cost_per_1k(self) -> float:
        return self.dep.cost_per_1k_input + self.dep.cost_per_1k_output
