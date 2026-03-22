"""Rate limiting middleware for Django."""

from __future__ import annotations

import math
from typing import Any

from django.http import JsonResponse

from agent_layer.async_utils import run_async_in_sync
from agent_layer.errors import rate_limit_error
from agent_layer.rate_limits import build_rate_limit_headers, create_rate_limiter
from agent_layer.types import RateLimitConfig


class RateLimitsMiddleware:
    """Django middleware that adds X-RateLimit-* headers and returns 429 when exceeded.

    Configure in settings.py::

        AGENT_LAYER_RATE_LIMIT = {"max": 100, "window_ms": 60000}
    """

    def __init__(self, get_response: object) -> None:
        self.get_response = get_response
        self._check: Any = None

    def _get_check(self) -> Any:
        if self._check is None:
            from django.conf import settings

            config_dict = getattr(settings, "AGENT_LAYER_RATE_LIMIT", {"max": 100})
            config = RateLimitConfig(**config_dict)
            self._check = create_rate_limiter(config)
        return self._check

    def __call__(self, request: Any) -> Any:
        check = self._get_check()
        result = run_async_in_sync(check(request))

        if not result.allowed:
            retry_after = result.retry_after or math.ceil(result.reset_ms / 1000)
            envelope = rate_limit_error(retry_after)
            response = JsonResponse(
                {"error": envelope.model_dump(exclude_none=True)},
                status=429,
            )
            response["Retry-After"] = str(retry_after)
        else:
            response = self.get_response(request)

        for key, value in build_rate_limit_headers(result).items():
            response[key] = value

        return response
