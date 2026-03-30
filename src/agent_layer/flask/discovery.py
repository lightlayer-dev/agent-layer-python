"""Discovery blueprint for Flask."""

from __future__ import annotations

from flask import Blueprint, jsonify

from agent_layer.discovery import generate_ai_manifest, generate_json_ld
from agent_layer.types import DiscoveryConfig


def discovery_blueprint(config: DiscoveryConfig) -> Blueprint:
    """Create a Flask blueprint with /.well-known/ai and /json-ld."""
    bp = Blueprint("discovery", __name__)

    @bp.route("/.well-known/ai")
    def well_known_ai():
        return jsonify(generate_ai_manifest(config))

    @bp.route("/json-ld")
    def json_ld():
        return jsonify(generate_json_ld(config))

    if config.openapi_spec:

        @bp.route("/openapi.json")
        def openapi_spec():
            return jsonify(config.openapi_spec)

    return bp
