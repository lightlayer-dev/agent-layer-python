"""API key authentication for Django."""

from __future__ import annotations

import functools
from typing import Any, Callable

from django.http import JsonResponse

from agent_layer.api_keys import ApiKeyStore, has_scope, validate_api_key
from agent_layer.async_utils import run_async_in_sync


def require_api_key(
    store: ApiKeyStore,
    required_scopes: list[str] | None = None,
) -> Callable:
    """Create a Django view decorator that validates API keys.

    Extracts the key from the ``Authorization: Bearer <key>`` header.
    Sets ``request.api_key`` to the resolved :class:`ScopedApiKey` on success.
    """

    def decorator(view_fn: Callable) -> Callable:
        @functools.wraps(view_fn)
        def wrapper(request: Any, *args: Any, **kwargs: Any) -> Any:
            auth = request.META.get("HTTP_AUTHORIZATION", "")
            if not auth.lower().startswith("bearer "):
                return JsonResponse({"error": "Missing API key"}, status=401)

            raw_key = auth.split(" ", 1)[1]
            result = run_async_in_sync(validate_api_key(store, raw_key))

            if not result.valid:
                status = 401 if result.error == "invalid_api_key" else 403
                return JsonResponse({"error": result.error}, status=status)

            assert result.key is not None
            if required_scopes and not has_scope(result.key, required_scopes):
                return JsonResponse({"error": "insufficient_scopes"}, status=403)

            request.api_key = result.key
            return view_fn(request, *args, **kwargs)

        return wrapper

    return decorator
