"""Global API-key authentication.

When ``API_KEYS`` is configured, every ``/api`` route except the health probes
requires a matching ``X-API-Key`` header. When it is empty the gate is disabled
(local dev only) — deployments MUST set it, especially now that governance
approval genuinely applies (an unauthenticated approve could promote a signal).
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import get_settings

logger = logging.getLogger(__name__)

API_KEY_HEADER = "X-API-Key"
PUBLIC_PATHS = frozenset({"/api/health", "/api/health/ready"})

_api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


async def verify_api_key(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> None:
    keys = get_settings().api_key_set
    if not keys:
        return  # auth disabled (no keys configured) — dev / tests
    if request.url.path in PUBLIC_PATHS:
        return  # health probes stay public so load balancers can reach them
    if api_key is None or api_key not in keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key.",
        )
