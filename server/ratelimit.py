"""Tiny fixed-window rate limiter per client IP (single instance, in memory)."""

from __future__ import annotations

import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, limit_per_min: int, prefix: str = "/api") -> None:
        super().__init__(app)
        self.limit = limit_per_min
        self.prefix = prefix
        self._windows: dict[str, tuple[float, int]] = {}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if self.limit <= 0 or not request.url.path.startswith(self.prefix):
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        start, count = self._windows.get(ip, (now, 0))
        if now - start >= 60:
            start, count = now, 0
        count += 1
        self._windows[ip] = (start, count)
        if count > self.limit:
            retry = max(1, int(60 - (now - start)))
            return JSONResponse(
                {"detail": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
        return await call_next(request)
