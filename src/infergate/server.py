"""ASGI entrypoint.

Usage:
    uvicorn infergate.server:app
    INFERGATE_CONFIG=config/config.yaml uvicorn infergate.server:app
"""

from __future__ import annotations

from .app import create_app

app = create_app()
