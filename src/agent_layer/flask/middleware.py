"""
Flask blueprint and middleware for agent-layer.

Provides a one-liner to install all agent-layer features on a Flask app:
    - agents.txt endpoint
    - llms.txt / llms-full.txt endpoints
    - /.well-known/ai discovery endpoint
    - /.well-known/agent.json A2A endpoint
    - Structured error handling
    - MCP server (JSON-RPC 2.0)
    - Analytics (agent detection)
    - API key validation
    - x402 payments
    - Agent identity verification
    - Unified discovery
    - AG-UI streaming
    - OAuth2 token validation
    - Agent meta (HTML transforms)
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, Flask, Response, jsonify, make_response, request

from agent_layer.core.a2a import A2AConfig, generate_agent_card
from agent_layer.core.agents_txt import AgentsTxtConfig, generate_agents_txt
from agent_layer.core.ag_ui import AG_UI_HEADERS
from agent_layer.core.agent_identity import AgentIdentityConfig
from agent_layer.core.agent_meta import AgentMetaConfig, transform_html
from agent_layer.core.analytics import AnalyticsConfig, AgentEvent, create_analytics
from agent_layer.core.api_keys import ApiKeyConfig
from agent_layer.core.discovery import DiscoveryConfig, generate_ai_manifest, generate_json_ld
from agent_layer.core.errors import AgentError
from agent_layer.core.llms_txt import LlmsTxtConfig, generate_llms_txt, generate_llms_full_txt
from agent_layer.core.mcp import (
    McpServerConfig, generate_server_info, generate_tool_definitions, handle_json_rpc,
)
from agent_layer.core.oauth2 import OAuth2MiddlewareConfig
from agent_layer.core.unified_discovery import UnifiedDiscoveryConfig, generate_all_discovery
from agent_layer.core.x402 import X402Config


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
        mcp: McpServerConfig | None = None,
        analytics: AnalyticsConfig | None = None,
        api_keys: ApiKeyConfig | None = None,
        x402: X402Config | None = None,
        agent_identity: AgentIdentityConfig | None = None,
        unified_discovery: UnifiedDiscoveryConfig | None = None,
        ag_ui: bool = False,
        oauth2: OAuth2MiddlewareConfig | None = None,
        agent_meta: AgentMetaConfig | None = None,
    ) -> None:
        self.agents_txt = agents_txt
        self.llms_txt = llms_txt
        self.discovery = discovery
        self.a2a = a2a
        self.errors = errors
        self.mcp = mcp
        self.analytics = analytics
        self.api_keys = api_keys
        self.x402 = x402
        self.agent_identity = agent_identity
        self.unified_discovery = unified_discovery
        self.ag_ui = ag_ui
        self.oauth2 = oauth2
        self.agent_meta = agent_meta

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

        # MCP server
        if self.mcp:
            mcp_config = self.mcp
            server_info = generate_server_info(mcp_config)
            auto_tools = generate_tool_definitions(mcp_config.routes or [])
            manual_tools = mcp_config.tools or []
            all_tools = auto_tools + manual_tools

            @bp.route("/mcp", methods=["POST"])
            def mcp_post() -> tuple[Response, int]:
                import asyncio
                body = request.get_json(silent=True)
                if not body or body.get("jsonrpc") != "2.0":
                    return jsonify({
                        "jsonrpc": "2.0", "id": None,
                        "error": {"code": -32600, "message": "Invalid JSON-RPC request"},
                    }), 400

                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(
                        handle_json_rpc(body, server_info, all_tools)
                    )
                finally:
                    loop.close()

                if result is None:
                    return Response(status=202)
                return jsonify(result), 200

            @bp.route("/mcp", methods=["GET"])
            def mcp_sse() -> Response:
                session_id = request.headers.get("mcp-session-id", str(uuid.uuid4()))
                resp = Response("", mimetype="text/event-stream")
                resp.headers["Cache-Control"] = "no-cache"
                resp.headers["Connection"] = "keep-alive"
                resp.headers["Mcp-Session-Id"] = session_id
                return resp

            @bp.route("/mcp", methods=["DELETE"])
            def mcp_delete() -> tuple[Response, int]:
                return jsonify({"ok": True}), 200

        # Unified discovery
        if self.unified_discovery:
            docs = generate_all_discovery(self.unified_discovery)
            for path, content in docs.items():
                if isinstance(content, dict):
                    _json_content = content
                    bp.add_url_rule(
                        path,
                        endpoint=f"unified_{path}",
                        view_func=lambda c=_json_content: (jsonify(c), 200),
                    )
                else:
                    _text_content = content
                    bp.add_url_rule(
                        path,
                        endpoint=f"unified_{path}",
                        view_func=lambda c=_text_content: Response(c, mimetype="text/plain"),
                    )

        # OAuth2 metadata
        if self.oauth2:
            oauth2_config = self.oauth2

            @bp.route("/.well-known/oauth-authorization-server")
            def oauth2_metadata() -> tuple[Response, int]:
                from agent_layer.core.oauth2 import build_oauth2_metadata
                return jsonify(build_oauth2_metadata(
                    issuer=oauth2_config.oauth2.issuer or "",
                    authorization_endpoint=oauth2_config.oauth2.authorization_endpoint,
                    token_endpoint=oauth2_config.oauth2.token_endpoint,
                    scopes=oauth2_config.oauth2.scopes or None,
                )), 200

        app.register_blueprint(bp)

        # Analytics — record events via after_request
        if self.analytics:
            analytics_inst = create_analytics(self.analytics)

            @app.after_request
            def record_analytics(response: Response) -> Response:
                ua = request.headers.get("user-agent", "")
                agent = analytics_inst["detect"](ua)
                if agent or analytics_inst["config"].track_all:
                    event = AgentEvent(
                        agent=agent or "unknown",
                        user_agent=ua,
                        method=request.method,
                        path=request.path,
                        status_code=response.status_code,
                        duration_ms=0,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        content_type=response.content_type,
                    )
                    analytics_inst["record"](event)
                return response

        # Agent meta — HTML transforms via after_request
        if self.agent_meta:
            meta_config = self.agent_meta

            @app.after_request
            def apply_agent_meta(response: Response) -> Response:
                ct = response.content_type or ""
                if "text/html" in ct and response.data:
                    html = response.data.decode("utf-8")
                    response.data = transform_html(html, meta_config).encode("utf-8")
                return response

        # Error handler
        if self.errors:

            @app.errorhandler(AgentError)
            def handle_agent_error(error: AgentError) -> tuple[Response, int]:
                return jsonify(error.to_json()), error.status
