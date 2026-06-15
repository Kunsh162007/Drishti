"""In-memory token-bucket rate limiting middleware.

Keyed by authenticated subject when available, else client IP. For multi-instance
production, swap the in-memory buckets for Redis (the interface stays the same).
"""
from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, per_minute: int | None = None):
        super().__init__(app)
        self.capacity = per_minute or settings.RATE_LIMIT_PER_MIN
        self.refill_per_sec = self.capacity / 60.0
        self._buckets: dict[str, list[float]] = defaultdict(lambda: [self.capacity, time.monotonic()])

    def _key(self, request) -> str:
        auth = request.headers.get("authorization", "")
        if auth:
            return "tok:" + auth[-24:]
        client = request.client.host if request.client else "anon"
        return "ip:" + client

    async def dispatch(self, request, call_next):
        # Don't rate-limit health checks or static assets.
        if request.url.path in ("/health", "/api/health") or request.method == "OPTIONS":
            return await call_next(request)
        key = self._key(request)
        tokens, last = self._buckets[key]
        now = time.monotonic()
        tokens = min(self.capacity, tokens + (now - last) * self.refill_per_sec)
        if tokens < 1:
            self._buckets[key] = [tokens, now]
            return JSONResponse({"detail": "Rate limit exceeded. Slow down."}, status_code=429)
        self._buckets[key] = [tokens - 1, now]
        return await call_next(request)
