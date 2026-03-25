"""API key authentication dependency for FastAPI."""

from __future__ import annotations

from typing import Callable

from fastapi import HTTPException, Request

from agent_layer.api_keys import ApiKeyStore, ScopedApiKey, has_scope, validate_api_key


def api_key_dependency(
    store: ApiKeyStore,
    required_scopes: list[str] | None = None,
) -> Callable:
    """Create a FastAPI dependency that validates API keys.

    Extracts the key from the ``Authorization: Bearer <key>`` header.
    """

    async def _dependency(request: Request) -> ScopedApiKey:
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Missing API key")

        raw_key = auth.split(" ", 1)[1]
        result = await validate_api_key(store, raw_key)

        if not result.valid:
            status = 401 if result.error == "invalid_api_key" else 403
            raise HTTPException(status_code=status, detail=result.error)

        assert result.key is not None
        if required_scopes and not has_scope(result.key, required_scopes):
            raise HTTPException(status_code=403, detail="insufficient_scopes")

        return result.key

    return _dependency
