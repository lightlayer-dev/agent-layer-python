"""OAuth2/PKCE routes for FastAPI."""

from __future__ import annotations

from fastapi import APIRouter

from agent_layer.oauth2 import OAuth2Config, build_oauth2_metadata


def oauth2_routes(config: OAuth2Config) -> APIRouter:
    """Create a router exposing OAuth2 metadata for agents."""
    router = APIRouter()

    @router.get("/.well-known/oauth2-metadata")
    async def oauth2_metadata():
        return build_oauth2_metadata(config)

    return router
