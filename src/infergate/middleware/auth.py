"""API-key authentication and tenant resolution.

When ``auth.enabled`` is false the gateway is open (great for local dev). When
enabled, the ``Authorization: Bearer <key>`` header is matched against configured
keys to resolve a tenant and an optional per-key rate limit.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel


class Principal(BaseModel):
    tenant: str = "anonymous"
    rpm: Optional[int] = None


async def get_principal(
    request: Request, authorization: Optional[str] = Header(default=None)
) -> Principal:
    settings = request.app.state.settings
    if not settings.auth.enabled:
        return Principal(tenant="anonymous", rpm=None)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")

    token = authorization.split(" ", 1)[1].strip()
    key_map = request.app.state.api_key_map
    entry = key_map.get(token)
    if entry is None:
        raise HTTPException(status_code=401, detail="Invalid API key.")
    return Principal(tenant=entry.tenant, rpm=entry.rpm)
