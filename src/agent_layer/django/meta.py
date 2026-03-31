"""Agent meta middleware for Django — injects agent-friendly headers."""

from __future__ import annotations

from typing import Any, Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from agent_layer.types import AgentMetaConfig


class AgentMetaMiddleware:
    """Django middleware that injects agent-related meta headers.

    Configure in settings.py::

        MIDDLEWARE = [
            "agent_layer.django.meta.AgentMetaMiddleware",
            ...
        ]

        AGENT_LAYER_META = {
            "agent_id_attribute": "data-agent-id",
            "aria_landmarks": True,
        }
    """

    def __init__(self, get_response: Callable[..., Any]) -> None:
        self.get_response = get_response
        raw: dict[str, Any] = getattr(settings, "AGENT_LAYER_META", {})
        self.config = AgentMetaConfig(**raw)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response["X-Agent-Meta"] = "true"
        if self.config.agent_id_attribute:
            response["X-Agent-Id-Attribute"] = self.config.agent_id_attribute
        return response
