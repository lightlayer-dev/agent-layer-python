"""Unified multi-format discovery routes for FastAPI."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse

from agent_layer.unified_discovery import (
    UnifiedDiscoveryConfig,
    generate_agents_txt,
    generate_unified_agent_card,
    generate_unified_ai_manifest,
    generate_unified_llms_full_txt,
    generate_unified_llms_txt,
)


def unified_discovery_routes(config: UnifiedDiscoveryConfig) -> APIRouter:
    """Create a FastAPI router serving all enabled discovery formats.

    Example::

        from agent_layer.fastapi.unified_discovery import unified_discovery_routes
        from agent_layer.unified_discovery import UnifiedDiscoveryConfig

        config = UnifiedDiscoveryConfig(
            name="My API",
            description="REST API for widgets",
            url="https://api.example.com",
            skills=[{"id": "search", "name": "Search", "description": "Full-text search"}],
        )
        app.include_router(unified_discovery_routes(config))
    """
    router = APIRouter()

    # Pre-generate all documents at startup
    ai_manifest = generate_unified_ai_manifest(config)
    agent_card_doc = generate_unified_agent_card(config)
    agents_txt_doc = generate_agents_txt(config)
    llms_txt_doc = generate_unified_llms_txt(config)
    llms_full_txt_doc = generate_unified_llms_full_txt(config)

    if config.formats.well_known_ai:

        @router.get("/.well-known/ai")
        async def well_known_ai():
            return JSONResponse(content=ai_manifest)

    if config.formats.agent_card:

        @router.get("/.well-known/agent.json")
        async def agent_card():
            return JSONResponse(
                content=agent_card_doc,
                headers={"Cache-Control": "public, max-age=3600"},
            )

    if config.formats.agents_txt:

        @router.get("/agents.txt")
        async def agents_txt():
            return PlainTextResponse(content=agents_txt_doc)

    if config.formats.llms_txt:

        @router.get("/llms.txt")
        async def llms_txt():
            return PlainTextResponse(content=llms_txt_doc)

        @router.get("/llms-full.txt")
        async def llms_full_txt():
            return PlainTextResponse(content=llms_full_txt_doc)

    return router
