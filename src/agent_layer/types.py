"""Shared types for agent-layer."""

from __future__ import annotations

from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, Field


# ── Error Envelope ──────────────────────────────────────────────────────


class AgentErrorEnvelope(BaseModel):
    type: str
    code: str
    message: str
    status: int
    is_retriable: bool
    retry_after: int | None = None
    param: str | None = None
    docs_url: str | None = None


class AgentErrorOptions(BaseModel):
    code: str
    message: str
    type: str | None = None
    status: int = 500
    is_retriable: bool | None = None
    retry_after: int | None = None
    param: str | None = None
    docs_url: str | None = None


# ── Rate Limiting ───────────────────────────────────────────────────────


class RateLimitStore(Protocol):
    async def increment(self, key: str, window_ms: int) -> int: ...
    async def get(self, key: str) -> int: ...
    async def reset(self, key: str) -> None: ...


class RateLimitConfig(BaseModel):
    max: int
    window_ms: int = 60_000
    key_fn: Callable[[Any], str] | None = None
    store: Any = None  # RateLimitStore — can't use Protocol in pydantic

    model_config = {"arbitrary_types_allowed": True}


class RateLimitResult(BaseModel):
    allowed: bool
    limit: int
    remaining: int
    reset_ms: int
    retry_after: int | None = None


# ── LLMs.txt ────────────────────────────────────────────────────────────


class LlmsTxtSection(BaseModel):
    title: str
    content: str


class LlmsTxtConfig(BaseModel):
    title: str
    description: str | None = None
    sections: list[LlmsTxtSection] = Field(default_factory=list)


class RouteParameter(BaseModel):
    name: str
    location: Literal["path", "query", "header", "body"]  # 'in' is reserved in Python
    required: bool = False
    description: str | None = None


class RouteMetadata(BaseModel):
    method: str
    path: str
    summary: str | None = None
    description: str | None = None
    parameters: list[RouteParameter] = Field(default_factory=list)


# ── Discovery ───────────────────────────────────────────────────────────


class AIManifestAuth(BaseModel):
    type: Literal["oauth2", "api_key", "bearer", "none"]
    authorization_url: str | None = None
    token_url: str | None = None
    scopes: dict[str, str] | None = None


class AIManifestContact(BaseModel):
    email: str | None = None
    url: str | None = None


class AIManifest(BaseModel):
    name: str
    description: str | None = None
    openapi_url: str | None = None
    llms_txt_url: str | None = None
    auth: AIManifestAuth | None = None
    contact: AIManifestContact | None = None
    capabilities: list[str] = Field(default_factory=list)


class DiscoveryConfig(BaseModel):
    manifest: AIManifest
    openapi_spec: dict[str, Any] | None = None


# ── Agent Meta ──────────────────────────────────────────────────────────


class AgentMetaConfig(BaseModel):
    agent_id_attribute: str = "data-agent-id"
    aria_landmarks: bool = True
    meta_tags: dict[str, str] = Field(default_factory=dict)


# ── Agent Auth ──────────────────────────────────────────────────────────


class AgentAuthConfig(BaseModel):
    issuer: str | None = None
    authorization_url: str | None = None
    token_url: str | None = None
    scopes: dict[str, str] = Field(default_factory=dict)
    realm: str = "agent-layer"


# ── Top-level Config ────────────────────────────────────────────────────


class AnalyticsConfigRef(BaseModel):
    """Lightweight reference config for analytics in AgentLayerConfig.

    Uses the same fields as agent_layer.analytics.AnalyticsConfig but
    avoids circular imports. The configure_agent_layer function converts
    this to the full AnalyticsConfig internally.
    """

    endpoint: str | None = None
    api_key: str | None = None
    buffer_size: int = 50
    flush_interval_seconds: float = 30.0
    track_all: bool = False

    model_config = {"arbitrary_types_allowed": True}


class AgentLayerConfig(BaseModel):
    errors: bool = True
    rate_limit: RateLimitConfig | None = None
    llms_txt: LlmsTxtConfig | None = None
    discovery: DiscoveryConfig | None = None
    agent_meta: AgentMetaConfig | None = None
    agent_auth: AgentAuthConfig | None = None
    analytics: AnalyticsConfigRef | None = None

    model_config = {"arbitrary_types_allowed": True}
