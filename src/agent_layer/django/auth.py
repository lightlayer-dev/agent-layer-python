"""Agent auth discovery URL patterns for Django."""

from __future__ import annotations

from django.http import JsonResponse
from django.urls import path

from agent_layer.types import AgentAuthConfig


def agent_auth_urlpatterns(config: AgentAuthConfig) -> list:
    """Create Django URL patterns for OAuth/auth discovery."""

    def oauth_metadata(request):
        metadata: dict = {}
        if config.issuer:
            metadata["issuer"] = config.issuer
        if config.authorization_url:
            metadata["authorization_endpoint"] = config.authorization_url
        if config.token_url:
            metadata["token_endpoint"] = config.token_url
        if config.scopes:
            metadata["scopes_supported"] = list(config.scopes.keys())
        return JsonResponse(metadata)

    return [
        path(
            ".well-known/oauth-authorization-server",
            oauth_metadata,
            name="oauth_metadata",
        ),
    ]
