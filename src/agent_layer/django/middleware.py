"""
Django middleware for agent-layer.

Serves agent-layer endpoints as Django middleware:
    - /agents.txt
    - /llms.txt, /llms-full.txt
    - /.well-known/ai
    - /.well-known/agent.json
    - /mcp (JSON-RPC 2.0)
    - Unified discovery endpoints
    - OAuth2 metadata
    - Analytics, agent meta HTML transforms

Usage in settings.py:
    MIDDLEWARE = ['agent_layer.django.AgentLayerMiddleware', ...]
    AGENT_LAYER = {
        'agents_txt': AgentsTxtConfig(rules=[...]),
        'llms_txt': LlmsTxtConfig(title="My API"),
        'discovery': DiscoveryConfig(manifest=AIManifest(name="My API")),
        'a2a': A2AConfig(card=A2AAgentCard(name="My Agent", url="https://...")),
        'mcp': McpServerConfig(name="My API"),
        'analytics': AnalyticsConfig(),
        'agent_meta': AgentMetaConfig(meta_tags={"ai-purpose": "api"}),
    }
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

from agent_layer.core.a2a import A2AConfig, generate_agent_card
from agent_layer.core.agents_txt import AgentsTxtConfig, generate_agents_txt
from agent_layer.core.agent_meta import AgentMetaConfig, transform_html
from agent_layer.core.analytics import AnalyticsConfig, AgentEvent, create_analytics
from agent_layer.core.api_keys import ApiKeyConfig
from agent_layer.core.discovery import DiscoveryConfig, generate_ai_manifest, generate_json_ld
from agent_layer.core.errors import AgentError
from agent_layer.core.llms_txt import LlmsTxtConfig, generate_llms_txt, generate_llms_full_txt
from agent_layer.core.mcp import (
    McpServerConfig, generate_server_info, generate_tool_definitions, handle_json_rpc,
)
from agent_layer.core.oauth2 import OAuth2MiddlewareConfig, build_oauth2_metadata
from agent_layer.core.unified_discovery import UnifiedDiscoveryConfig, generate_all_discovery
from agent_layer.core.x402 import X402Config


class AgentLayerMiddleware:
    """Django middleware that serves agent-layer endpoints.

    Configure via the AGENT_LAYER setting in your Django settings module.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self._config: dict[str, Any] = getattr(settings, "AGENT_LAYER", {})

        # Pre-generate unified discovery docs if configured
        self._unified_docs: dict[str, str | dict[str, Any]] = {}
        ud_config = self._config.get("unified_discovery")
        if isinstance(ud_config, UnifiedDiscoveryConfig):
            self._unified_docs = generate_all_discovery(ud_config)

        # Set up MCP if configured
        self._mcp_server_info = None
        self._mcp_tools = []
        mcp_config = self._config.get("mcp")
        if isinstance(mcp_config, McpServerConfig):
            self._mcp_server_info = generate_server_info(mcp_config)
            auto_tools = generate_tool_definitions(mcp_config.routes or [])
            manual_tools = mcp_config.tools or []
            self._mcp_tools = auto_tools + manual_tools

        # Set up analytics if configured
        self._analytics = None
        analytics_config = self._config.get("analytics")
        if isinstance(analytics_config, AnalyticsConfig):
            self._analytics = create_analytics(analytics_config)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        path = request.path

        # agents.txt
        if path == "/agents.txt":
            config = self._config.get("agents_txt")
            if isinstance(config, AgentsTxtConfig):
                return HttpResponse(
                    generate_agents_txt(config),
                    content_type="text/plain",
                )

        # llms.txt
        if path == "/llms.txt":
            config = self._config.get("llms_txt")
            if isinstance(config, LlmsTxtConfig):
                return HttpResponse(
                    generate_llms_txt(config),
                    content_type="text/plain",
                )

        # llms-full.txt
        if path == "/llms-full.txt":
            config = self._config.get("llms_txt")
            if isinstance(config, LlmsTxtConfig):
                return HttpResponse(
                    generate_llms_full_txt(config),
                    content_type="text/plain",
                )

        # .well-known/ai
        if path == "/.well-known/ai":
            config = self._config.get("discovery")
            if isinstance(config, DiscoveryConfig):
                return JsonResponse(generate_ai_manifest(config))

        # .well-known/ai/json-ld
        if path == "/.well-known/ai/json-ld":
            config = self._config.get("discovery")
            if isinstance(config, DiscoveryConfig):
                return JsonResponse(generate_json_ld(config))

        # .well-known/agent.json
        if path == "/.well-known/agent.json":
            config = self._config.get("a2a")
            if isinstance(config, A2AConfig):
                return JsonResponse(generate_agent_card(config))

        # MCP server
        if path == "/mcp" and self._mcp_server_info:
            if request.method == "POST":
                try:
                    body = json.loads(request.body)
                except (json.JSONDecodeError, ValueError):
                    return JsonResponse(
                        {"jsonrpc": "2.0", "id": None,
                         "error": {"code": -32600, "message": "Invalid JSON-RPC request"}},
                        status=400,
                    )
                if body.get("jsonrpc") != "2.0":
                    return JsonResponse(
                        {"jsonrpc": "2.0", "id": None,
                         "error": {"code": -32600, "message": "Invalid JSON-RPC request"}},
                        status=400,
                    )
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(
                        handle_json_rpc(body, self._mcp_server_info, self._mcp_tools)
                    )
                finally:
                    loop.close()
                if result is None:
                    return HttpResponse(status=202)
                return JsonResponse(result)

            elif request.method == "GET":
                session_id = request.headers.get("mcp-session-id", str(uuid.uuid4()))
                response = HttpResponse("", content_type="text/event-stream")
                response["Cache-Control"] = "no-cache"
                response["Connection"] = "keep-alive"
                response["Mcp-Session-Id"] = session_id
                return response

            elif request.method == "DELETE":
                return JsonResponse({"ok": True})

        # Unified discovery endpoints
        if path in self._unified_docs:
            content = self._unified_docs[path]
            if isinstance(content, dict):
                return JsonResponse(content)
            return HttpResponse(content, content_type="text/plain")

        # OAuth2 metadata
        if path == "/.well-known/oauth-authorization-server":
            oauth2_config = self._config.get("oauth2")
            if isinstance(oauth2_config, OAuth2MiddlewareConfig):
                return JsonResponse(build_oauth2_metadata(
                    issuer=oauth2_config.oauth2.issuer or "",
                    authorization_endpoint=oauth2_config.oauth2.authorization_endpoint,
                    token_endpoint=oauth2_config.oauth2.token_endpoint,
                    scopes=oauth2_config.oauth2.scopes or None,
                ))

        # Pass through to next middleware / view
        start = time.time()
        try:
            response = self.get_response(request)
        except AgentError as e:
            return JsonResponse(e.to_json(), status=e.status)

        # Analytics
        if self._analytics:
            duration_ms = (time.time() - start) * 1000
            ua = request.META.get("HTTP_USER_AGENT", "")
            agent = self._analytics["detect"](ua)
            if agent or self._analytics["config"].track_all:
                event = AgentEvent(
                    agent=agent or "unknown",
                    user_agent=ua,
                    method=request.method,
                    path=request.path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    content_type=response.get("Content-Type", ""),
                )
                self._analytics["record"](event)

        # Agent meta — HTML transforms
        meta_config = self._config.get("agent_meta")
        if isinstance(meta_config, AgentMetaConfig):
            ct = response.get("Content-Type", "")
            if "text/html" in ct and hasattr(response, "content"):
                html = response.content.decode("utf-8")
                response.content = transform_html(html, meta_config).encode("utf-8")

        return response
