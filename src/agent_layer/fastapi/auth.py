"""Agent auth discovery routes for FastAPI."""

from __future__ import annotations

from fastapi import APIRouter

from agent_layer.types import AgentAuthConfig


def agent_auth_routes(config: AgentAuthConfig) -> APIRouter:
    """Create a router exposing OAuth/auth discovery for agents."""
    router = APIRouter()

    @router.get("/.well-known/oauth-authorization-server")
    async def oauth_metadata():
        metadata: dict = {}
        if config.issuer:
            metadata["issuer"] = config.issuer
        if config.authorization_url:
            metadata["authorization_endpoint"] = config.authorization_url
        if config.token_url:
            metadata["token_endpoint"] = config.token_url
        if config.scopes:
            metadata["scopes_supported"] = list(config.scopes.keys())
        return metadata

    return router
