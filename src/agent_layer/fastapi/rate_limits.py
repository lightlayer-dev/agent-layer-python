"""Rate limiting middleware for FastAPI."""

from __future__ import annotations

import math

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from agent_layer.errors import rate_limit_error
from agent_layer.rate_limits import build_rate_limit_headers, create_rate_limiter
from agent_layer.types import RateLimitConfig


class RateLimitsMiddleware(BaseHTTPMiddleware):
    """Adds X-RateLimit-* headers and returns 429 when exceeded."""

    def __init__(self, app, config: RateLimitConfig) -> None:
        super().__init__(app)
        self._check = create_rate_limiter(config)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        result = await self._check(request)

        response: Response
        if not result.allowed:
            retry_after = result.retry_after or math.ceil(result.reset_ms / 1000)
            envelope = rate_limit_error(retry_after)
            response = JSONResponse(
                status_code=429,
                content={"error": envelope.model_dump(exclude_none=True)},
            )
            response.headers["Retry-After"] = str(retry_after)
        else:
            response = await call_next(request)

        for key, value in build_rate_limit_headers(result).items():
            response.headers[key] = value

        return response


def rate_limits_middleware(app: FastAPI, config: RateLimitConfig) -> None:
    """Add rate limiting to a FastAPI app."""
    app.add_middleware(RateLimitsMiddleware, config=config)
