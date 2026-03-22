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
    check_identity,
    extract_token_from_header,
)


def agent_identity_middleware(
    config: AgentIdentityConfig,
    verify_token: Callable[[str], Awaitable[AgentIdentityClaims | None]] | None = None,
    optional: bool = False,
):
    """Create a FastAPI middleware that verifies agent identity.

    Attach verified claims to request.state.agent_identity.

    Args:
        config: Agent identity configuration.
        verify_token: Optional async token verifier.
        optional: If True, don't reject unauthenticated requests.
    """
    header_name = config.header_name.lower()
    prefix = config.token_prefix
    runtime_policies = [AgentAuthzPolicyRuntime.from_policy(p) for p in config.policies]

    async def middleware(request: Request, call_next: Any):
        raw = request.headers.get(header_name)
        token = extract_token_from_header(raw, prefix)

        # Optional async verification
        decoded = None
        if token and verify_token:
            decoded = await verify_token(token)
            if decoded is None:
                if optional:
                    return await call_next(request)
                from agent_layer.errors import format_error
                from agent_layer.types import AgentErrorOptions

                envelope = format_error(
                    AgentErrorOptions(
                        code="verification_failed",
                        message="Agent identity token verification failed.",
                        status=401,
                    )
                )
                return JSONResponse(
                    status_code=401,
                    content={"error": envelope.model_dump(exclude_none=True)},
                )

        result = check_identity(
            token,
            config,
            decoded_claims=decoded,
            method=request.method,
            path=request.url.path,
            headers=dict(request.headers),
            runtime_policies=runtime_policies,
        )

        if not result.ok:
            if optional:
                return await call_next(request)
            return JSONResponse(
                status_code=result.error_status,
                content=result.error_body,
            )

        request.state.agent_identity = result.claims
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
    return agent_identity_middleware(config, verify_token, optional=True)
