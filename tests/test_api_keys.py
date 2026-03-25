"""Tests for scoped API key authentication."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent_layer.api_keys import (
    CreateApiKeyOptions,
    MemoryApiKeyStore,
    ScopedApiKey,
    create_api_key,
    has_scope,
    validate_api_key,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


def _make_store_and_key(**overrides):
    store = MemoryApiKeyStore()
    opts = CreateApiKeyOptions(
        company_id="comp_1",
        user_id="user_1",
        scopes=["read", "write"],
        **overrides,
    )
    result = create_api_key(store, opts)
    return store, result


# ── Tests: create_api_key ────────────────────────────────────────────────


class TestCreateApiKey:
    def test_key_has_al_prefix(self):
        _, result = _make_store_and_key()
        assert result.raw_key.startswith("al_")

    def test_raw_key_length(self):
        _, result = _make_store_and_key()
        # al_ prefix + 32 hex chars = 35
        assert len(result.raw_key) == 35

    def test_key_id_is_hex(self):
        _, result = _make_store_and_key()
        int(result.key.key_id, 16)  # should not raise

    def test_key_fields_match_options(self):
        _, result = _make_store_and_key()
        assert result.key.company_id == "comp_1"
        assert result.key.user_id == "user_1"
        assert result.key.scopes == ["read", "write"]

    def test_key_stored_in_store(self):
        store, result = _make_store_and_key()
        assert store.size == 1

    def test_optional_fields(self):
        expires = datetime(2030, 1, 1, tzinfo=timezone.utc)
        _, result = _make_store_and_key(
            expires_at=expires, metadata={"env": "test"}
        )
        assert result.key.expires_at == expires
        assert result.key.metadata == {"env": "test"}


# ── Tests: validate_api_key ──────────────────────────────────────────────


class TestValidateApiKey:
    @pytest.mark.asyncio
    async def test_valid_key(self):
        store, result = _make_store_and_key()
        validation = await validate_api_key(store, result.raw_key)
        assert validation.valid is True
        assert validation.key is not None
        assert validation.key.key_id == result.key.key_id

    @pytest.mark.asyncio
    async def test_invalid_key(self):
        store = MemoryApiKeyStore()
        validation = await validate_api_key(store, "al_nonexistent")
        assert validation.valid is False
        assert validation.error == "invalid_api_key"

    @pytest.mark.asyncio
    async def test_expired_key(self):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        store, result = _make_store_and_key(expires_at=past)
        validation = await validate_api_key(store, result.raw_key)
        assert validation.valid is False
        assert validation.error == "api_key_expired"

    @pytest.mark.asyncio
    async def test_not_yet_expired_key(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        store, result = _make_store_and_key(expires_at=future)
        validation = await validate_api_key(store, result.raw_key)
        assert validation.valid is True


# ── Tests: has_scope ─────────────────────────────────────────────────────


class TestHasScope:
    def test_single_scope_present(self):
        key = ScopedApiKey(
            key_id="k1", company_id="c", user_id="u", scopes=["read", "write"]
        )
        assert has_scope(key, "read") is True

    def test_single_scope_missing(self):
        key = ScopedApiKey(
            key_id="k1", company_id="c", user_id="u", scopes=["read"]
        )
        assert has_scope(key, "write") is False

    def test_multiple_scopes_all_present(self):
        key = ScopedApiKey(
            key_id="k1", company_id="c", user_id="u", scopes=["read", "write", "delete"]
        )
        assert has_scope(key, ["read", "write"]) is True

    def test_multiple_scopes_some_missing(self):
        key = ScopedApiKey(
            key_id="k1", company_id="c", user_id="u", scopes=["read"]
        )
        assert has_scope(key, ["read", "write"]) is False

    def test_wildcard_grants_all(self):
        key = ScopedApiKey(
            key_id="k1", company_id="c", user_id="u", scopes=["*"]
        )
        assert has_scope(key, "anything") is True
        assert has_scope(key, ["read", "write", "admin"]) is True

    def test_empty_required(self):
        key = ScopedApiKey(
            key_id="k1", company_id="c", user_id="u", scopes=["read"]
        )
        assert has_scope(key, []) is True


# ── Tests: MemoryApiKeyStore ─────────────────────────────────────────────


class TestMemoryApiKeyStore:
    @pytest.mark.asyncio
    async def test_resolve_returns_none_for_unknown(self):
        store = MemoryApiKeyStore()
        assert await store.resolve("unknown") is None

    def test_set_and_delete(self):
        store = MemoryApiKeyStore()
        key = ScopedApiKey(
            key_id="k1", company_id="c", user_id="u", scopes=["read"]
        )
        store.set("raw", key)
        assert store.size == 1
        store.delete("raw")
        assert store.size == 0

    def test_delete_nonexistent_is_noop(self):
        store = MemoryApiKeyStore()
        store.delete("nope")  # should not raise
