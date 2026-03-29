"""Agent Onboarding routes and auth middleware for FastAPI."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent_layer.agent_onboarding import (
    OnboardingConfig,
    RegistrationRequest,
    create_onboarding_handler,
)


class _RegistrationBody(BaseModel):
    """Pydantic model for the registration request body."""

    agent_id: str
    agent_name: str
    agent_provider: str
    identity_token: str | None = None
    metadata: dict | None = None


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def agent_onboarding_routes(config: OnboardingConfig) -> APIRouter:
    """Create a router with POST /agent/register."""
    router = APIRouter()
    handler = create_onboarding_handler(config)

    @router.post("/agent/register")
    async def register_agent(request: Request):
        body = await request.json()
        reg = RegistrationRequest(
            agent_id=body.get("agent_id", ""),
            agent_name=body.get("agent_name", ""),
            agent_provider=body.get("agent_provider", ""),
            identity_token=body.get("identity_token"),
            metadata=body.get("metadata"),
        )
        ip = _get_client_ip(request)
        result = await handler.handle_register(reg, ip)
        return JSONResponse(status_code=result.status, content=result.body)

    return router


def agent_onboarding_auth_middleware(config: OnboardingConfig):
    """Create a FastAPI middleware that returns 401 for unauthenticated agent requests."""
    handler = create_onboarding_handler(config)

    async def middleware(request: Request, call_next):
        headers: dict[str, str | None] = {}
        for k, v in request.headers.items():
            headers[k] = v

        if handler.should_return_401(request.url.path, headers):
            return JSONResponse(status_code=401, content=handler.get_auth_required_response())

        return await call_next(request)

    return middleware
