"""One-liner to configure all agent-layer features on a Flask app."""

from __future__ import annotations

from flask import Flask

from agent_layer.types import AgentLayerConfig
from agent_layer.flask.errors import agent_errors_handler
from agent_layer.flask.rate_limits import rate_limits_middleware
from agent_layer.flask.llms_txt import llms_txt_blueprint
from agent_layer.flask.discovery import discovery_blueprint
from agent_layer.flask.auth import agent_auth_blueprint
from agent_layer.flask.meta import agent_meta_middleware
from agent_layer.flask.a2a import a2a_blueprint
from agent_layer.flask.robots_txt import robots_txt_routes
from agent_layer.flask.security_headers import security_headers_middleware


def configure_agent_layer(app: Flask, config: AgentLayerConfig) -> Flask:
    """One-liner: compose all agent-layer features onto a Flask app.

    Usage::

        from flask import Flask
        from agent_layer.flask import configure_agent_layer
        from agent_layer.types import AgentLayerConfig, RateLimitConfig, LlmsTxtConfig

        app = Flask(__name__)
        configure_agent_layer(app, AgentLayerConfig(
            rate_limit=RateLimitConfig(max=100),
            llms_txt=LlmsTxtConfig(title="My API"),
        ))
    """
    if config.errors:
        agent_errors_handler(app)

    if config.rate_limit:
        rate_limits_middleware(app, config.rate_limit)

    if config.agent_meta:
        agent_meta_middleware(app, config.agent_meta)

    if config.llms_txt:
        app.register_blueprint(llms_txt_blueprint(config.llms_txt))

    if config.discovery:
        app.register_blueprint(discovery_blueprint(config.discovery))

    if config.agent_auth:
        app.register_blueprint(agent_auth_blueprint(config.agent_auth))

    if config.a2a:
        app.register_blueprint(a2a_blueprint(config.a2a))

    if config.analytics:
        from agent_layer.analytics import AnalyticsConfig as _AC
        from agent_layer.flask.analytics import agent_analytics_middleware

        agent_analytics_middleware(app, _AC(**config.analytics.model_dump()))

    if config.security_headers:
        security_headers_middleware(app, config.security_headers)

    if config.robots_txt:
        app.register_blueprint(robots_txt_routes(config.robots_txt))

    return app
