"""
Django middleware for agent-layer.

Serves agent-layer endpoints as Django middleware:
    - /agents.txt
    - /llms.txt, /llms-full.txt
    - /.well-known/ai
    - /.well-known/agent.json

Usage in settings.py:
    MIDDLEWARE = ['agent_layer.django.AgentLayerMiddleware', ...]
    AGENT_LAYER = {
        'agents_txt': AgentsTxtConfig(rules=[...]),
        'llms_txt': LlmsTxtConfig(title="My API"),
        'discovery': DiscoveryConfig(manifest=AIManifest(name="My API")),
        'a2a': A2AConfig(card=A2AAgentCard(name="My Agent", url="https://...")),
    }
"""

from __future__ import annotations

import json
from typing import Any, Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

from agent_layer.core.a2a import A2AConfig, generate_agent_card
from agent_layer.core.agents_txt import AgentsTxtConfig, generate_agents_txt
from agent_layer.core.discovery import DiscoveryConfig, generate_ai_manifest, generate_json_ld
from agent_layer.core.errors import AgentError
from agent_layer.core.llms_txt import LlmsTxtConfig, generate_llms_txt, generate_llms_full_txt


class AgentLayerMiddleware:
    """Django middleware that serves agent-layer endpoints.

    Configure via the AGENT_LAYER setting in your Django settings module.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self._config: dict[str, Any] = getattr(settings, "AGENT_LAYER", {})

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

        # Pass through to next middleware / view
        try:
            return self.get_response(request)
        except AgentError as e:
            return JsonResponse(e.to_json(), status=e.status)
