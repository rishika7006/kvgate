from __future__ import annotations

from pathlib import Path

from infergate.config import default_settings, load_settings


def test_default_settings_runs_with_mock():
    s = default_settings()
    assert [p.name for p in s.providers] == ["mock-fast", "mock-smart"]
    assert s.model_map()["demo"].deployments


def test_env_expansion(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MY_KEY", "secret-123")
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        """
providers:
  - name: openai
    type: openai
    api_key: ${MY_KEY}
  - name: fallback
    type: mock
    base_url: ${MISSING:-http://default}
models:
  - name: demo
    deployments:
      - provider: fallback
        model: fallback
"""
    )
    s = load_settings(str(cfg))
    pmap = s.provider_map()
    assert pmap["openai"].api_key == "secret-123"
    assert pmap["fallback"].base_url == "http://default"


def test_example_config_is_valid():
    example = Path(__file__).resolve().parent.parent / "config" / "config.example.yaml"
    s = load_settings(str(example))
    assert "demo" in s.model_map()
    assert s.routing.strategy in {"round_robin", "weighted", "latency", "least_busy", "cost"}
