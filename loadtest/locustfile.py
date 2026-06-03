"""Locust load test for InferGate.

Runs entirely against the mock providers, so you can benchmark routing, caching,
and rate limiting with zero upstream cost. A slice of requests intentionally
reuses prompts to exercise the cache; the rest are unique to exercise routing.

    locust -f loadtest/locustfile.py --host http://localhost:8080
    # headless 60s run, 50 users:
    locust -f loadtest/locustfile.py --host http://localhost:8080 \
        -u 50 -r 10 -t 60s --headless
"""

from __future__ import annotations

import random

from locust import HttpUser, between, task

# A small pool of shared prompts → high cache-hit probability.
HOT_PROMPTS = [
    "What is an LLM inference gateway?",
    "Explain semantic caching in one sentence.",
    "How does request routing reduce latency?",
    "Summarize the benefits of a model proxy.",
]


class GatewayUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def _payload(self, content: str, stream: bool = False) -> dict:
        return {
            "model": "demo",
            "stream": stream,
            "messages": [{"role": "user", "content": content}],
        }

    @task(6)
    def cached_request(self) -> None:
        """Reuse hot prompts → should mostly hit the cache."""
        self.client.post(
            "/v1/chat/completions",
            json=self._payload(random.choice(HOT_PROMPTS)),
            name="/v1/chat/completions [hot]",
        )

    @task(3)
    def unique_request(self) -> None:
        """Unique prompts → cache misses that exercise routing + failover."""
        nonce = random.randint(0, 1_000_000)
        self.client.post(
            "/v1/chat/completions",
            json=self._payload(f"Unique question #{nonce}: explain topic {nonce}."),
            name="/v1/chat/completions [unique]",
        )

    @task(1)
    def streaming_request(self) -> None:
        with self.client.post(
            "/v1/chat/completions",
            json=self._payload(random.choice(HOT_PROMPTS), stream=True),
            name="/v1/chat/completions [stream]",
            stream=True,
        ) as resp:
            for _ in resp.iter_lines():
                pass
