"""Rate limiting middleware for Flask."""

from __future__ import annotations

import math

from flask import Flask, Response, g, jsonify, request

from agent_layer.async_utils import run_async_in_sync
from agent_layer.errors import rate_limit_error
from agent_layer.rate_limits import build_rate_limit_headers, create_rate_limiter
from agent_layer.types import RateLimitConfig


def rate_limits_middleware(app: Flask, config: RateLimitConfig) -> None:
    """Add rate limiting to a Flask app via before/after_request hooks."""
    check = create_rate_limiter(config)

    @app.before_request
    def check_rate_limit():
        result = run_async_in_sync(check(request))
        g.rate_limit_result = result

        if not result.allowed:
            retry_after = result.retry_after or math.ceil(result.reset_ms / 1000)
            envelope = rate_limit_error(retry_after)
            resp = jsonify({"error": envelope.model_dump(exclude_none=True)})
            resp.status_code = 429
            resp.headers["Retry-After"] = str(retry_after)
            for key, value in build_rate_limit_headers(result).items():
                resp.headers[key] = value
            return resp

    @app.after_request
    def add_rate_limit_headers(response: Response) -> Response:
        result = getattr(g, "rate_limit_result", None)
        if result:
            for key, value in build_rate_limit_headers(result).items():
                response.headers[key] = value
        return response
