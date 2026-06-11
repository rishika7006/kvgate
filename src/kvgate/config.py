"""Configuration models and loader for KVGate.

Config is layered: a YAML file provides the structure, and ``${ENV_VAR}`` /
``${ENV_VAR:-default}`` placeholders inside string values are expanded from the
environment at load time. This keeps secrets (API keys) out of the repo while
keeping the topology (providers, models, routing) in version control.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")


def _expand_env(value: Any) -> Any:
    """Recursively expand ``${VAR}`` / ``${VAR:-default}`` in strings."""
    if isinstance(value, str):

        def repl(match: re.Match[str]) -> str:
            var, default = match.group(1), match.group(2)
            return os.environ.get(var, default if default is not None else "")

        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    return value


class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"
    request_timeout_s: float = 60.0


class ApiKey(BaseModel):
    key: str
    tenant: str = "default"
    rpm: Optional[int] = None  # per-key override of the default rate limit
    budget_usd: Optional[float] = None  # per-key spend cap per window (overrides default)


class AuthSettings(BaseModel):
    enabled: bool = False
    api_keys: List[ApiKey] = Field(default_factory=list)


class BudgetSettings(BaseModel):
    """Per-tenant spend caps. When a tenant's spend in the current window exceeds its
    cap, further requests are rejected with HTTP 402 until the window resets."""

    enabled: bool = False
    default_usd: Optional[float] = None  # cap applied to tenants without a per-key cap
    window_s: int = 86400  # rolling window length (default: 1 day)


class SemanticCacheSettings(BaseModel):
    enabled: bool = True
    threshold: float = 0.95  # cosine similarity required for a semantic hit
    embedder: Literal["hashing", "sentence_transformers", "openai"] = "hashing"
    model: str = "all-MiniLM-L6-v2"
    max_entries: int = 2000


class CacheSettings(BaseModel):
    enabled: bool = True
    backend: Literal["memory", "redis"] = "memory"
    redis_url: str = "redis://localhost:6379/0"
    ttl_seconds: int = 3600
    semantic: SemanticCacheSettings = Field(default_factory=SemanticCacheSettings)


class RateLimitSettings(BaseModel):
    enabled: bool = True
    backend: Literal["memory", "redis"] = "memory"
    redis_url: str = "redis://localhost:6379/0"
    default_rpm: int = 600
    burst: int = 60


class PrefixKvAwareSettings(BaseModel):
    """Tuning for the `prefix_kv_aware` routing strategy."""

    block_size: int = 16
    affinity_backend: Literal["memory", "redis"] = "memory"
    # Redis URL for the shared (cross-gateway-replica) affinity index. Supports ${ENV}
    # expansion. Only used when affinity_backend == "redis".
    affinity_redis_url: str = "redis://localhost:6379/0"
    affinity_ttl_s: float = 300.0
    max_blocks_per_replica: int = 200_000
    weight_prefix: float = 1.0  # reward for each matched (warm) prefix block
    weight_load: float = 0.5  # penalty per in-flight request on a replica
    # Load guard: a replica may carry at most this many more in-flight requests
    # than the least-busy replica and still be eligible for prefix affinity. This
    # stops a shared (e.g. system-prompt) prefix from snowballing all traffic onto
    # one replica. Lower = more balanced; higher = more cache-reuse-greedy.
    max_inflight_skew: int = 8
    tokenizer: Literal["approx", "hf"] = "approx"
    hf_model: Optional[str] = None
    image_key: Literal["bytes_sha256", "url"] = "bytes_sha256"
    cold_fallback: Literal["round_robin", "weighted", "latency", "least_busy", "cost"] = (
        "least_busy"
    )


class RoutingSettings(BaseModel):
    strategy: Literal[
        "round_robin", "weighted", "latency", "least_busy", "cost", "prefix_kv_aware"
    ] = "latency"
    # EWMA smoothing factor for the latency strategy.
    latency_ewma_alpha: float = 0.3
    # Open the circuit after this many consecutive failures on a deployment.
    failure_threshold: int = 3
    # Seconds a deployment stays ejected before a trial request is allowed.
    cooldown_s: float = 15.0
    # Settings for the prefix_kv_aware strategy (used only when selected).
    prefix_kv_aware: PrefixKvAwareSettings = Field(default_factory=PrefixKvAwareSettings)


class ProviderConfig(BaseModel):
    name: str
    type: Literal["mock", "openai", "anthropic", "openai_compatible"]
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    # mock-only knobs
    latency_ms: int = 50
    tokens_per_second: float = 800.0
    extra: Dict[str, Any] = Field(default_factory=dict)


class Deployment(BaseModel):
    provider: str  # references ProviderConfig.name
    model: str  # the upstream model id sent to that provider
    weight: float = 1.0
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0


class ModelConfig(BaseModel):
    name: str  # the model id clients request, e.g. "demo" or "gpt-4o"
    deployments: List[Deployment]


class Settings(BaseModel):
    server: ServerSettings = Field(default_factory=ServerSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    ratelimit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    budget: BudgetSettings = Field(default_factory=BudgetSettings)
    routing: RoutingSettings = Field(default_factory=RoutingSettings)
    providers: List[ProviderConfig] = Field(default_factory=list)
    models: List[ModelConfig] = Field(default_factory=list)

    def provider_map(self) -> Dict[str, ProviderConfig]:
        return {p.name: p for p in self.providers}

    def model_map(self) -> Dict[str, ModelConfig]:
        return {m.name: m for m in self.models}


def load_settings(path: Optional[str] = None) -> Settings:
    """Load settings from a YAML file (env-expanded). Falls back to a built-in
    mock-only default when no path is given and no config file is found."""
    path = path or os.environ.get("KVGATE_CONFIG")
    if path:
        raw = yaml.safe_load(Path(path).read_text()) or {}
        return Settings.model_validate(_expand_env(raw))
    return default_settings()


def default_settings() -> Settings:
    """A zero-dependency, runs-out-of-the-box config using only mock providers."""
    return Settings.model_validate(
        {
            "providers": [
                {"name": "mock-fast", "type": "mock", "latency_ms": 40, "tokens_per_second": 1200},
                {"name": "mock-smart", "type": "mock", "latency_ms": 180, "tokens_per_second": 600},
            ],
            "models": [
                {
                    "name": "demo",
                    "deployments": [
                        {
                            "provider": "mock-fast",
                            "model": "mock-fast",
                            "weight": 2,
                            "cost_per_1k_input": 0.0005,
                            "cost_per_1k_output": 0.0015,
                        },
                        {
                            "provider": "mock-smart",
                            "model": "mock-smart",
                            "weight": 1,
                            "cost_per_1k_input": 0.003,
                            "cost_per_1k_output": 0.006,
                        },
                    ],
                }
            ],
        }
    )
