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
    check_identity,
    extract_token_from_header,
)


def agent_identity_middleware(
    app: Flask,
    config: AgentIdentityConfig,
    verify_token: Callable[[str], AgentIdentityClaims | None] | None = None,
    optional: bool = False,
) -> None:
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

        raw = request.headers.get(header_name)
        token = extract_token_from_header(raw, prefix)

        # Optional sync verification
        decoded = None
        if token and verify_token:
            try:
                decoded = verify_token(token)
            except Exception:
                if optional:
                    return None
                decoded = None
            if decoded is None and verify_token:
                if optional:
                    return None
                from agent_layer.errors import format_error
                from agent_layer.types import AgentErrorOptions

                envelope = format_error(
                    AgentErrorOptions(
                        code="verification_failed",
                        message="Agent identity token verification failed.",
                        status=401,
                    )
                )
                return jsonify({"error": envelope.model_dump(exclude_none=True)}), 401

        identity = check_identity(
            token,
            config,
            decoded_claims=decoded,
            method=request.method,
            path=request.path,
            headers=dict(request.headers),
            runtime_policies=runtime_policies,
        )

        if not identity.ok:
            if optional:
                return None
            return jsonify(identity.error_body), identity.error_status

        g.agent_identity = identity.claims
        return None
