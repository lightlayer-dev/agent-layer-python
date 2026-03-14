"""FastAPI middleware for agent-layer."""

from agent_layer.fastapi.errors import agent_errors_middleware, not_found_handler
from agent_layer.fastapi.rate_limits import rate_limits_middleware
from agent_layer.fastapi.llms_txt import llms_txt_routes
from agent_layer.fastapi.discovery import discovery_routes
from agent_layer.fastapi.auth import agent_auth_routes
from agent_layer.fastapi.meta import agent_meta_middleware
from agent_layer.fastapi.app import configure_agent_layer

__all__ = [
    "agent_errors_middleware",
    "not_found_handler",
    "rate_limits_middleware",
    "llms_txt_routes",
    "discovery_routes",
    "agent_auth_routes",
    "agent_meta_middleware",
    "configure_agent_layer",
]
