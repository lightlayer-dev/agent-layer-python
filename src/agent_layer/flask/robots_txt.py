"""Flask route handler for /robots.txt."""

from __future__ import annotations

from flask import Blueprint, Response

from agent_layer.robots_txt import RobotsTxtConfig, generate_robots_txt


def robots_txt_routes(config: RobotsTxtConfig | None = None) -> Blueprint:
    """Create a Flask Blueprint that serves GET /robots.txt."""
    content = generate_robots_txt(config)
    bp = Blueprint("robots_txt", __name__)

    @bp.route("/robots.txt")
    def robots_txt() -> Response:
        return Response(
            content,
            mimetype="text/plain; charset=utf-8",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    return bp
