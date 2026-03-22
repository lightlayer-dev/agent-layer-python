"""Unified multi-format discovery URL patterns for Django."""

from __future__ import annotations

from django.http import HttpResponse, JsonResponse
from django.urls import path

from agent_layer.unified_discovery import (
    UnifiedDiscoveryConfig,
    generate_agents_txt,
    generate_unified_agent_card,
    generate_unified_ai_manifest,
    generate_unified_llms_full_txt,
    generate_unified_llms_txt,
)


def unified_discovery_urlpatterns(config: UnifiedDiscoveryConfig) -> list:
    """Create Django URL patterns serving all enabled discovery formats.

    Example::

        from agent_layer.django.unified_discovery import unified_discovery_urlpatterns
        from agent_layer.unified_discovery import UnifiedDiscoveryConfig

        config = UnifiedDiscoveryConfig(
            name="My API",
            description="REST API for widgets",
            url="https://api.example.com",
        )
        urlpatterns += unified_discovery_urlpatterns(config)
    """
    patterns: list = []

    # Pre-generate all documents
    ai_manifest = generate_unified_ai_manifest(config)
    agent_card_doc = generate_unified_agent_card(config)
    agents_txt_doc = generate_agents_txt(config)
    llms_txt_doc = generate_unified_llms_txt(config)
    llms_full_txt_doc = generate_unified_llms_full_txt(config)

    if config.formats.well_known_ai:

        def well_known_ai(request):
            return JsonResponse(ai_manifest)

        patterns.append(path(".well-known/ai", well_known_ai, name="unified_well_known_ai"))

    if config.formats.agent_card:

        def agent_card(request):
            response = JsonResponse(agent_card_doc)
            response["Cache-Control"] = "public, max-age=3600"
            return response

        patterns.append(
            path(".well-known/agent.json", agent_card, name="unified_agent_card")
        )

    if config.formats.agents_txt:

        def agents_txt(request):
            return HttpResponse(agents_txt_doc, content_type="text/plain")

        patterns.append(path("agents.txt", agents_txt, name="unified_agents_txt"))

    if config.formats.llms_txt:

        def llms_txt(request):
            return HttpResponse(llms_txt_doc, content_type="text/plain")

        def llms_full_txt(request):
            return HttpResponse(llms_full_txt_doc, content_type="text/plain")

        patterns.append(path("llms.txt", llms_txt, name="unified_llms_txt"))
        patterns.append(path("llms-full.txt", llms_full_txt, name="unified_llms_full_txt"))

    return patterns
