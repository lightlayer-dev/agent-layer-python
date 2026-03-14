"""llms.txt route handlers for FastAPI."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from agent_layer.llms_txt import generate_llms_txt, generate_llms_full_txt
from agent_layer.types import LlmsTxtConfig, RouteMetadata


def llms_txt_routes(
    config: LlmsTxtConfig,
    routes: list[RouteMetadata] | None = None,
) -> APIRouter:
    """Create a router with /llms.txt and optionally /llms-full.txt."""
    router = APIRouter()

    @router.get("/llms.txt", response_class=PlainTextResponse)
    async def llms_txt():
        return generate_llms_txt(config)

    if routes is not None:
        @router.get("/llms-full.txt", response_class=PlainTextResponse)
        async def llms_full_txt():
            return generate_llms_full_txt(config, routes)

    return router
