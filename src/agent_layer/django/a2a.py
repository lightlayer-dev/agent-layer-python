"""A2A Agent Card URL patterns for Django."""

from __future__ import annotations

from django.http import JsonResponse
from django.urls import path

from agent_layer.a2a import A2AConfig, generate_agent_card


def a2a_urlpatterns(config: A2AConfig) -> list:
    """Create Django URL patterns for /.well-known/agent.json."""
    card = generate_agent_card(config)

    def agent_card_view(request):
        response = JsonResponse(card)
        response["Cache-Control"] = "public, max-age=3600"
        return response

    return [
        path(".well-known/agent.json", agent_card_view, name="a2a_agent_card"),
    ]
