"""Scoped API key authentication."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable


# ── Types ────────────────────────────────────────────────────────────────


@dataclass
class ScopedApiKey:
    """A scoped API key with permissions and metadata."""

    key_id: str
    company_id: str
    user_id: str
    scopes: list[str]
    expires_at: datetime | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class ApiKeyValidationResult:
    """Result of validating an API key."""

    valid: bool
    key: ScopedApiKey | None = None
    error: str | None = None


@dataclass
class CreateApiKeyOptions:
    """Options for creating a new API key."""

    company_id: str
    user_id: str
    scopes: list[str]
    expires_at: datetime | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class CreateApiKeyResult:
    """Result of creating a new API key."""

    raw_key: str
    key: ScopedApiKey


# ── ApiKeyStore Protocol ─────────────────────────────────────────────────


@runtime_checkable
class ApiKeyStore(Protocol):
    """Protocol for resolving raw API key strings to ScopedApiKey objects."""

    async def resolve(self, raw_key: str) -> ScopedApiKey | None: ...


# ── MemoryApiKeyStore ────────────────────────────────────────────────────


class MemoryApiKeyStore:
    """In-memory API key store for development and testing."""

    def __init__(self) -> None:
        self._keys: dict[str, ScopedApiKey] = {}

    async def resolve(self, raw_key: str) -> ScopedApiKey | None:
        return self._keys.get(raw_key)

    def set(self, raw_key: str, key: ScopedApiKey) -> None:
        """Store a key mapping."""
        self._keys[raw_key] = key

    def delete(self, raw_key: str) -> None:
        """Remove a key mapping."""
        self._keys.pop(raw_key, None)

    @property
    def size(self) -> int:
        """Number of stored keys."""
        return len(self._keys)


# ── Key generation ───────────────────────────────────────────────────────


def create_api_key(
    store: MemoryApiKeyStore,
    opts: CreateApiKeyOptions,
) -> CreateApiKeyResult:
    """Generate a new scoped API key and store it.

    Key format: ``al_`` prefix + 32 random hex characters.
    """
    raw_key = f"al_{secrets.token_hex(16)}"
    key_id = secrets.token_hex(8)

    key = ScopedApiKey(
        key_id=key_id,
        company_id=opts.company_id,
        user_id=opts.user_id,
        scopes=list(opts.scopes),
        expires_at=opts.expires_at,
        metadata=opts.metadata,
    )

    store.set(raw_key, key)
    return CreateApiKeyResult(raw_key=raw_key, key=key)


# ── Validation ───────────────────────────────────────────────────────────


async def validate_api_key(
    store: ApiKeyStore,
    raw_key: str,
) -> ApiKeyValidationResult:
    """Validate a raw API key string against a store.

    Checks existence and expiry.
    """
    key = await store.resolve(raw_key)

    if key is None:
        return ApiKeyValidationResult(valid=False, error="invalid_api_key")

    if key.expires_at is not None:
        now = datetime.now(timezone.utc)
        expires = (
            key.expires_at if key.expires_at.tzinfo else key.expires_at.replace(tzinfo=timezone.utc)
        )
        if expires <= now:
            return ApiKeyValidationResult(valid=False, error="api_key_expired")

    return ApiKeyValidationResult(valid=True, key=key)


# ── Scope checking ───────────────────────────────────────────────────────


def has_scope(key: ScopedApiKey, required: str | list[str]) -> bool:
    """Check if a scoped API key has the required scope(s).

    Supports wildcard ``*`` which grants all scopes.
    """
    if "*" in key.scopes:
        return True

    required_scopes = required if isinstance(required, list) else [required]
    return all(scope in key.scopes for scope in required_scopes)
