"""One-liner to configure all agent-layer features on a Flask app."""

from __future__ import annotations

from flask import Flask

from agent_layer.types import AgentLayerConfig
from agent_layer.flask.errors import agent_errors_handler
from agent_layer.flask.rate_limits import rate_limits_middleware
from agent_layer.flask.llms_txt import llms_txt_blueprint
from agent_layer.flask.discovery import discovery_blueprint


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

    if config.llms_txt:
        app.register_blueprint(llms_txt_blueprint(config.llms_txt))

    if config.discovery:
        app.register_blueprint(discovery_blueprint(config.discovery))

    return app
