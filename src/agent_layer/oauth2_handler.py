"""Framework-agnostic OAuth2 middleware handler.

Provides shared logic for OAuth2 Bearer token validation
that framework adapters (FastAPI, Flask, Django) call into.

Mirrors the TypeScript oauth2-handler.ts in agent-layer-ts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable

from agent_layer.errors import format_error
from agent_layer.oauth2 import (
    OAuth2Config,
    DecodedAccessToken,
    TokenValidationResult,
    extract_bearer_token,
    validate_access_token,
)
from agent_layer.types import AgentErrorEnvelope, AgentErrorOptions


# ── Types ────────────────────────────────────────────────────────────────


@dataclass
class OAuth2MiddlewareConfig:
    """Configuration for the OAuth2 middleware handler."""

    oauth2: OAuth2Config
    """OAuth2 configuration for token validation."""

    required_scopes: list[str] | None = None
    """Scopes required for the protected route."""

    clock_skew_seconds: int = 30
    """Clock skew tolerance in seconds."""

    custom_validator: Callable[[str], Awaitable[TokenValidationResult]] | None = None
    """Custom token validator (for signature verification with JWKS, etc.)."""


@dataclass
class OAuth2ValidationSuccess:
    """Successful OAuth2 validation result."""

    passed: bool = field(default=True, init=False)
    token: DecodedAccessToken = field(default_factory=lambda: DecodedAccessToken(sub="", exp=0))


@dataclass
class OAuth2ValidationFailure:
    """Failed OAuth2 validation result."""

    passed: bool = field(default=False, init=False)
    status: int = 401
    www_authenticate: str = ""
    envelope: AgentErrorEnvelope | None = None


OAuth2ValidationResult = OAuth2ValidationSuccess | OAuth2ValidationFailure


# ── Handler ──────────────────────────────────────────────────────────────


async def handle_oauth2(
    authorization_header: str | None,
    config: OAuth2MiddlewareConfig,
) -> OAuth2ValidationResult:
    """Validate an OAuth2 Bearer token from the Authorization header.

    Returns a structured result the framework adapter can use to allow or deny.
    """
    raw_token = extract_bearer_token(authorization_header)

    if not raw_token:
        realm = config.oauth2.issuer or "api"
        scope_str = " ".join(config.required_scopes) if config.required_scopes else None
        www_auth = (
            f'Bearer realm="{realm}", scope="{scope_str}"'
            if scope_str
            else f'Bearer realm="{realm}"'
        )

        envelope = format_error(
            AgentErrorOptions(
                code="authentication_required",
                message="Bearer token required. Obtain one via the OAuth2 authorization flow.",
                status=401,
                docs_url=config.oauth2.authorization_endpoint,
            )
        )

        return OAuth2ValidationFailure(
            status=401,
            www_authenticate=www_auth,
            envelope=envelope,
        )

    # Use custom validator if provided (e.g., JWKS signature verification)
    if config.custom_validator:
        result = await config.custom_validator(raw_token)
    else:
        result = validate_access_token(
            raw_token,
            config.oauth2,
            config.required_scopes,
            config.clock_skew_seconds,
        )

    if not result.valid:
        is_scope_error = (result.error or "").startswith("missing_scopes")
        status = 403 if is_scope_error else 401
        code = "insufficient_scope" if is_scope_error else "invalid_token"
        message = (
            f"Insufficient scope. Required: {', '.join(config.required_scopes or [])}"
            if is_scope_error
            else f"Invalid token: {result.error}"
        )

        realm = config.oauth2.issuer or "api"
        www_auth = (
            f'Bearer realm="{realm}", error="insufficient_scope", scope="{" ".join(config.required_scopes or [])}"'
            if is_scope_error
            else f'Bearer realm="{realm}", error="invalid_token"'
        )

        envelope = format_error(
            AgentErrorOptions(code=code, message=message, status=status)
        )

        return OAuth2ValidationFailure(
            status=status,
            www_authenticate=www_auth,
            envelope=envelope,
        )

    return OAuth2ValidationSuccess(token=result.token)  # type: ignore[arg-type]
