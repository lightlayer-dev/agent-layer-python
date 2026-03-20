"""A2A Agent Card route handler for FastAPI."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from agent_layer.a2a import A2AConfig, generate_agent_card


def a2a_routes(config: A2AConfig) -> APIRouter:
    """Create a router serving /.well-known/agent.json."""
    router = APIRouter()
    card = generate_agent_card(config)

    @router.get("/.well-known/agent.json")
    async def agent_card():
        return JSONResponse(
            content=card,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    return router
