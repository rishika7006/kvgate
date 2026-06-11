"""ASGI entrypoint.

Usage:
    uvicorn kvgate.server:app
    KVGATE_CONFIG=config/config.yaml uvicorn kvgate.server:app
"""

from __future__ import annotations

from .app import create_app

app = create_app()
