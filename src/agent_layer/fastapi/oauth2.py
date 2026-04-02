"""OAuth2/PKCE routes and middleware for FastAPI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from agent_layer.oauth2 import DecodedAccessToken, OAuth2Config, build_oauth2_metadata
from agent_layer.oauth2_handler import OAuth2MiddlewareConfig, handle_oauth2


def oauth2_routes(config: OAuth2Config) -> APIRouter:
    """Create a router exposing OAuth2 metadata for agents."""
    router = APIRouter()

    @router.get("/.well-known/oauth2-metadata")
    async def oauth2_metadata() -> dict[str, Any]:
        return build_oauth2_metadata(config)

    return router


def require_token(
    config: OAuth2Config,
    required_scopes: list[str] | None = None,
    clock_skew_seconds: int = 30,
):
    """FastAPI dependency that validates Bearer tokens.

    Usage::

        token = Depends(require_token(config, required_scopes=["read"]))

    Returns the decoded access token on success, raises HTTPException on failure.
    """
    mw_config = OAuth2MiddlewareConfig(
        oauth2=config,
        required_scopes=required_scopes,
        clock_skew_seconds=clock_skew_seconds,
    )

    async def _dependency(request: Request) -> DecodedAccessToken:
        authorization = request.headers.get("authorization")
        result = await handle_oauth2(authorization, mw_config)

        if result.passed:
            return result.token  # type: ignore[union-attr]

        raise HTTPException(
            status_code=result.status,  # type: ignore[union-attr]
            detail=result.envelope,  # type: ignore[union-attr]
            headers={"WWW-Authenticate": result.www_authenticate},  # type: ignore[union-attr]
        )

    return _dependency
