"""API key authentication decorator for Flask."""

from __future__ import annotations

import functools
from typing import Any, Callable

from flask import g, jsonify, request

from agent_layer.api_keys import ApiKeyStore, ScopedApiKey, has_scope, validate_api_key
from agent_layer.async_utils import run_async_in_sync


def require_api_key(
    store: ApiKeyStore,
    required_scopes: list[str] | None = None,
) -> Callable:
    """Create a Flask decorator that validates API keys.

    Extracts the key from the ``Authorization: Bearer <key>`` header.
    Sets ``g.api_key`` to the resolved :class:`ScopedApiKey` on success.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            auth = request.headers.get("authorization", "")
            if not auth.lower().startswith("bearer "):
                return jsonify({"error": "Missing API key"}), 401

            raw_key = auth.split(" ", 1)[1]
            result = run_async_in_sync(validate_api_key(store, raw_key))

            if not result.valid:
                status = 401 if result.error == "invalid_api_key" else 403
                return jsonify({"error": result.error}), status

            assert result.key is not None
            if required_scopes and not has_scope(result.key, required_scopes):
                return jsonify({"error": "insufficient_scopes"}), 403

            g.api_key = result.key
            return fn(*args, **kwargs)

        return wrapper

    return decorator
