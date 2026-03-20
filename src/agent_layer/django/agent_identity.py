"""Agent Identity Middleware for Django.

Per IETF draft-klrc-aiagent-auth-00.

Usage in settings.py::

    MIDDLEWARE = [
        ...
        "agent_layer.django.agent_identity.AgentIdentityMiddleware",
    ]

    AGENT_IDENTITY = {
        "trusted_issuers": ["https://auth.example.com"],
        "audience": ["https://api.example.com"],
    }
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

from agent_layer.agent_identity import (
    AgentIdentityConfig,
    AgentAuthzPolicyRuntime,
    AuthzContext,
    decode_jwt_claims,
    extract_claims,
    validate_claims,
    evaluate_authz,
)
from agent_layer.errors import format_error


class AgentIdentityMiddleware:
    """Django middleware for agent identity verification."""

    def __init__(self, get_response: Any):
        self.get_response = get_response
        raw = getattr(settings, "AGENT_IDENTITY", {})
        self.config = AgentIdentityConfig(**raw)
        self.header_name = self.config.header_name
        self.prefix = self.config.token_prefix
        self.runtime_policies = [
            AgentAuthzPolicyRuntime.from_policy(p) for p in self.config.policies
        ]
        self.optional = raw.get("optional", False)

    def _extract_token(self, request: HttpRequest) -> str | None:
        # Django normalizes headers: Authorization → META HTTP_AUTHORIZATION
        meta_key = "HTTP_" + self.header_name.upper().replace("-", "_")
        raw = request.META.get(meta_key)
        if not raw:
            return None
        if raw.startswith(self.prefix + " "):
            return raw[len(self.prefix) + 1 :]
        return raw

    def _error(self, code: str, message: str, status: int) -> JsonResponse:
        return JsonResponse(
            {"error": format_error(code=code, message=message, status=status)},
            status=status,
        )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.agent_identity = None  # type: ignore[attr-defined]

        token = self._extract_token(request)

        if not token:
            if self.optional:
                return self.get_response(request)
            return self._error(
                "agent_identity_required",
                "Agent identity token is required.",
                401,
            )

        payload = decode_jwt_claims(token)
        if not payload:
            if self.optional:
                return self.get_response(request)
            return self._error(
                "malformed_token",
                "Agent identity token is malformed.",
                401,
            )

        claims = extract_claims(payload)
        validation_error = validate_claims(claims, self.config)
        if validation_error:
            if self.optional:
                return self.get_response(request)
            status = 401 if validation_error.code == "expired_token" else 403
            return self._error(validation_error.code, validation_error.message, status)

        request.agent_identity = claims  # type: ignore[attr-defined]

        if self.runtime_policies:
            context = AuthzContext(
                method=request.method,
                path=request.path,
                headers={k: v for k, v in request.META.items() if k.startswith("HTTP_")},
            )
            result = evaluate_authz(
                claims, context, self.runtime_policies, self.config.default_policy
            )
            if not result.allowed:
                return self._error(
                    "agent_unauthorized",
                    result.denied_reason or "Agent is not authorized.",
                    403,
                )

        return self.get_response(request)
