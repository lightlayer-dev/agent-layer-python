"""OAuth2/PKCE URL patterns for Django."""

from __future__ import annotations

from django.http import JsonResponse
from django.urls import path

from agent_layer.oauth2 import OAuth2Config, build_oauth2_metadata


def oauth2_urlpatterns(config: OAuth2Config) -> list:
    """Create Django URL patterns for OAuth2 metadata."""

    def oauth2_metadata(request):
        return JsonResponse(build_oauth2_metadata(config))

    return [
        path(
            ".well-known/oauth2-metadata",
            oauth2_metadata,
            name="oauth2_metadata",
        ),
    ]
