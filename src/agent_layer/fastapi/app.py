"""One-liner to configure all agent-layer middleware on a FastAPI app."""

from __future__ import annotations

from fastapi import FastAPI

from agent_layer.types import AgentLayerConfig
from agent_layer.fastapi.errors import agent_errors_middleware
from agent_layer.fastapi.rate_limits import rate_limits_middleware
from agent_layer.fastapi.llms_txt import llms_txt_routes
from agent_layer.fastapi.discovery import discovery_routes
from agent_layer.fastapi.auth import agent_auth_routes
from agent_layer.fastapi.analytics import agent_analytics_middleware
from agent_layer.fastapi.meta import agent_meta_middleware
from agent_layer.fastapi.a2a import a2a_routes


def configure_agent_layer(app: FastAPI, config: AgentLayerConfig) -> FastAPI:
    """One-liner: compose all agent-layer features onto a FastAPI app.

    Each feature can be disabled by leaving it as None in the config.

    Usage::

        from fastapi import FastAPI
        from agent_layer.fastapi import configure_agent_layer
        from agent_layer.types import AgentLayerConfig, RateLimitConfig, LlmsTxtConfig

        app = FastAPI()
        configure_agent_layer(app, AgentLayerConfig(
            rate_limit=RateLimitConfig(max=100),
            llms_txt=LlmsTxtConfig(title="My API", description="Does things"),
        ))
    """
    # Middleware (order matters — errors should be outermost)
    if config.errors:
        agent_errors_middleware(app)

    if config.rate_limit:
        rate_limits_middleware(app, config.rate_limit)

    if config.agent_meta:
        agent_meta_middleware(app, config.agent_meta)

    # Routes
    if config.llms_txt:
        app.include_router(llms_txt_routes(config.llms_txt))

    if config.discovery:
        app.include_router(discovery_routes(config.discovery))

    if config.agent_auth:
        app.include_router(agent_auth_routes(config.agent_auth))

    if config.a2a:
        app.include_router(a2a_routes(config.a2a))

    if config.analytics:
        from agent_layer.analytics import AnalyticsConfig as _AC

        agent_analytics_middleware(app, _AC(**config.analytics.model_dump()))

    return app
