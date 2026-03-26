"""FastAPI route handler for /robots.txt."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from agent_layer.robots_txt import RobotsTxtConfig, generate_robots_txt


def robots_txt_routes(config: RobotsTxtConfig | None = None) -> APIRouter:
    """Create a FastAPI router that serves GET /robots.txt."""
    content = generate_robots_txt(config)
    router = APIRouter()

    @router.get("/robots.txt", response_class=PlainTextResponse)
    async def robots_txt() -> PlainTextResponse:
        return PlainTextResponse(
            content,
            headers={"Cache-Control": "public, max-age=86400"},
        )

    return router
