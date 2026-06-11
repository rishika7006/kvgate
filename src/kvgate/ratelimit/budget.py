"""Per-tenant spend caps (budgets).

Tracks cumulative estimated cost per tenant within a fixed window. When a tenant's
spend reaches its cap, ``check`` returns ``allowed=False`` and the API rejects further
requests with HTTP 402 until the window resets. In-memory only (single gateway replica);
a Redis-backed version would share budgets across replicas, mirroring the rate limiter.
"""

from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

from pydantic import BaseModel

from ..config import BudgetSettings


class BudgetDecision(BaseModel):
    allowed: bool
    spent_usd: float = 0.0
    cap_usd: Optional[float] = None
    remaining_usd: Optional[float] = None
    reset_in_s: float = 0.0


class BudgetTracker:
    def __init__(self, settings: BudgetSettings):
        self.settings = settings
        self.enabled = settings.enabled
        self.window_s = max(1, settings.window_s)
        # tenant -> (window_start_monotonic, spent_usd)
        self._state: Dict[str, Tuple[float, float]] = {}

    def _window(self, tenant: str) -> Tuple[float, float]:
        now = time.monotonic()
        start, spent = self._state.get(tenant, (now, 0.0))
        if now - start >= self.window_s:  # window expired -> reset
            start, spent = now, 0.0
            self._state[tenant] = (start, spent)
        return start, spent

    def check(self, tenant: str, cap_usd: Optional[float]) -> BudgetDecision:
        """Called before a request. cap_usd is the tenant's resolved cap (per-key
        override or the configured default); None means unlimited."""
        cap = cap_usd if cap_usd is not None else self.settings.default_usd
        if not self.enabled or cap is None:
            return BudgetDecision(allowed=True, cap_usd=cap)
        start, spent = self._window(tenant)
        reset_in = max(0.0, self.window_s - (time.monotonic() - start))
        if spent >= cap:
            return BudgetDecision(
                allowed=False, spent_usd=round(spent, 6), cap_usd=cap,
                remaining_usd=0.0, reset_in_s=round(reset_in, 1),
            )
        return BudgetDecision(
            allowed=True, spent_usd=round(spent, 6), cap_usd=cap,
            remaining_usd=round(cap - spent, 6), reset_in_s=round(reset_in, 1),
        )

    def record(self, tenant: str, cost_usd: float) -> float:
        """Called after a request completes. Adds cost to the tenant's window total
        and returns the new total."""
        if not self.enabled or cost_usd <= 0:
            start, spent = self._window(tenant)
            return spent
        start, spent = self._window(tenant)
        spent += cost_usd
        self._state[tenant] = (start, spent)
        return spent
