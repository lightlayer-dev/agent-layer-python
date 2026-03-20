"""Agent Identity Middleware for Flask.

Per IETF draft-klrc-aiagent-auth-00.
"""

from __future__ import annotations

from typing import Callable

from flask import Flask, g, jsonify, request

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


def _extract_token(header_name: str, prefix: str) -> str | None:
    raw = request.headers.get(header_name)
    if not raw:
        return None
    if raw.startswith(prefix + " "):
        return raw[len(prefix) + 1 :]
    return raw


def _verify_sync(
    token: str,
    config: AgentIdentityConfig,
    verify_token: Callable[[str], AgentIdentityClaims | None] | None = None,
) -> AgentIdentityClaims | None:
    if verify_token:
        return verify_token(token)
    payload = decode_jwt_claims(token)
    if payload is None:
        return None
    return extract_claims(payload)


def agent_identity_extension(
    app: Flask,
    config: AgentIdentityConfig,
    verify_token: Callable[[str], AgentIdentityClaims | None] | None = None,
    optional: bool = False,
):
    """Register agent identity verification on a Flask app.

    Verified claims are stored in ``g.agent_identity``.

    Args:
        app: Flask application.
        config: Agent identity configuration.
        verify_token: Optional sync token verifier.
        optional: If True, don't reject unauthenticated requests.
    """
    header_name = config.header_name
    prefix = config.token_prefix
    runtime_policies = [AgentAuthzPolicyRuntime.from_policy(p) for p in config.policies]

    @app.before_request
    def _check_agent_identity():
        g.agent_identity = None

        token = _extract_token(header_name, prefix)

        if not token:
            if optional:
                return None
            return (
                jsonify(
                    error=format_error(
                        code="agent_identity_required",
                        message="Agent identity token is required.",
                        status=401,
                    )
                ),
                401,
            )

        try:
            claims = _verify_sync(token, config, verify_token)
        except Exception:
            if optional:
                return None
            claims = None

        if not claims:
            if optional:
                return None
            code = "verification_failed" if verify_token else "malformed_token"
            msg = (
                "Agent identity token verification failed."
                if verify_token
                else "Agent identity token is malformed."
            )
            return jsonify(error=format_error(code=code, message=msg, status=401)), 401

        validation_error = validate_claims(claims, config)
        if validation_error:
            if optional:
                return None
            status = 401 if validation_error.code == "expired_token" else 403
            return (
                jsonify(
                    error=format_error(
                        code=validation_error.code,
                        message=validation_error.message,
                        status=status,
                    )
                ),
                status,
            )

        g.agent_identity = claims

        if runtime_policies:
            context = AuthzContext(
                method=request.method,
                path=request.path,
                headers=dict(request.headers),
            )
            result = evaluate_authz(claims, context, runtime_policies, config.default_policy)
            if not result.allowed:
                return (
                    jsonify(
                        error=format_error(
                            code="agent_unauthorized",
                            message=result.denied_reason or "Agent is not authorized.",
                            status=403,
                        )
                    ),
                    403,
                )

        return None
