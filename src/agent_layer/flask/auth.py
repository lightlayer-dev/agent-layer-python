"""Agent auth discovery routes for Flask."""

from __future__ import annotations

from flask import Blueprint, jsonify

from agent_layer.types import AgentAuthConfig


def agent_auth_blueprint(config: AgentAuthConfig) -> Blueprint:
    """Create a Flask blueprint exposing OAuth/auth discovery for agents."""
    bp = Blueprint("agent_auth", __name__)

    @bp.route("/.well-known/oauth-authorization-server")
    def oauth_metadata():
        metadata: dict = {}
        if config.issuer:
            metadata["issuer"] = config.issuer
        if config.authorization_url:
            metadata["authorization_endpoint"] = config.authorization_url
        if config.token_url:
            metadata["token_endpoint"] = config.token_url
        if config.scopes:
            metadata["scopes_supported"] = list(config.scopes.keys())
        return jsonify(metadata)

    return bp
