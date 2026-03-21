"""
Flask blueprint and middleware for agent-layer.

Provides a one-liner to install all agent-layer features on a Flask app:
    - agents.txt endpoint
    - llms.txt / llms-full.txt endpoints
    - /.well-known/ai discovery endpoint
    - /.well-known/agent.json A2A endpoint
    - Structured error handling
"""

from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, Flask, Response, jsonify, request

from agent_layer.core.a2a import A2AConfig, generate_agent_card
from agent_layer.core.agents_txt import AgentsTxtConfig, generate_agents_txt
from agent_layer.core.discovery import DiscoveryConfig, generate_ai_manifest, generate_json_ld
from agent_layer.core.errors import AgentError
from agent_layer.core.llms_txt import LlmsTxtConfig, generate_llms_txt, generate_llms_full_txt


class AgentLayer:
    """One-liner agent-layer integration for Flask.

    Usage:
        app = Flask(__name__)
        agent = AgentLayer(
            llms_txt=LlmsTxtConfig(title="My API"),
            discovery=DiscoveryConfig(manifest=AIManifest(name="My API")),
        )
        agent.install(app)
    """

    def __init__(
        self,
        *,
        agents_txt: AgentsTxtConfig | None = None,
        llms_txt: LlmsTxtConfig | None = None,
        discovery: DiscoveryConfig | None = None,
        a2a: A2AConfig | None = None,
        errors: bool = True,
    ) -> None:
        self.agents_txt = agents_txt
        self.llms_txt = llms_txt
        self.discovery = discovery
        self.a2a = a2a
        self.errors = errors

    def install(self, app: Flask) -> None:
        """Register all agent-layer routes and error handlers on the Flask app."""
        bp = Blueprint("agent_layer", __name__)

        # agents.txt
        if self.agents_txt:
            config = self.agents_txt

            @bp.route("/agents.txt")
            def agents_txt_route() -> Response:
                return Response(
                    generate_agents_txt(config),
                    mimetype="text/plain",
                )

        # llms.txt
        if self.llms_txt:
            config_llms = self.llms_txt

            @bp.route("/llms.txt")
            def llms_txt_route() -> Response:
                return Response(
                    generate_llms_txt(config_llms),
                    mimetype="text/plain",
                )

            @bp.route("/llms-full.txt")
            def llms_full_txt_route() -> Response:
                return Response(
                    generate_llms_full_txt(config_llms),
                    mimetype="text/plain",
                )

        # Discovery
        if self.discovery:
            config_disc = self.discovery

            @bp.route("/.well-known/ai")
            def well_known_ai_route() -> tuple[Response, int]:
                return jsonify(generate_ai_manifest(config_disc)), 200

            @bp.route("/.well-known/ai/json-ld")
            def json_ld_route() -> tuple[Response, int]:
                return jsonify(generate_json_ld(config_disc)), 200

        # A2A
        if self.a2a:
            config_a2a = self.a2a

            @bp.route("/.well-known/agent.json")
            def agent_card_route() -> tuple[Response, int]:
                return jsonify(generate_agent_card(config_a2a)), 200

        app.register_blueprint(bp)

        # Error handler
        if self.errors:

            @app.errorhandler(AgentError)
            def handle_agent_error(error: AgentError) -> tuple[Response, int]:
                return jsonify(error.to_json()), error.status
