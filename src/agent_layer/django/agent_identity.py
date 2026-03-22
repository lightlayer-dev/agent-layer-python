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
    check_identity,
    extract_token_from_header,
)


class AgentIdentityMiddleware:
    """Django middleware for agent identity verification."""

    def __init__(self, get_response: object) -> None:
        self.get_response = get_response
        raw: dict[str, Any] = getattr(settings, "AGENT_IDENTITY", {})
        self.config = AgentIdentityConfig(**raw)
        self.header_name = self.config.header_name
        self.prefix = self.config.token_prefix
        self.runtime_policies = [
            AgentAuthzPolicyRuntime.from_policy(p) for p in self.config.policies
        ]
        self.optional: bool = raw.get("optional", False)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.agent_identity = None  # type: ignore[attr-defined]

        # Django normalizes headers: Authorization → META HTTP_AUTHORIZATION
        meta_key = "HTTP_" + self.header_name.upper().replace("-", "_")
        raw_header = request.META.get(meta_key)
        token = extract_token_from_header(raw_header, self.prefix)

        result = check_identity(
            token,
            self.config,
            method=request.method,
            path=request.path,
            headers={k: v for k, v in request.META.items() if k.startswith("HTTP_")},
            runtime_policies=self.runtime_policies,
        )

        if not result.ok:
            if self.optional:
                return self.get_response(request)
            return JsonResponse(result.error_body, status=result.error_status)

        request.agent_identity = result.claims  # type: ignore[attr-defined]
        return self.get_response(request)
