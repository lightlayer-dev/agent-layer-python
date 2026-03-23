"""FastAPI middleware for agent traffic analytics.

Usage::

    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from agent_layer.fastapi.analytics import agent_analytics_middleware

    analytics_instance = None

    @asynccontextmanager
    async def lifespan(app):
        nonlocal analytics_instance
        analytics_instance = agent_analytics_middleware(app)
        yield
        await analytics_instance.shutdown()

    app = FastAPI(lifespan=lifespan)
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from agent_layer.analytics import AnalyticsConfig, AnalyticsInstance, build_agent_event, create_analytics


def agent_analytics_middleware(
    app: object,
    config: AnalyticsConfig | None = None,
) -> AnalyticsInstance:
    """Add agent analytics middleware to a FastAPI/Starlette app.

    Returns the AnalyticsInstance so callers can manage its lifecycle
    via lifespan handlers. Call ``instance.buffer.start_flush_timer()``
    on startup and ``await instance.shutdown()`` on shutdown.

    For apps **without** a custom lifespan, the middleware registers
    lifespan hooks automatically. If the app already has a lifespan,
    manage the instance yourself (see module docstring).
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

            event = build_agent_event(
                agent=agent,
                user_agent=user_agent,
                method=request.method,
                path=str(request.url.path),
                status_code=response.status_code,
                duration_ms=duration_ms,
                content_type=response.headers.get("content-type"),
                response_size=int(content_length) if content_length else None,
            )
            instance.record(event)

            return response

    assert isinstance(app, FastAPI), "app must be a FastAPI instance"
    app.add_middleware(_AnalyticsMiddleware)

    # If the app has no custom lifespan, wrap the existing one to add
    # startup/shutdown hooks without using the deprecated on_event API.
    existing_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def _analytics_lifespan(app_: FastAPI) -> AsyncGenerator[dict, None]:  # type: ignore[type-arg]
        instance.buffer.start_flush_timer()
        if existing_lifespan is not None:
            async with existing_lifespan(app_) as state:
                yield state or {}
        else:
            yield {}
        await instance.shutdown()

    app.router.lifespan_context = _analytics_lifespan  # type: ignore[assignment]

    return instance
