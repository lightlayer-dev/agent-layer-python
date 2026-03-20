"""A2A Agent Card blueprint for Flask."""

from __future__ import annotations

from flask import Blueprint, jsonify, make_response

from agent_layer.a2a import A2AConfig, generate_agent_card


def a2a_blueprint(config: A2AConfig) -> Blueprint:
    """Create a Flask blueprint serving /.well-known/agent.json."""
    bp = Blueprint("a2a", __name__)
    card = generate_agent_card(config)

    @bp.route("/.well-known/agent.json")
    def agent_card():
        response = make_response(jsonify(card))
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response

    return bp
