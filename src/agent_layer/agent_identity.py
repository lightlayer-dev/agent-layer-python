"""Agent Identity Module — per IETF draft-klrc-aiagent-auth-00.

Implements agent identity verification following the AIMS (Agent Identity
Management System) model. Treats AI agents as workloads with SPIFFE/WIMSE
identifiers, JWT-based credentials, and scoped authorization.

Supports:
- JWT-based Workload Identity Tokens (WIT) verification
- SPIFFE ID extraction and validation
- Scoped authorization policies
- Audit event generation for the analytics pipeline
"""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, Field


# ── Types ────────────────────────────────────────────────────────────────


@dataclass
class SpiffeId:
    """SPIFFE ID in URI form: spiffe://trust-domain/path"""

    trust_domain: str
    path: str
    raw: str


@dataclass
class AgentIdentityClaims:
    """Claims extracted from a verified agent identity token."""

    agent_id: str
    issuer: str
    subject: str
    audience: list[str]
    expires_at: int
    issued_at: int
    scopes: list[str]
    delegated: bool
    spiffe_id: SpiffeId | None = None
    delegated_by: str | None = None
    custom_claims: dict[str, Any] = field(default_factory=dict)


class AgentAuthzPolicy(BaseModel):
    """A policy rule for agent authorization."""

    name: str
    agent_pattern: str | None = None
    trust_domains: list[str] | None = None
    required_scopes: list[str] | None = None
    methods: list[str] | None = None
    paths: list[str] | None = None
    allow_delegated: bool | None = None
    # NOTE: evaluate is not included in Pydantic model; use AgentAuthzPolicyWithEval


@dataclass
class AgentAuthzPolicyRuntime:
    """Runtime policy with optional custom evaluator (not serializable)."""

    name: str
    agent_pattern: str | None = None
    trust_domains: list[str] | None = None
    required_scopes: list[str] | None = None
    methods: list[str] | None = None
    paths: list[str] | None = None
    allow_delegated: bool | None = None
    evaluate: Callable[[AgentIdentityClaims, AuthzContext], bool] | None = None

    @staticmethod
    def from_policy(p: AgentAuthzPolicy) -> AgentAuthzPolicyRuntime:
        return AgentAuthzPolicyRuntime(
            name=p.name,
            agent_pattern=p.agent_pattern,
            trust_domains=p.trust_domains,
            required_scopes=p.required_scopes,
            methods=p.methods,
            paths=p.paths,
            allow_delegated=p.allow_delegated,
        )


@dataclass
class AuthzContext:
    method: str
    path: str
    headers: dict[str, str | None]


@dataclass
class AuthzResult:
    allowed: bool
    matched_policy: str | None = None
    denied_reason: str | None = None


class AgentIdentityConfig(BaseModel):
    """Configuration for the agent identity module."""

    trusted_issuers: list[str]
    audience: list[str]
    jwks_endpoints: dict[str, str] | None = None
    trusted_domains: list[str] | None = None
    policies: list[AgentAuthzPolicy] = Field(default_factory=list)
    default_policy: str = "deny"  # "allow" or "deny"
    header_name: str = "Authorization"
    token_prefix: str = "Bearer"
    clock_skew_seconds: int = 30
    max_lifetime_seconds: int = 3600

    model_config = {"arbitrary_types_allowed": True}


# ── SPIFFE ID Parser ─────────────────────────────────────────────────────

_SPIFFE_RE = re.compile(r"^spiffe://([^/]+)(/.*)?$")


def parse_spiffe_id(uri: str) -> SpiffeId | None:
    """Parse a SPIFFE ID URI. Returns None if not a valid SPIFFE ID."""
    m = _SPIFFE_RE.match(uri)
    if not m:
        return None
    return SpiffeId(
        trust_domain=m.group(1),
        path=m.group(2) or "/",
        raw=uri,
    )


def is_spiffe_trusted(spiffe_id: SpiffeId, trusted_domains: list[str]) -> bool:
    """Validate a SPIFFE ID against a list of trusted domains."""
    return spiffe_id.trust_domain in trusted_domains


# ── JWT Decoding ─────────────────────────────────────────────────────────


def _base64url_decode(s: str) -> bytes:
    padded = s + "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(padded)


def decode_jwt_claims(token: str) -> dict[str, Any] | None:
    """Decode JWT claims WITHOUT verification (for inspection only)."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        return json.loads(_base64url_decode(parts[1]))
    except Exception:
        return None


# ── Claims Extraction ────────────────────────────────────────────────────

_KNOWN_CLAIMS = {
    "iss",
    "sub",
    "aud",
    "exp",
    "iat",
    "nbf",
    "jti",
    "scope",
    "scopes",
    "scp",
    "act",
    "agent_id",
}


def extract_claims(payload: dict[str, Any]) -> AgentIdentityClaims:
    """Extract AgentIdentityClaims from raw JWT payload."""
    iss = str(payload.get("iss", ""))
    sub = str(payload.get("sub", ""))
    agent_id = str(payload.get("agent_id", payload.get("sub", "")))

    spiffe_id = parse_spiffe_id(agent_id)

    # Audience normalization
    raw_aud = payload.get("aud")
    if isinstance(raw_aud, list):
        audience = [str(a) for a in raw_aud]
    elif raw_aud is not None:
        audience = [str(raw_aud)]
    else:
        audience = []

    # Scopes
    scopes: list[str] = []
    if isinstance(payload.get("scope"), str):
        scopes = [s for s in payload["scope"].split(" ") if s]
    elif isinstance(payload.get("scopes"), list):
        scopes = [str(s) for s in payload["scopes"]]
    elif isinstance(payload.get("scp"), list):
        scopes = [str(s) for s in payload["scp"]]

    # Delegation
    delegated = payload.get("act") is not None
    delegated_by = None
    if delegated:
        act = payload.get("act", {})
        if isinstance(act, dict):
            delegated_by = str(act.get("sub", "")) or None

    # Custom claims
    custom_claims = {k: v for k, v in payload.items() if k not in _KNOWN_CLAIMS}

    return AgentIdentityClaims(
        agent_id=agent_id,
        spiffe_id=spiffe_id,
        issuer=iss,
        subject=sub,
        audience=audience,
        expires_at=int(payload.get("exp", 0)),
        issued_at=int(payload.get("iat", 0)),
        scopes=scopes,
        delegated=delegated,
        delegated_by=delegated_by,
        custom_claims=custom_claims,
    )


# ── Token Validation ─────────────────────────────────────────────────────


@dataclass
class TokenValidationError:
    code: str  # missing_token, malformed_token, untrusted_issuer, invalid_audience, expired_token, token_too_long_lived, untrusted_domain, verification_failed
    message: str


def validate_claims(
    claims: AgentIdentityClaims,
    config: AgentIdentityConfig,
) -> TokenValidationError | None:
    """Validate extracted claims against the identity config. Returns None if valid."""
    now = int(time.time())
    skew = config.clock_skew_seconds

    if claims.issuer not in config.trusted_issuers:
        return TokenValidationError(
            code="untrusted_issuer",
            message=f'Issuer "{claims.issuer}" is not trusted.',
        )

    if claims.audience:
        aud_match = any(a in config.audience for a in claims.audience)
        if not aud_match:
            return TokenValidationError(
                code="invalid_audience",
                message="Token audience does not match any expected audience.",
            )

    if claims.expires_at and claims.expires_at + skew < now:
        return TokenValidationError(
            code="expired_token",
            message="Token has expired.",
        )

    max_lifetime = config.max_lifetime_seconds
    if claims.issued_at and claims.expires_at:
        lifetime = claims.expires_at - claims.issued_at
        if lifetime > max_lifetime:
            return TokenValidationError(
                code="token_too_long_lived",
                message=f"Token lifetime {lifetime}s exceeds maximum {max_lifetime}s.",
            )

    if claims.spiffe_id and config.trusted_domains:
        if not is_spiffe_trusted(claims.spiffe_id, config.trusted_domains):
            return TokenValidationError(
                code="untrusted_domain",
                message=f'SPIFFE trust domain "{claims.spiffe_id.trust_domain}" is not trusted.',
            )

    return None


# ── Authorization ────────────────────────────────────────────────────────


def _glob_match(pattern: str, value: str) -> bool:
    """Simple glob match: supports * wildcard."""
    regex_str = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
    return bool(re.match(regex_str, value))


def evaluate_authz(
    claims: AgentIdentityClaims,
    context: AuthzContext,
    policies: list[AgentAuthzPolicyRuntime],
    default_policy: str = "deny",
) -> AuthzResult:
    """Evaluate authorization policies against verified claims."""
    for policy in policies:
        # Match agent pattern
        if policy.agent_pattern and not _glob_match(policy.agent_pattern, claims.agent_id):
            continue

        # Match trust domain
        if policy.trust_domains and claims.spiffe_id:
            if claims.spiffe_id.trust_domain not in policy.trust_domains:
                continue

        # Match method
        if policy.methods and context.method.upper() not in policy.methods:
            continue

        # Match path
        if policy.paths:
            if not any(_glob_match(p, context.path) for p in policy.paths):
                continue

        # Check delegation
        if policy.allow_delegated is False and claims.delegated:
            return AuthzResult(
                allowed=False,
                matched_policy=policy.name,
                denied_reason="Delegated access not allowed by policy.",
            )

        # Check required scopes
        if policy.required_scopes:
            missing = [s for s in policy.required_scopes if s not in claims.scopes]
            if missing:
                return AuthzResult(
                    allowed=False,
                    matched_policy=policy.name,
                    denied_reason=f"Missing required scopes: {', '.join(missing)}",
                )

        # Custom evaluator
        if policy.evaluate and not policy.evaluate(claims, context):
            return AuthzResult(
                allowed=False,
                matched_policy=policy.name,
                denied_reason="Custom policy evaluation denied access.",
            )

        return AuthzResult(allowed=True, matched_policy=policy.name)

    # No policy matched
    return AuthzResult(
        allowed=(default_policy == "allow"),
        denied_reason="No matching authorization policy." if default_policy == "deny" else None,
    )


# ── Audit Event ──────────────────────────────────────────────────────────


@dataclass
class AgentIdentityAuditEvent:
    type: str
    timestamp: str
    agent_id: str
    issuer: str
    delegated: bool
    scopes: list[str]
    method: str
    path: str
    authz_result: AuthzResult
    spiffe_id: str | None = None
    delegated_by: str | None = None


def build_audit_event(
    claims: AgentIdentityClaims,
    context: AuthzContext,
    authz_result: AuthzResult,
) -> AgentIdentityAuditEvent:
    """Build an audit event from identity verification results."""
    return AgentIdentityAuditEvent(
        type="agent_identity",
        timestamp=datetime.now(timezone.utc).isoformat(),
        agent_id=claims.agent_id,
        spiffe_id=claims.spiffe_id.raw if claims.spiffe_id else None,
        issuer=claims.issuer,
        delegated=claims.delegated,
        delegated_by=claims.delegated_by,
        scopes=claims.scopes,
        method=context.method,
        path=context.path,
        authz_result=authz_result,
    )


# ── Token Extraction ────────────────────────────────────────────────────


def extract_token_from_header(raw_header: str | None, prefix: str) -> str | None:
    """Extract a bearer token from a raw Authorization header value."""
    if not raw_header:
        return None
    if raw_header.startswith(prefix + " "):
        return raw_header[len(prefix) + 1 :]
    return raw_header


# ── Core Identity Check ────────────────────────────────────────────────


@dataclass
class IdentityResult:
    """Result of a core identity verification check."""

    ok: bool
    claims: AgentIdentityClaims | None = None
    error_body: dict[str, Any] | None = None
    error_status: int = 401


def check_identity(
    token: str | None,
    config: AgentIdentityConfig,
    decoded_claims: AgentIdentityClaims | None = None,
    method: str = "",
    path: str = "",
    headers: dict[str, Any] | None = None,
    runtime_policies: list[AgentAuthzPolicyRuntime] | None = None,
) -> IdentityResult:
    """Core identity check — framework-agnostic.

    Either provide ``decoded_claims`` (from an async verifier) or just a
    ``token`` (will be decoded via :func:`decode_jwt_claims`).

    Returns an :class:`IdentityResult` that adapters use to build
    framework-specific responses.
    """
    from agent_layer.errors import format_error
    from agent_layer.types import AgentErrorOptions

    def _err(code: str, message: str, status: int) -> IdentityResult:
        envelope = format_error(AgentErrorOptions(code=code, message=message, status=status))
        return IdentityResult(
            ok=False,
            error_body={"error": envelope.model_dump(exclude_none=True)},
            error_status=status,
        )

    if token is None:
        return _err("agent_identity_required", "Agent identity token is required.", 401)

    claims = decoded_claims
    if claims is None:
        payload = decode_jwt_claims(token)
        if payload is None:
            return _err("malformed_token", "Agent identity token is malformed.", 401)
        claims = extract_claims(payload)

    validation_error = validate_claims(claims, config)
    if validation_error:
        status = 401 if validation_error.code == "expired_token" else 403
        return _err(validation_error.code, validation_error.message, status)

    if runtime_policies:
        context = AuthzContext(method=method, path=path, headers=headers or {})
        result = evaluate_authz(claims, context, runtime_policies, config.default_policy)
        if not result.allowed:
            return _err(
                "agent_unauthorized",
                result.denied_reason or "Agent is not authorized.",
                403,
            )

    return IdentityResult(ok=True, claims=claims)
