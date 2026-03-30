"""llms.txt URL patterns for Django."""

from __future__ import annotations

from django.http import HttpResponse
from django.urls import path

from agent_layer.llms_txt import generate_llms_txt, generate_llms_full_txt
from agent_layer.types import LlmsTxtConfig, RouteMetadata


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
