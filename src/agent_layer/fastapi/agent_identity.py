"""Agent Identity Middleware for FastAPI.

Per IETF draft-klrc-aiagent-auth-00:
- Validates JWT-based Workload Identity Tokens
- Enforces short-lived credential requirements
- Supports SPIFFE trust domain validation
- Generates audit events for observability
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse

from agent_layer.agent_identity import (
    AgentIdentityConfig,
    AgentIdentityClaims,
    AgentAuthzPolicyRuntime,
    AuthzContext,
    decode_jwt_claims,
    extract_claims,
    validate_claims,
    evaluate_authz,
)
from agent_layer.errors import format_error


def _extract_token(request: Request, header_name: str, prefix: str) -> str | None:
    """Extract the token string from the request header."""
    raw = request.headers.get(header_name)
    if not raw:
        return None
    if raw.startswith(prefix + " "):
        return raw[len(prefix) + 1 :]
    return raw


async def _verify_and_extract(
    token: str,
    config: AgentIdentityConfig,
    verify_token: Callable[[str], Awaitable[AgentIdentityClaims | None]] | None = None,
) -> AgentIdentityClaims | None:
    """Verify token and return claims, or None."""
    if verify_token:
        return await verify_token(token)
    payload = decode_jwt_claims(token)
    if payload is None:
        return None
    return extract_claims(payload)


def agent_identity_middleware(
    config: AgentIdentityConfig,
    verify_token: Callable[[str], Awaitable[AgentIdentityClaims | None]] | None = None,
):
    """Create a FastAPI middleware that requires agent identity on all routes.

    Attach verified claims to request.state.agent_identity.

    For optional identity (doesn't reject unauthenticated), use
    agent_identity_optional_middleware.
    """
    header_name = config.header_name.lower()
    prefix = config.token_prefix
    runtime_policies = [AgentAuthzPolicyRuntime.from_policy(p) for p in config.policies]

    async def middleware(request: Request, call_next: Any):
        token = _extract_token(request, header_name, prefix)

        if not token:
            return JSONResponse(
                status_code=401,
                content={
                    "error": format_error(
                        code="agent_identity_required",
                        message="Agent identity token is required.",
                        status=401,
                    ),
                },
            )

        claims = await _verify_and_extract(token, config, verify_token)
        if not claims:
            code = "verification_failed" if verify_token else "malformed_token"
            msg = (
                "Agent identity token verification failed."
                if verify_token
                else "Agent identity token is malformed."
            )
            return JSONResponse(
                status_code=401,
                content={"error": format_error(code=code, message=msg, status=401)},
            )

        validation_error = validate_claims(claims, config)
        if validation_error:
            status = 401 if validation_error.code == "expired_token" else 403
            return JSONResponse(
                status_code=status,
                content={
                    "error": format_error(
                        code=validation_error.code,
                        message=validation_error.message,
                        status=status,
                    ),
                },
            )

        request.state.agent_identity = claims

        if runtime_policies:
            context = AuthzContext(
                method=request.method,
                path=request.url.path,
                headers=dict(request.headers),
            )
            result = evaluate_authz(claims, context, runtime_policies, config.default_policy)
            if not result.allowed:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": format_error(
                            code="agent_unauthorized",
                            message=result.denied_reason or "Agent is not authorized.",
                            status=403,
                        ),
                    },
                )

        return await call_next(request)

    return middleware


def agent_identity_optional_middleware(
    config: AgentIdentityConfig,
    verify_token: Callable[[str], Awaitable[AgentIdentityClaims | None]] | None = None,
):
    """Create a FastAPI middleware that optionally extracts agent identity.

    If a valid token is present, attaches to request.state.agent_identity.
    If absent or invalid, silently continues without identity.
    """
    header_name = config.header_name.lower()
    prefix = config.token_prefix

    async def middleware(request: Request, call_next: Any):
        token = _extract_token(request, header_name, prefix)
        if token:
            try:
                claims = await _verify_and_extract(token, config, verify_token)
                if claims:
                    err = validate_claims(claims, config)
                    if not err:
                        request.state.agent_identity = claims
            except Exception:
                pass  # Silently ignore — identity is optional

        return await call_next(request)

    return middleware
