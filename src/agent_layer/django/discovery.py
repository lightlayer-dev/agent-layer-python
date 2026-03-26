"""Discovery route URL patterns for Django."""

from __future__ import annotations

from django.http import JsonResponse
from django.urls import path

from agent_layer.discovery import generate_ai_manifest, generate_json_ld
from agent_layer.types import DiscoveryConfig


def discovery_urlpatterns(config: DiscoveryConfig) -> list:
    """Create Django URL patterns for /.well-known/ai and /json-ld."""

    def well_known_ai(request):
        return JsonResponse(generate_ai_manifest(config))

    def json_ld(request):
        return JsonResponse(generate_json_ld(config))

    patterns = [
        path(".well-known/ai", well_known_ai, name="well_known_ai"),
        path("json-ld", json_ld, name="json_ld"),
    ]

    if config.openapi_spec:
        def openapi_spec(request):
            return JsonResponse(config.openapi_spec)

        patterns.append(path("openapi.json", openapi_spec, name="openapi_spec"))

    return patterns
