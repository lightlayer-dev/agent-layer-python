"""Framework-agnostic agent auth helpers.

Extracts the duplicated oauthDiscoveryDocument and requireAuth logic
into a single, testable module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_layer.errors import format_error
from agent_layer.types import AgentAuthConfig, AgentErrorEnvelope, AgentErrorOptions


def build_oauth_discovery_document(
    config: AgentAuthConfig,
) -> dict[str, Any]:
    """Generate the OAuth 2.0 discovery document from auth config."""
    doc: dict[str, Any] = {}

    if config.issuer:
        doc["issuer"] = config.issuer
    if config.authorization_url:
        doc["authorization_endpoint"] = config.authorization_url
    if config.token_url:
        doc["token_endpoint"] = config.token_url
    if config.scopes:
        doc["scopes_supported"] = list(config.scopes.keys())

    return doc


def build_www_authenticate(
    realm: str,
    scopes: dict[str, str] | None = None,
) -> str:
    """Build the WWW-Authenticate header value."""
    parts = [f'Bearer realm="{realm}"']
    if scopes:
        parts.append(f'scope="{" ".join(scopes.keys())}"')
    return ", ".join(parts)


@dataclass
class RequireAuthResult:
    """Result of checking an auth requirement.

    If ``passed`` is True, the request has an Authorization header.
    If ``passed`` is False, ``www_authenticate`` and ``envelope`` describe the 401 response.
    """

    passed: bool
    www_authenticate: str | None = None
    envelope: AgentErrorEnvelope | None = None


def check_require_auth(
    config: AgentAuthConfig,
    authorization_header: str | None,
) -> RequireAuthResult:
    """Check whether a request has an Authorization header.

    Returns a result indicating whether to continue or send a 401.
    """
    if authorization_header:
        return RequireAuthResult(passed=True)

    realm = config.realm or "api"
    www_authenticate = build_www_authenticate(realm, config.scopes or None)
    envelope = format_error(
        AgentErrorOptions(
            code="authentication_required",
            message="This endpoint requires authentication.",
            status=401,
            docs_url=config.authorization_url,
        )
    )

    return RequireAuthResult(
        passed=False,
        www_authenticate=www_authenticate,
        envelope=envelope,
    )
