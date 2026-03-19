"""FastAPI middleware for agent traffic analytics.

Usage::

    from fastapi import FastAPI
    from agent_layer.fastapi.analytics import agent_analytics_middleware
    from agent_layer.analytics import AnalyticsConfig

    app = FastAPI()
    analytics = agent_analytics_middleware(app, AnalyticsConfig(
        endpoint="https://dash.lightlayer.dev/api/agent-events/",
        api_key="ll_your_key",
    ))
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from agent_layer.analytics import AgentEvent, AnalyticsConfig, AnalyticsInstance, create_analytics


def agent_analytics_middleware(
    app: object,
    config: AnalyticsConfig | None = None,
) -> AnalyticsInstance:
    """Add agent analytics middleware to a FastAPI/Starlette app.

    Returns the AnalyticsInstance for manual flush/shutdown.
    """
    from fastapi import FastAPI

    if config is None:
        config = AnalyticsConfig()

    instance = create_analytics(config)

    class _AnalyticsMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
            user_agent = request.headers.get("user-agent", "")
            agent = instance.detect(user_agent)

            if not agent and not config.track_all:
                return await call_next(request)

            start = time.monotonic()
            response = await call_next(request)
            duration_ms = (time.monotonic() - start) * 1000

            content_length = response.headers.get("content-length")

            event = AgentEvent(
                agent=agent or "unknown",
                user_agent=user_agent,
                method=request.method,
                path=str(request.url.path),
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
                timestamp=datetime.now(timezone.utc).isoformat(),
                content_type=response.headers.get("content-type"),
                response_size=int(content_length) if content_length else None,
            )
            instance.record(event)

            return response

    assert isinstance(app, FastAPI), "app must be a FastAPI instance"
    app.add_middleware(_AnalyticsMiddleware)

    # Start periodic flush on app startup
    @app.on_event("startup")  # type: ignore[union-attr]
    async def _start_flush() -> None:
        instance.buffer.start_flush_timer()

    @app.on_event("shutdown")  # type: ignore[union-attr]
    async def _shutdown_analytics() -> None:
        await instance.shutdown()

    return instance
