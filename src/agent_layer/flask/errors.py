"""Agent-friendly error handling for Flask."""

from __future__ import annotations

from flask import Flask, jsonify

from agent_layer.errors import AgentError, format_error
from agent_layer.types import AgentErrorOptions


def agent_errors_handler(app: Flask) -> None:
    """Register error handlers that return agent-friendly envelopes."""

    @app.errorhandler(AgentError)
    def handle_agent_error(e: AgentError):
        return jsonify(e.to_dict()), e.status

    @app.errorhandler(404)
    def handle_404(e):
        envelope = format_error(AgentErrorOptions(code="not_found", message=str(e), status=404))
        return jsonify({"error": envelope.model_dump(exclude_none=True)}), 404

    @app.errorhandler(500)
    def handle_500(e):
        envelope = format_error(
            AgentErrorOptions(
                code="internal_error", message="An unexpected error occurred.", status=500
            )
        )
        return jsonify({"error": envelope.model_dump(exclude_none=True)}), 500
