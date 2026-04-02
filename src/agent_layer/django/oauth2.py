"""OAuth2/PKCE URL patterns and middleware for Django."""

from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable

from django.http import JsonResponse
from django.urls import path

from agent_layer.oauth2 import OAuth2Config, build_oauth2_metadata
from agent_layer.oauth2_handler import OAuth2MiddlewareConfig, handle_oauth2


def oauth2_urlpatterns(config: OAuth2Config) -> list:
    """Create Django URL patterns for OAuth2 metadata."""

    def oauth2_metadata(request):
        return JsonResponse(build_oauth2_metadata(config))

    return [
        path(
            ".well-known/oauth2-metadata",
            oauth2_metadata,
            name="oauth2_metadata",
        ),
    ]


def require_token(
    config: OAuth2Config,
    required_scopes: list[str] | None = None,
    clock_skew_seconds: int = 30,
) -> Callable:
    """Django decorator that validates Bearer tokens.

    Usage::

        @require_token(config, required_scopes=["read"])
        def protected_view(request, oauth2_token: DecodedAccessToken):
            return JsonResponse({"sub": oauth2_token.sub})

    Injects the decoded token as the second argument (after request).
    """
    mw_config = OAuth2MiddlewareConfig(
        oauth2=config,
        required_scopes=required_scopes,
        clock_skew_seconds=clock_skew_seconds,
    )

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(request: Any, *args: Any, **kwargs: Any) -> Any:
            authorization = request.META.get("HTTP_AUTHORIZATION")

            # Run async handler in sync context
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    handle_oauth2(authorization, mw_config)
                )
            finally:
                loop.close()

            if result.passed:
                return fn(request, result.token, *args, **kwargs)  # type: ignore[union-attr]

            response = JsonResponse(result.envelope, status=result.status)  # type: ignore[union-attr]
            response["WWW-Authenticate"] = result.www_authenticate  # type: ignore[union-attr]
            return response

        return wrapper

    return decorator
