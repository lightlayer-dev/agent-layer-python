"""Django middleware for agent traffic analytics.

Usage in settings.py::

    MIDDLEWARE = [
        "agent_layer.django.analytics.AgentAnalyticsMiddleware",
        # ...
    ]

    AGENT_LAYER_ANALYTICS = {
        "endpoint": "https://dash.lightlayer.dev/api/agent-events/",
        "api_key": "ll_your_key",
    }

Or programmatic::

    from agent_layer.django.analytics import get_analytics_instance
    analytics = get_analytics_instance()
    await analytics.flush()
"""

from __future__ import annotations

import time
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from agent_layer.analytics import AnalyticsConfig, AnalyticsInstance, build_agent_event, create_analytics

_instance: AnalyticsInstance | None = None


def get_analytics_instance() -> AnalyticsInstance:
    """Get or create the singleton analytics instance from Django settings."""
    global _instance  # noqa: PLW0603
    if _instance is None:
        raw: dict[str, Any] = getattr(settings, "AGENT_LAYER_ANALYTICS", {})
        config = AnalyticsConfig(**raw)
        _instance = create_analytics(config)
    return _instance


class AgentAnalyticsMiddleware:
    """Django middleware that detects AI agent traffic and collects analytics."""

    def __init__(self, get_response: object) -> None:
        self.get_response = get_response
        self.analytics = get_analytics_instance()

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        agent = self.analytics.detect(user_agent)
        config = self.analytics.config

        if not agent and not config.track_all:
            return self.get_response(request)

        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = (time.monotonic() - start) * 1000

        content_length = response.get("Content-Length")

        event = build_agent_event(
            agent=agent,
            user_agent=user_agent,
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            content_type=response.get("Content-Type"),
            response_size=int(content_length) if content_length else None,
        )
        self.analytics.record(event)

        return response
