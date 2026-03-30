"""
OAuth2 — Authorization server metadata, token endpoint helpers.

Provides PKCE support, token validation, authorization URL building,
and RFC 8414 authorization server metadata generation.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class OAuth2Config:
    """OAuth2 configuration."""

    client_id: str
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    scopes: list[str] = field(default_factory=list)
    issuer: str | None = None
    audience: str | list[str] | None = None
    redirect_uri: str | None = None


@dataclass
class TokenResponse:
    """OAuth2 token response."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    scope: str | None = None


@dataclass
class PKCEPair:
    """PKCE code verifier and challenge pair."""

    code_verifier: str
    code_challenge: str


@dataclass
class DecodedAccessToken:
    """Parsed JWT claims from an access token."""

    sub: str | None = None
    iss: str | None = None
    aud: str | list[str] | None = None
    exp: float | None = None
    iat: float | None = None
    scope: str | None = None
    scopes: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenValidationResult:
    """Result of token validation."""

    valid: bool
    claims: DecodedAccessToken | None = None
    error: str | None = None


@dataclass
class OAuth2MiddlewareConfig:
    """Configuration for OAuth2 middleware."""

    oauth2: OAuth2Config
    required_scopes: list[str] = field(default_factory=list)
    clock_skew_seconds: int = 30
    custom_validator: Callable[[str], Awaitable[dict[str, Any]]] | None = None


class OAuth2TokenError(Exception):
    """OAuth2 token error."""

    def __init__(self, error: str, description: str | None = None) -> None:
        super().__init__(description or error)
        self.error = error
        self.description = description


# ── PKCE ─────────────────────────────────────────────────────────────────

def generate_code_verifier() -> str:
    """Generate a cryptographically random PKCE code verifier."""
    return secrets.token_urlsafe(32)


def compute_code_challenge(verifier: str) -> str:
    """Compute S256 code challenge from verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def generate_pkce() -> PKCEPair:
    """Generate a PKCE code verifier and challenge pair."""
    verifier = generate_code_verifier()
    challenge = compute_code_challenge(verifier)
    return PKCEPair(code_verifier=verifier, code_challenge=challenge)


# ── Authorization URL ────────────────────────────────────────────────────

def build_authorization_url(
    config: OAuth2Config,
    state: str | None = None,
    pkce: PKCEPair | None = None,
) -> str:
    """Build an OAuth2 authorization endpoint URL."""
    if not config.authorization_endpoint:
        raise ValueError("authorization_endpoint is required")

    params: dict[str, str] = {
        "response_type": "code",
        "client_id": config.client_id,
    }

    if config.redirect_uri:
        params["redirect_uri"] = config.redirect_uri
    if config.scopes:
        params["scope"] = " ".join(config.scopes)
    if state:
        params["state"] = state
    if pkce:
        params["code_challenge"] = pkce.code_challenge
        params["code_challenge_method"] = "S256"

    from urllib.parse import urlencode
    return f"{config.authorization_endpoint}?{urlencode(params)}"


# ── Token Validation ─────────────────────────────────────────────────────

def _base64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def _decode_jwt(token: str) -> dict[str, Any] | None:
    """Decode JWT payload without signature verification."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        return json.loads(_base64url_decode(parts[1]))
    except Exception:
        return None


def extract_bearer_token(header: str | None) -> str | None:
    """Extract a Bearer token from an Authorization header."""
    if not header or not header.startswith("Bearer "):
        return None
    return header[7:]


def validate_access_token(
    token: str,
    config: OAuth2Config,
    clock_skew: int = 30,
) -> TokenValidationResult:
    """Validate a JWT access token.

    Checks expiration, issuer, audience, and extracts scopes.
    """
    payload = _decode_jwt(token)
    if payload is None:
        return TokenValidationResult(valid=False, error="malformed_token")

    # Extract scopes from various formats
    scopes: list[str] = []
    if "scope" in payload and isinstance(payload["scope"], str):
        scopes = payload["scope"].split()
    elif "scopes" in payload and isinstance(payload["scopes"], list):
        scopes = payload["scopes"]
    elif "scp" in payload and isinstance(payload["scp"], list):
        scopes = payload["scp"]

    # Parse audience
    aud = payload.get("aud")
    aud_list = [aud] if isinstance(aud, str) else (aud if isinstance(aud, list) else [])

    claims = DecodedAccessToken(
        sub=payload.get("sub"),
        iss=payload.get("iss"),
        aud=payload.get("aud"),
        exp=payload.get("exp"),
        iat=payload.get("iat"),
        scope=payload.get("scope") if isinstance(payload.get("scope"), str) else None,
        scopes=scopes,
        raw=payload,
    )

    now = time.time()

    # Check expiration
    if claims.exp is not None and now > claims.exp + clock_skew:
        return TokenValidationResult(valid=False, claims=claims, error="token_expired")

    # Check issuer
    if config.issuer and claims.iss != config.issuer:
        return TokenValidationResult(valid=False, claims=claims, error="invalid_issuer")

    # Check audience
    if config.audience:
        expected = [config.audience] if isinstance(config.audience, str) else config.audience
        if not any(a in aud_list for a in expected):
            return TokenValidationResult(valid=False, claims=claims, error="invalid_audience")

    return TokenValidationResult(valid=True, claims=claims)


# ── OAuth2 Metadata ──────────────────────────────────────────────────────

def build_oauth2_metadata(
    issuer: str,
    authorization_endpoint: str | None = None,
    token_endpoint: str | None = None,
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    """Generate RFC 8414 authorization server metadata."""
    metadata: dict[str, Any] = {"issuer": issuer}
    if authorization_endpoint:
        metadata["authorization_endpoint"] = authorization_endpoint
    if token_endpoint:
        metadata["token_endpoint"] = token_endpoint
    metadata["response_types_supported"] = ["code"]
    metadata["grant_types_supported"] = ["authorization_code", "refresh_token"]
    metadata["code_challenge_methods_supported"] = ["S256"]
    if scopes:
        metadata["scopes_supported"] = scopes
    return metadata


# ── OAuth2 Handler ───────────────────────────────────────────────────────

async def handle_oauth2(
    raw_header: str | None,
    config: OAuth2MiddlewareConfig,
) -> dict[str, Any]:
    """Framework-agnostic OAuth2 middleware handler.

    Returns {"valid": True, "claims": ...} or
    {"valid": False, "status": 401|403, "error": ..., "www_authenticate": ...}.
    """
    token = extract_bearer_token(raw_header)
    if not token:
        www_auth = 'Bearer'
        if config.oauth2.authorization_endpoint:
            www_auth += f', docs_url="{config.oauth2.authorization_endpoint}"'
        return {
            "valid": False,
            "status": 401,
            "error": "missing_token",
            "message": "Missing or invalid Authorization header",
            "www_authenticate": www_auth,
        }

    # Use custom validator if provided
    if config.custom_validator:
        try:
            payload = await config.custom_validator(token)
            scopes: list[str] = []
            if "scope" in payload and isinstance(payload["scope"], str):
                scopes = payload["scope"].split()
            elif "scopes" in payload and isinstance(payload["scopes"], list):
                scopes = payload["scopes"]
            elif "scp" in payload and isinstance(payload["scp"], list):
                scopes = payload["scp"]

            claims = DecodedAccessToken(
                sub=payload.get("sub"),
                iss=payload.get("iss"),
                aud=payload.get("aud"),
                exp=payload.get("exp"),
                iat=payload.get("iat"),
                scopes=scopes,
                raw=payload,
            )
        except Exception:
            return {
                "valid": False,
                "status": 401,
                "error": "invalid_token",
                "message": "Token validation failed",
                "www_authenticate": "Bearer",
            }
    else:
        result = validate_access_token(token, config.oauth2, config.clock_skew_seconds)
        if not result.valid:
            status = 401 if result.error in ("malformed_token", "token_expired") else 403
            return {
                "valid": False,
                "status": status,
                "error": result.error,
                "message": f"Token validation failed: {result.error}",
                "www_authenticate": "Bearer",
            }
        claims = result.claims  # type: ignore

    # Check required scopes
    if config.required_scopes:
        if "*" not in claims.scopes:
            if not all(s in claims.scopes for s in config.required_scopes):
                return {
                    "valid": False,
                    "status": 403,
                    "error": "insufficient_scope",
                    "message": f"Required scopes: {', '.join(config.required_scopes)}",
                    "www_authenticate": f'Bearer scope="{" ".join(config.required_scopes)}"',
                }

    return {"valid": True, "claims": claims}
