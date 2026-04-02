"""OAuth2/PKCE routes and middleware for Flask."""

from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable

from flask import Blueprint, jsonify, request

from agent_layer.oauth2 import OAuth2Config, build_oauth2_metadata
from agent_layer.oauth2_handler import OAuth2MiddlewareConfig, handle_oauth2


def oauth2_blueprint(config: OAuth2Config) -> Blueprint:
    """Create a Flask blueprint exposing OAuth2 metadata for agents."""
    bp = Blueprint("oauth2", __name__)

    @bp.route("/.well-known/oauth2-metadata")
    def oauth2_metadata():
        return jsonify(build_oauth2_metadata(config))

    return bp


def require_token(
    config: OAuth2Config,
    required_scopes: list[str] | None = None,
    clock_skew_seconds: int = 30,
) -> Callable:
    """Flask decorator that validates Bearer tokens.

    Usage::

        @app.route("/protected")
        @require_token(config, required_scopes=["read"])
        def protected(oauth2_token: DecodedAccessToken):
            return f"Hello {oauth2_token.sub}"

    Injects the decoded token as the first argument to the wrapped function.
    """
    mw_config = OAuth2MiddlewareConfig(
        oauth2=config,
        required_scopes=required_scopes,
        clock_skew_seconds=clock_skew_seconds,
    )

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            authorization = request.headers.get("Authorization")

            # Run async handler in sync context
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    handle_oauth2(authorization, mw_config)
                )
            finally:
                loop.close()

            if result.passed:
                return fn(result.token, *args, **kwargs)  # type: ignore[union-attr]

            response = jsonify(result.envelope)  # type: ignore[union-attr]
            response.status_code = result.status  # type: ignore[union-attr]
            response.headers["WWW-Authenticate"] = result.www_authenticate  # type: ignore[union-attr]
            return response

        return wrapper

    return decorator
