"""In-process per-client rate limiting middleware.

A sliding-window limiter keyed by client IP: a speed bump against abuse / accidental
request storms, NOT a distributed quota. State is per-process, so a multi-replica
deployment limits per replica — put a shared limiter at the ingress/gateway if you
need a global quota. Disabled when ``limit_per_minute <= 0`` (the default), so local
dev and the test suite are unaffected. Exempt paths (health probes) are never limited
so load balancers can always reach them.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

WINDOW_SECONDS = 60.0
_SWEEP_EVERY = 1024  # periodically drop idle clients so the map can't grow unbounded


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        limit_per_minute: int,
        exempt_paths: frozenset[str] = frozenset(),
    ) -> None:
        super().__init__(app)
        self._limit = limit_per_minute
        self._exempt = exempt_paths
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._since_sweep = 0

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if self._limit <= 0 or request.url.path in self._exempt:
            return await call_next(request)

        now = time.monotonic()
        cutoff = now - WINDOW_SECONDS
        self._maybe_sweep(cutoff)

        client = request.client.host if request.client else "unknown"
        hits = self._hits[client]
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= self._limit:
            retry_after = max(1, int(hits[0] + WINDOW_SECONDS - now) + 1)
            return JSONResponse(
                {"detail": "Rate limit exceeded. Slow down."},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)
        return await call_next(request)

    def _maybe_sweep(self, cutoff: float) -> None:
        self._since_sweep += 1
        if self._since_sweep < _SWEEP_EVERY:
            return
        self._since_sweep = 0
        idle = [client for client, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for client in idle:
            del self._hits[client]
