"""Router — selects a deployment for a model and supports failover.

The router is backend-agnostic: it picks among the deployments configured for a
model using the active strategy, skips deployments whose circuit breaker is open,
and lets the request handler retry the next-best deployment when one fails.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Set

from ..config import Settings
from ..providers.base import Provider
from .state import DeploymentState
from .strategies import STRATEGIES


class NoDeploymentAvailable(Exception):
    pass


class Router:
    def __init__(self, settings: Settings, providers: Dict[str, Provider]):
        self.routing = settings.routing
        self.providers = providers
        self._models = settings.model_map()
        self._strategy = STRATEGIES[self.routing.strategy]
        self._states: Dict[str, Dict[str, DeploymentState]] = {}
        self._rr_counter: Dict[str, int] = {}

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

    def pick(self, model: str, exclude: Optional[Set[str]] = None) -> DeploymentState:
        exclude = exclude or set()
        all_states = self._states.get(model)
        if not all_states:
            raise NoDeploymentAvailable(f"no deployments configured for model '{model}'")

        candidates = [s for s in all_states.values() if s.key not in exclude]
        if not candidates:
            raise NoDeploymentAvailable(f"all deployments for '{model}' have been tried")

        now = time.monotonic()
        healthy = [s for s in candidates if s.is_available(now)]
        # If every deployment's circuit is open, allow a trial request through the
        # whole set rather than failing hard.
        pool = healthy or candidates

        if self.routing.strategy == "round_robin":
            counter = self._rr_counter.get(model, 0)
            chosen = self._strategy(pool, counter)
            self._rr_counter[model] = counter + 1
        else:
            chosen = self._strategy(pool, 0)
        return chosen
