"""Rate limiting middleware for Flask."""

from __future__ import annotations

import asyncio
import math
import time

from flask import Flask, Response, g, jsonify, request

from agent_layer.errors import rate_limit_error
from agent_layer.rate_limit import create_rate_limiter
from agent_layer.types import RateLimitConfig


def rate_limits_middleware(app: Flask, config: RateLimitConfig) -> None:
    """Add rate limiting to a Flask app via before/after_request hooks."""
    check = create_rate_limiter(config)

    # Create a shared event loop for the sync Flask context
    _loop = asyncio.new_event_loop()

    @app.before_request
    def check_rate_limit():
        result = _loop.run_until_complete(check(request))
        g.rate_limit_result = result

        if not result.allowed:
            retry_after = result.retry_after or math.ceil(result.reset_ms / 1000)
            envelope = rate_limit_error(retry_after)
            resp = jsonify({"error": envelope.model_dump(exclude_none=True)})
            resp.status_code = 429
            resp.headers["Retry-After"] = str(retry_after)
            resp.headers["X-RateLimit-Limit"] = str(result.limit)
            resp.headers["X-RateLimit-Remaining"] = str(result.remaining)
            resp.headers["X-RateLimit-Reset"] = str(int(time.time()) + math.ceil(result.reset_ms / 1000))
            return resp

    @app.after_request
    def add_rate_limit_headers(response: Response) -> Response:
        result = getattr(g, "rate_limit_result", None)
        if result:
            response.headers["X-RateLimit-Limit"] = str(result.limit)
            response.headers["X-RateLimit-Remaining"] = str(result.remaining)
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + math.ceil(result.reset_ms / 1000))
        return response
