"""Unified multi-format discovery routes for Flask."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, make_response

from agent_layer.unified_discovery import (
    UnifiedDiscoveryConfig,
    generate_agents_txt,
    generate_unified_agent_card,
    generate_unified_ai_manifest,
    generate_unified_llms_full_txt,
    generate_unified_llms_txt,
)


def unified_discovery_blueprint(config: UnifiedDiscoveryConfig) -> Blueprint:
    """Create a Flask blueprint serving all enabled discovery formats.

    Example::

        from agent_layer.flask.unified_discovery import unified_discovery_blueprint
        from agent_layer.unified_discovery import UnifiedDiscoveryConfig

        config = UnifiedDiscoveryConfig(
            name="My API",
            description="REST API for widgets",
            url="https://api.example.com",
        )
        app.register_blueprint(unified_discovery_blueprint(config))
    """
    bp = Blueprint("unified_discovery", __name__)

    # Pre-generate all documents at startup
    ai_manifest = generate_unified_ai_manifest(config)
    agent_card_doc = generate_unified_agent_card(config)
    agents_txt_doc = generate_agents_txt(config)
    llms_txt_doc = generate_unified_llms_txt(config)
    llms_full_txt_doc = generate_unified_llms_full_txt(config)

    if config.formats.well_known_ai:

        @bp.route("/.well-known/ai")
        def well_known_ai():
            return jsonify(ai_manifest)

    if config.formats.agent_card:

        @bp.route("/.well-known/agent.json")
        def agent_card():
            response = make_response(jsonify(agent_card_doc))
            response.headers["Cache-Control"] = "public, max-age=3600"
            return response

    if config.formats.agents_txt:

        @bp.route("/agents.txt")
        def agents_txt():
            return Response(agents_txt_doc, mimetype="text/plain")

    if config.formats.llms_txt:

        @bp.route("/llms.txt")
        def llms_txt():
            return Response(llms_txt_doc, mimetype="text/plain")

        @bp.route("/llms-full.txt")
        def llms_full_txt():
            return Response(llms_full_txt_doc, mimetype="text/plain")

    return bp
