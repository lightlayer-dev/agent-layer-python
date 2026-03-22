"""Agent meta middleware for Flask — injects agent-friendly headers."""

from __future__ import annotations

from flask import Flask

from agent_layer.types import AgentMetaConfig


def agent_meta_middleware(app: Flask, config: AgentMetaConfig) -> None:
    """Add agent meta headers to all responses in a Flask app."""

    @app.after_request
    def _add_meta_headers(response):
        response.headers["X-Agent-Meta"] = "true"
        if config.agent_id_attribute:
            response.headers["X-Agent-Id-Attribute"] = config.agent_id_attribute
        return response
