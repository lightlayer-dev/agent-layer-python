"""Django URL patterns for llms.txt and discovery endpoints."""

from __future__ import annotations

from django.http import HttpResponse, JsonResponse
from django.urls import path

from agent_layer.discovery import generate_ai_manifest, generate_json_ld
from agent_layer.llms_txt import generate_llms_txt, generate_llms_full_txt
from agent_layer.types import DiscoveryConfig, LlmsTxtConfig, RouteMetadata


def llms_txt_urlpatterns(
    config: LlmsTxtConfig,
    routes: list[RouteMetadata] | None = None,
) -> list:
    """Create Django URL patterns for /llms.txt and optionally /llms-full.txt."""

    def llms_txt_view(request):
        return HttpResponse(generate_llms_txt(config), content_type="text/plain")

    patterns = [path("llms.txt", llms_txt_view, name="llms_txt")]

    if routes is not None:
        def llms_full_txt_view(request):
            return HttpResponse(generate_llms_full_txt(config, routes), content_type="text/plain")

        patterns.append(path("llms-full.txt", llms_full_txt_view, name="llms_full_txt"))

    return patterns


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
