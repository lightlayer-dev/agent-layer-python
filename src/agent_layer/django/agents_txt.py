"""agents.txt views and enforcement middleware for Django."""

from __future__ import annotations

import json
from typing import Callable

from django.http import HttpRequest, HttpResponse, JsonResponse

from agent_layer.agents_txt import AgentsTxtConfig, generate_agents_txt, is_agent_allowed


def agents_txt_view(config: AgentsTxtConfig):
    """Return a Django view function serving /agents.txt."""
    content = generate_agents_txt(config)

    def view(request: HttpRequest) -> HttpResponse:
        resp = HttpResponse(content, content_type="text/plain; charset=utf-8")
        resp["Cache-Control"] = "public, max-age=3600"
        return resp

    return view


class AgentsTxtEnforceMiddleware:
    """Django middleware that enforces agents.txt rules."""

    def __init__(self, get_response: Callable, config: AgentsTxtConfig | None = None):
        self.get_response = get_response
        self.config = config

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if self.config and self.config.enforce:
            user_agent = request.META.get("HTTP_USER_AGENT", "")
            path = request.path
            allowed = is_agent_allowed(self.config, user_agent, path)

            if allowed is False:
                return JsonResponse(
                    {
                        "error": {
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
                    },
                    status=403,
                )

        return self.get_response(request)
