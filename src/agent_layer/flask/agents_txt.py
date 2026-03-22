"""agents.txt route handler and enforcement for Flask."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from agent_layer.agents_txt import AgentsTxtConfig, generate_agents_txt, is_agent_allowed


def agents_txt_routes(config: AgentsTxtConfig) -> Blueprint:
    """Create a Blueprint serving /agents.txt."""
    bp = Blueprint("agents_txt", __name__)
    content = generate_agents_txt(config)

    @bp.route("/agents.txt")
    def agents_txt():
        resp = Response(content, mimetype="text/plain; charset=utf-8")
        resp.headers["Cache-Control"] = "public, max-age=3600"
        return resp

    return bp


def agents_txt_enforce(config: AgentsTxtConfig):
    """Return a before_request handler that enforces agents.txt rules."""

    def before_request():
        if not config.enforce:
            return None

        user_agent = request.headers.get("User-Agent", "")
        path = request.path
        allowed = is_agent_allowed(config, user_agent, path)

        if allowed is False:
            return (
                jsonify(
                    error={
                        "type": "forbidden_error",
                        "code": "agent_denied",
                        "message": (
                            f'Access denied for agent "{user_agent}" on path "{path}". '
                            "See /agents.txt for access policy."
                        ),
                        "status": 403,
                        "is_retriable": False,
                        "docs_url": "/agents.txt",
                    }
                ),
                403,
            )
        return None

    return before_request
