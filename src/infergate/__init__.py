"""InferGate — an OpenAI-compatible LLM inference gateway."""

from __future__ import annotations

__version__ = "0.1.0"

from .app import create_app

__all__ = ["create_app", "__version__"]
