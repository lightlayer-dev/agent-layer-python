"""Rate limiting middleware for Django."""

from __future__ import annotations

import asyncio
import math
import time

from django.http import JsonResponse

from agent_layer.errors import rate_limit_error
from agent_layer.rate_limit import create_rate_limiter
from agent_layer.types import RateLimitConfig


class RateLimitsMiddleware:
    """Django middleware that adds X-RateLimit-* headers and returns 429 when exceeded.

    Configure in settings.py::

        AGENT_LAYER_RATE_LIMIT = {"max": 100, "window_ms": 60000}
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._loop = asyncio.new_event_loop()
        self._check = None

    def _get_check(self):
        if self._check is None:
            from django.conf import settings
            config_dict = getattr(settings, "AGENT_LAYER_RATE_LIMIT", {"max": 100})
            config = RateLimitConfig(**config_dict)
            self._check = create_rate_limiter(config)
        return self._check

    def __call__(self, request):
        check = self._get_check()
        result = self._loop.run_until_complete(check(request))

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

        response["X-RateLimit-Limit"] = str(result.limit)
        response["X-RateLimit-Remaining"] = str(result.remaining)
        reset_epoch = int(time.time()) + math.ceil(result.reset_ms / 1000)
        response["X-RateLimit-Reset"] = str(reset_epoch)

        return response
