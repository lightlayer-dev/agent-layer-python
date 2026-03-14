"""Discovery route handlers for FastAPI."""

from __future__ import annotations

from fastapi import APIRouter

from agent_layer.discovery import generate_ai_manifest, generate_json_ld
from agent_layer.types import DiscoveryConfig


def discovery_routes(config: DiscoveryConfig) -> APIRouter:
    """Create a router with /.well-known/ai and /json-ld endpoints."""
    router = APIRouter()

    @router.get("/.well-known/ai")
    async def well_known_ai():
        return generate_ai_manifest(config)

    @router.get("/json-ld")
    async def json_ld():
        return generate_json_ld(config)

    if config.openapi_spec:
        @router.get("/openapi.json")
        async def openapi_spec():
            return config.openapi_spec

    return router
