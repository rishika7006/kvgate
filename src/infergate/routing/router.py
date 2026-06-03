"""Router — selects a deployment for a model and supports failover.

The router is backend-agnostic: it picks among the deployments configured for a
model using the active strategy, skips deployments whose circuit breaker is open,
and lets the request handler retry the next-best deployment when one fails.

The ``prefix_kv_aware`` strategy is request-aware: it routes to the replica that
already holds the longest warm prefix of the request (see ``affinity.py`` /
``keying.py``), balanced against current load, to maximize engine-side KV reuse.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Set

from ..config import Settings
from ..models import ChatCompletionRequest
from ..observability import metrics
from ..providers.base import Provider
from .affinity import PrefixAffinityIndex, build_affinity_index
from .keying import build_routing_key
from .state import DeploymentState
from .strategies import STRATEGIES


class NoDeploymentAvailable(Exception):
    pass


class Router:
    def __init__(self, settings: Settings, providers: Dict[str, Provider]):
        self.routing = settings.routing
        self.providers = providers
        self._models = settings.model_map()
        self._is_prefix_aware = self.routing.strategy == "prefix_kv_aware"
        self._strategy = None if self._is_prefix_aware else STRATEGIES[self.routing.strategy]
        self._states: Dict[str, Dict[str, DeploymentState]] = {}
        self._rr_counter: Dict[str, int] = {}

        # prefix_kv_aware machinery (built only when that strategy is active)
        self._affinity: Optional[PrefixAffinityIndex] = None
        if self._is_prefix_aware:
            self._pkv = self.routing.prefix_kv_aware
            self._affinity = build_affinity_index(self._pkv)
            self._cold_fallback = STRATEGIES[self._pkv.cold_fallback]

        for model_name, model_cfg in self._models.items():
            self._states[model_name] = {}
            for dep in model_cfg.deployments:
                state = DeploymentState(
                    dep,
                    ewma_alpha=self.routing.latency_ewma_alpha,
                    failure_threshold=self.routing.failure_threshold,
                    cooldown_s=self.routing.cooldown_s,
                )
                self._states[model_name][state.key] = state

    def known_models(self) -> List[str]:
        return list(self._models.keys())

    def has_model(self, model: str) -> bool:
        return model in self._states

    def states(self, model: str) -> List[DeploymentState]:
        return list(self._states.get(model, {}).values())

    def provider_for(self, state: DeploymentState) -> Provider:
        return self.providers[state.dep.provider]

    @property
    def affinity(self) -> Optional[PrefixAffinityIndex]:
        return self._affinity

    def _candidate_pool(self, model: str, exclude: Set[str]) -> List[DeploymentState]:
        all_states = self._states.get(model)
        if not all_states:
            raise NoDeploymentAvailable(f"no deployments configured for model '{model}'")
        candidates = [s for s in all_states.values() if s.key not in exclude]
        if not candidates:
            raise NoDeploymentAvailable(f"all deployments for '{model}' have been tried")
        now = time.monotonic()
        healthy = [s for s in candidates if s.is_available(now)]
        # If every circuit is open, allow a trial through the whole set.
        return healthy or candidates

    def pick(
        self,
        model: str,
        exclude: Optional[Set[str]] = None,
        request: Optional[ChatCompletionRequest] = None,
    ) -> DeploymentState:
        exclude = exclude or set()
        pool = self._candidate_pool(model, exclude)

        if self._is_prefix_aware:
            if request is not None:
                return self._pick_prefix_aware(model, pool, request)
            # prefix_kv_aware but no request (shouldn't happen via the service
            # path) -> degrade gracefully to the configured cold fallback.
            counter = self._rr_counter.get(model, 0)
            self._rr_counter[model] = counter + 1
            return self._cold_fallback(pool, counter)

        assert self._strategy is not None
        if self.routing.strategy == "round_robin":
            counter = self._rr_counter.get(model, 0)
            chosen = self._strategy(pool, counter)
            self._rr_counter[model] = counter + 1
            return chosen
        return self._strategy(pool, 0)

    def _pick_prefix_aware(
        self, model: str, pool: List[DeploymentState], request: ChatCompletionRequest
    ) -> DeploymentState:
        assert self._affinity is not None
        key = build_routing_key(
            request,
            block_size=self._pkv.block_size,
            image_key=self._pkv.image_key,
        )
        chain = key.block_hashes
        now = time.monotonic()

        best: Optional[DeploymentState] = None
        best_score = float("-inf")
        best_matched = 0
        for s in pool:
            matched = self._affinity.matched_blocks(s.key, chain, now)
            score = self._pkv.weight_prefix * matched - self._pkv.weight_load * s.in_flight
            if score > best_score:
                best, best_score, best_matched = s, score, matched

        # No warm prefix anywhere -> cold path: use the configured load/cost fallback.
        if best is None or best_matched == 0:
            chosen = self._cold_fallback(pool, self._rr_counter.get(model, 0))
            self._rr_counter[model] = self._rr_counter.get(model, 0) + 1
            metrics.ROUTING_AFFINITY_HITS.labels(model, "cold").inc()
            metrics.ROUTING_AFFINITY_MATCHED_BLOCKS.labels(model).observe(0)
        else:
            chosen = best
            metrics.ROUTING_AFFINITY_HITS.labels(model, "warm").inc()
            metrics.ROUTING_AFFINITY_MATCHED_BLOCKS.labels(model).observe(best_matched)

        # Register the full chain on the chosen replica: it will now have it warm.
        self._affinity.register(chosen.key, chain, now)
        return chosen
