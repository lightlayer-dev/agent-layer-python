"""Tests for API keys module."""

import time

import pytest

from agent_layer.core.api_keys import (
    CreateApiKeyOptions,
    MemoryApiKeyStore,
    ScopedApiKey,
    create_api_key,
    has_scope,
    validate_api_key,
)


class TestCreateApiKey:
    def test_generates_key_with_prefix(self):
        result = create_api_key()
        assert result.key.startswith("al_")
        assert len(result.key) == 35  # "al_" + 32 hex chars

    def test_generates_unique_keys(self):
        k1 = create_api_key()
        k2 = create_api_key()
        assert k1.key != k2.key
        assert k1.key_id != k2.key_id

    def test_with_scopes(self):
        result = create_api_key(CreateApiKeyOptions(scopes=["read", "write"]))
        assert result.scopes == ["read", "write"]

    def test_with_expiration(self):
        result = create_api_key(CreateApiKeyOptions(expires_at=99999999.0))
        assert result.expires_at == 99999999.0


class TestMemoryApiKeyStore:
    @pytest.mark.asyncio
    async def test_set_and_resolve(self):
        store = MemoryApiKeyStore()
        key = ScopedApiKey(key_id="k1", key="al_test123", scopes=["read"])
        await store.set(key)
        resolved = await store.resolve("al_test123")
        assert resolved is not None
        assert resolved.key_id == "k1"

    @pytest.mark.asyncio
    async def test_resolve_missing(self):
        store = MemoryApiKeyStore()
        assert await store.resolve("nonexistent") is None

    @pytest.mark.asyncio
    async def test_delete(self):
        store = MemoryApiKeyStore()
        key = ScopedApiKey(key_id="k1", key="al_test123")
        await store.set(key)
        await store.delete("al_test123")
        assert await store.resolve("al_test123") is None

    @pytest.mark.asyncio
    async def test_size(self):
        store = MemoryApiKeyStore()
        assert store.size == 0
        await store.set(ScopedApiKey(key_id="k1", key="al_a"))
        assert store.size == 1


class TestValidateApiKey:
    @pytest.mark.asyncio
    async def test_valid_key(self):
        store = MemoryApiKeyStore()
        await store.set(ScopedApiKey(key_id="k1", key="al_test", scopes=["read"]))
        result = await validate_api_key("al_test", store)
        assert result.valid is True
        assert result.key is not None

    @pytest.mark.asyncio
    async def test_invalid_key(self):
        store = MemoryApiKeyStore()
        result = await validate_api_key("al_nonexistent", store)
        assert result.valid is False
        assert result.error == "invalid_api_key"

    @pytest.mark.asyncio
    async def test_expired_key(self):
        store = MemoryApiKeyStore()
        await store.set(ScopedApiKey(key_id="k1", key="al_expired", expires_at=1.0))
        result = await validate_api_key("al_expired", store)
        assert result.valid is False
        assert result.error == "api_key_expired"


class TestHasScope:
    def test_has_scope(self):
        key = ScopedApiKey(key_id="k1", key="test", scopes=["read", "write"])
        assert has_scope(key, "read") is True

    def test_missing_scope(self):
        key = ScopedApiKey(key_id="k1", key="test", scopes=["read"])
        assert has_scope(key, "write") is False

    def test_wildcard(self):
        key = ScopedApiKey(key_id="k1", key="test", scopes=["*"])
        assert has_scope(key, "anything") is True

    def test_multiple_required(self):
        key = ScopedApiKey(key_id="k1", key="test", scopes=["read", "write"])
        assert has_scope(key, ["read", "write"]) is True
        assert has_scope(key, ["read", "admin"]) is False
