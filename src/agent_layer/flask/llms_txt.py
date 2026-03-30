"""llms.txt blueprint for Flask."""

from __future__ import annotations

from flask import Blueprint, Response

from agent_layer.llms_txt import generate_llms_txt, generate_llms_full_txt
from agent_layer.types import LlmsTxtConfig, RouteMetadata


def llms_txt_blueprint(
    config: LlmsTxtConfig,
    routes: list[RouteMetadata] | None = None,
) -> Blueprint:
    """Create a Flask blueprint serving /llms.txt and optionally /llms-full.txt."""
    bp = Blueprint("llms_txt", __name__)

    @bp.route("/llms.txt")
    def llms_txt():
        return Response(generate_llms_txt(config), mimetype="text/plain")

    if routes is not None:

        @bp.route("/llms-full.txt")
        def llms_full_txt():
            return Response(generate_llms_full_txt(config, routes), mimetype="text/plain")

    return bp
