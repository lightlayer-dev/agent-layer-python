"""Flask extension for agent traffic analytics.

Usage::

    from flask import Flask
    from agent_layer.flask.analytics import agent_analytics_middleware
    from agent_layer.analytics import AnalyticsConfig

    app = Flask(__name__)
    analytics = agent_analytics_middleware(app, AnalyticsConfig(
        endpoint="https://dash.lightlayer.dev/api/agent-events/",
        api_key="ll_your_key",
    ))
"""

from __future__ import annotations

import time

from flask import Flask, g, request

from agent_layer.analytics import AnalyticsConfig, AnalyticsInstance, build_agent_event, create_analytics


def agent_analytics_middleware(
    app: Flask,
    config: AnalyticsConfig | None = None,
) -> AnalyticsInstance:
    """Register agent analytics hooks on a Flask app.

    Returns the AnalyticsInstance for manual flush/shutdown.

    Note: Flask is synchronous, so events are buffered but remote flushing
    requires an async context (or a background thread). For sync-only apps,
    use the ``on_event`` callback to log events synchronously.
    """
    if config is None:
        config = AnalyticsConfig()

    instance = create_analytics(config)

    @app.before_request
    def _before() -> None:
        g._analytics_start = time.monotonic()

    @app.after_request
    def _after(response):  # type: ignore[no-untyped-def]
        user_agent = request.headers.get("User-Agent", "")
        agent = instance.detect(user_agent)

        if not agent and not config.track_all:
            return response

        start = getattr(g, "_analytics_start", None)
        duration_ms = (time.monotonic() - start) * 1000 if start else 0.0

        content_length = response.headers.get("Content-Length")

        event = build_agent_event(
            agent=agent,
            user_agent=user_agent,
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            content_type=response.content_type,
            response_size=int(content_length) if content_length else None,
        )
        instance.record(event)

        return response

    return instance
