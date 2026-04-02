"""Framework-agnostic agent identity verification handler.

Extracts the duplicated extractAndVerify, requireIdentity, and
optionalIdentity logic from all framework adapters.

Mirrors the TypeScript identity-handler.ts in agent-layer-ts.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent_layer.agent_identity import (
    AgentAuthzPolicyRuntime,
    AgentIdentityConfig,
    AgentIdentityClaims,
    AuthzContext,
    decode_jwt_claims,
    extract_claims,
    validate_claims,
    evaluate_authz,
)
from agent_layer.errors import format_error
from agent_layer.types import AgentErrorEnvelope, AgentErrorOptions


async def extract_and_verify_token(
    raw_header: str | None,
    config: AgentIdentityConfig,
) -> AgentIdentityClaims | None:
    """Extract and verify a token from a raw header value.

    Returns verified claims, or None if extraction/verification fails.
    """
    if not raw_header:
        return None

    prefix = config.token_prefix or "Bearer"
    if raw_header.startswith(prefix + " "):
        token = raw_header[len(prefix) + 1 :]
    else:
        token = raw_header

    payload = decode_jwt_claims(token)
    if not payload:
        return None
    return extract_claims(payload)


@dataclass
class IdentityError:
    """Error result from identity verification."""

    status: int
    envelope: AgentErrorEnvelope


@dataclass
class IdentitySuccess:
    """Success result from identity verification."""

    claims: AgentIdentityClaims


async def handle_require_identity(
    raw_header: str | None,
    config: AgentIdentityConfig,
    context: AuthzContext,
) -> IdentitySuccess | IdentityError:
    """Full identity verification and authorization flow.

    This replaces the duplicated requireIdentity() logic across all
    framework adapters. The caller only needs to:
    1. Extract the raw header value from the request
    2. Call this function
    3. If IdentityError, send the error response
    4. If IdentitySuccess, attach claims to request and continue
    """
    if not raw_header:
        return IdentityError(
            status=401,
            envelope=format_error(
                AgentErrorOptions(
                    code="agent_identity_required",
                    message="Agent identity token is required.",
                    status=401,
                )
            ),
        )

    claims = await extract_and_verify_token(raw_header, config)
    if not claims:
        return IdentityError(
            status=401,
            envelope=format_error(
                AgentErrorOptions(
                    code="malformed_token",
                    message="Agent identity token is malformed.",
                    status=401,
                )
            ),
        )

    validation_error = validate_claims(claims, config)
    if validation_error:
        status = 401 if validation_error.code == "expired_token" else 403
        return IdentityError(
            status=status,
            envelope=format_error(
                AgentErrorOptions(
                    code=validation_error.code,
                    message=validation_error.message,
                    status=status,
                )
            ),
        )

    if config.policies and len(config.policies) > 0:
        runtime_policies = [
            AgentAuthzPolicyRuntime.from_policy(p) for p in config.policies
        ]
        authz_result = evaluate_authz(
            claims,
            context,
            runtime_policies,
            config.default_policy,
        )

        if not authz_result.allowed:
            return IdentityError(
                status=403,
                envelope=format_error(
                    AgentErrorOptions(
                        code="agent_unauthorized",
                        message=authz_result.denied_reason or "Agent is not authorized.",
                        status=403,
                    )
                ),
            )

    return IdentitySuccess(claims=claims)


async def handle_optional_identity(
    raw_header: str | None,
    config: AgentIdentityConfig,
) -> AgentIdentityClaims | None:
    """Optional identity extraction — extracts and validates identity if present,
    but does not reject the request if missing or invalid.
    """
    if not raw_header:
        return None

    try:
        claims = await extract_and_verify_token(raw_header, config)
        if not claims:
            return None

        err = validate_claims(claims, config)
        if err:
            return None

        return claims
    except Exception:
        return None
