"""
API Keys — Key generation, validation, scopes, and pluggable store.

Provides a lightweight API key management system with a pluggable
storage backend and scope-based access control.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ScopedApiKey:
    """A stored API key with identity and scopes."""

    key_id: str
    key: str
    scopes: list[str] = field(default_factory=list)
    expires_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ApiKeyStore(Protocol):
    """Protocol for API key storage backends."""

    async def resolve(self, key: str) -> ScopedApiKey | None: ...
    async def set(self, key_data: ScopedApiKey) -> None: ...
    async def delete(self, key: str) -> None: ...


class MemoryApiKeyStore:
    """In-memory API key store for development/testing."""

    def __init__(self) -> None:
        self._keys: dict[str, ScopedApiKey] = {}

    async def resolve(self, key: str) -> ScopedApiKey | None:
        return self._keys.get(key)

    async def set(self, key_data: ScopedApiKey) -> None:
        self._keys[key_data.key] = key_data

    async def delete(self, key: str) -> None:
        self._keys.pop(key, None)

    @property
    def size(self) -> int:
        return len(self._keys)


@dataclass
class CreateApiKeyOptions:
    """Options for creating a new API key."""

    scopes: list[str] = field(default_factory=list)
    expires_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CreateApiKeyResult:
    """Result of creating a new API key."""

    key: str
    key_id: str
    scopes: list[str]
    expires_at: float | None = None


@dataclass
class ApiKeyValidationResult:
    """Result of validating an API key."""

    valid: bool
    key: ScopedApiKey | None = None
    error: str | None = None


@dataclass
class ApiKeyConfig:
    """Configuration for API key middleware."""

    store: MemoryApiKeyStore | None = None
    header_name: str = "X-Agent-Key"


def create_api_key(options: CreateApiKeyOptions | None = None) -> CreateApiKeyResult:
    """Generate a new API key with the al_ prefix.

    Format: al_ + 32 random hex characters (16 bytes).
    """
    opts = options or CreateApiKeyOptions()
    raw = secrets.token_hex(16)
    key = f"al_{raw}"
    key_id = secrets.token_hex(8)

    return CreateApiKeyResult(
        key=key,
        key_id=key_id,
        scopes=opts.scopes,
        expires_at=opts.expires_at,
    )


import time


async def validate_api_key(
    key: str,
    store: MemoryApiKeyStore | ApiKeyStore,
) -> ApiKeyValidationResult:
    """Validate an API key against the store.

    Checks key existence and expiration.
    """
    stored = await store.resolve(key)
    if stored is None:
        return ApiKeyValidationResult(valid=False, error="invalid_api_key")

    if stored.expires_at is not None and time.time() * 1000 > stored.expires_at:
        return ApiKeyValidationResult(valid=False, error="api_key_expired")

    return ApiKeyValidationResult(valid=True, key=stored)


def has_scope(key: ScopedApiKey, required: str | list[str]) -> bool:
    """Check if a key has the required scope(s).

    Wildcard "*" grants access to all scopes.
    """
    if "*" in key.scopes:
        return True

    required_list = [required] if isinstance(required, str) else required
    return all(s in key.scopes for s in required_list)
