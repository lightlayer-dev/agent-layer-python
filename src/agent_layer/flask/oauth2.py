"""OAuth2/PKCE routes for Flask."""

from __future__ import annotations

from flask import Blueprint, jsonify

from agent_layer.oauth2 import OAuth2Config, build_oauth2_metadata


def oauth2_blueprint(config: OAuth2Config) -> Blueprint:
    """Create a Flask blueprint exposing OAuth2 metadata for agents."""
    bp = Blueprint("oauth2", __name__)

    @bp.route("/.well-known/oauth2-metadata")
    def oauth2_metadata():
        return jsonify(build_oauth2_metadata(config))

    return bp
