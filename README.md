# agent-layer (Python)

[![CI](https://github.com/lightlayer-dev/agent-layer-python/actions/workflows/ci.yml/badge.svg)](https://github.com/lightlayer-dev/agent-layer-python/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Composable middleware that makes any Python web app AI-agent-friendly.**

Drop-in support for agent discovery, payments, identity verification, analytics, and structured errors — across **FastAPI**, **Flask**, and **Django**.

> Part of the [LightLayer](https://company.lightlayer.dev) open-source stack for agent-native infrastructure.

---

## Framework Support

| Framework | Integration Style | Status |
|-----------|------------------|--------|
| **FastAPI** | Middleware + Router | ✅ Full support |
| **Flask** | Middleware + Blueprint | ✅ Full support |
| **Django** | Middleware + URL patterns | ✅ Full support |

## Features

| Module | What it does | FastAPI | Flask | Django |
|--------|-------------|---------|-------|--------|
| **errors** | Structured error envelopes agents can parse | ✅ | ✅ | ✅ |
| **rate_limits** | `X-RateLimit-*` headers + 429 with `Retry-After` | ✅ | ✅ | ✅ |
| **llms_txt** | Auto-serve `/llms.txt` and `/llms-full.txt` | ✅ | ✅ | ✅ |
| **discovery** | `/.well-known/ai` manifest + JSON-LD | ✅ | ✅ | ✅ |
| **a2a** | `/.well-known/agent.json` — Google A2A Agent Card | ✅ | ✅ | ✅ |
| **x402** | HTTP 402 micropayments via [x402.org](https://x402.org) (USDC) | ✅ | ✅ | ✅ |
| **agent_identity** | Agent credential verification per [IETF draft-klrc-aiagent-auth](https://datatracker.ietf.org/doc/draft-klrc-aiagent-auth/) | ✅ | ✅ | ✅ |
| **analytics** | Detect AI agent traffic, collect telemetry, batch flush | ✅ | ✅ | ✅ |
| **auth** | OAuth discovery endpoint (`/.well-known/oauth-authorization-server`) | ✅ | ✅ | ✅ |
| **meta** | Agent capability headers (`X-Agent-Meta`) | ✅ | ✅ | ✅ |
| **mcp** | Model Context Protocol server (JSON-RPC + Streamable HTTP) | ✅ | ✅ | ✅ |
| **unified_discovery** | Single config → all discovery formats at once | ✅ | ✅ | ✅ |
| **ag_ui** | AG-UI SSE streaming ([docs.ag-ui.com](https://docs.ag-ui.com)) — CopilotKit/ADK frontend protocol | ✅ | ✅ | ✅ |

---

## Quick Start

### FastAPI

```bash
pip install agent-layer[fastapi]
```

```python
from fastapi import FastAPI
from agent_layer.fastapi import configure_agent_layer
from agent_layer.types import AgentLayerConfig, RateLimitConfig, LlmsTxtConfig

app = FastAPI()

configure_agent_layer(app, AgentLayerConfig(
    rate_limit=RateLimitConfig(max=100),
    llms_txt=LlmsTxtConfig(
        title="My API",
        description="A powerful API that agents love",
    ),
))

@app.get("/items")
async def list_items():
    return [{"id": 1, "name": "Widget"}]
```

### Flask

```bash
pip install agent-layer[flask]
```

```python
from flask import Flask
from agent_layer.flask import configure_agent_layer
from agent_layer.types import AgentLayerConfig, RateLimitConfig, LlmsTxtConfig

app = Flask(__name__)

configure_agent_layer(app, AgentLayerConfig(
    rate_limit=RateLimitConfig(max=100),
    llms_txt=LlmsTxtConfig(title="My API"),
))
```

### Django

```bash
pip install agent-layer[django]
```

```python
# urls.py
from agent_layer.django import configure_agent_layer
from agent_layer.types import AgentLayerConfig, LlmsTxtConfig

urlpatterns = [
    path("admin/", admin.site.urls),
]
urlpatterns = configure_agent_layer(urlpatterns, AgentLayerConfig(
    llms_txt=LlmsTxtConfig(title="My API"),
))
```

```python
# settings.py — add middleware classes
MIDDLEWARE = [
    "agent_layer.django.errors.AgentErrorsMiddleware",
    "agent_layer.django.rate_limits.RateLimitsMiddleware",
    "agent_layer.django.meta.AgentMetaMiddleware",
    "agent_layer.django.analytics.AgentAnalyticsMiddleware",
    # ...
]
```

Your API now has structured error envelopes, rate limiting with proper headers, `/llms.txt`, and agent-discoverable endpoints.

---

## Module Usage

### Agent Errors

Standardized error envelopes that agents can parse and act on. Maps HTTP status codes to agent-friendly error types.

```python
from agent_layer.errors import format_error, not_found_error, rate_limit_error
from agent_layer.types import AgentErrorOptions

# Automatic error wrapping (via middleware)
configure_agent_layer(app, AgentLayerConfig(errors=True))  # enabled by default

# Manual error formatting
error = format_error(AgentErrorOptions(
    code="invalid_widget",
    message="Widget ID must be a positive integer",
    status=400,
))
# → { "type": "invalid_request_error", "code": "invalid_widget", ... }
```

### Rate Limits

Sliding-window rate limiting with pluggable stores and `X-RateLimit-*` headers.

```python
from agent_layer.types import RateLimitConfig

configure_agent_layer(app, AgentLayerConfig(
    rate_limit=RateLimitConfig(
        max=100,            # requests per window
        window_ms=60_000,   # 1 minute
    ),
))
```

Use standalone:

```python
from agent_layer.fastapi import rate_limits_middleware
from agent_layer.types import RateLimitConfig

rate_limits_middleware(app, RateLimitConfig(max=50, window_ms=30_000))
```

### llms.txt

Serve `/llms.txt` and `/llms-full.txt` so LLMs can understand your API.

```python
from agent_layer.types import LlmsTxtConfig, LlmsTxtSection

configure_agent_layer(app, AgentLayerConfig(
    llms_txt=LlmsTxtConfig(
        title="Widget API",
        description="CRUD operations for widgets",
        sections=[
            LlmsTxtSection(title="Authentication", content="Use Bearer tokens."),
            LlmsTxtSection(title="Pagination", content="Use ?page=N&limit=M."),
        ],
    ),
))
```

### Discovery

Serve a `/.well-known/ai` manifest and JSON-LD structured data so agents can discover your API.

```python
from agent_layer.types import DiscoveryConfig, AIManifest

configure_agent_layer(app, AgentLayerConfig(
    discovery=DiscoveryConfig(
        manifest=AIManifest(
            name="Widget API",
            description="Manage widgets programmatically",
            openapi_url="/openapi.json",
            llms_txt_url="/llms.txt",
            capabilities=["search", "crud"],
        ),
    ),
))
```

### A2A (Agent-to-Agent)

Serve a machine-readable `/.well-known/agent.json` per the [Google A2A protocol](https://github.com/google/A2A):

```python
from agent_layer.a2a import A2AConfig, A2AAgentCard, A2ASkill

configure_agent_layer(app, AgentLayerConfig(
    a2a=A2AConfig(
        card=A2AAgentCard(
            name="Widget Service",
            description="Agent that manages widgets",
            url="https://api.example.com",
            skills=[
                A2ASkill(
                    id="search",
                    name="Search Widgets",
                    description="Full-text search across all widgets",
                ),
            ],
        ),
    ),
))
```

### x402 Payments

Accept micropayments from AI agents via the [x402 protocol](https://x402.org). Agents pay with USDC stablecoin and retry automatically.

```python
from agent_layer.x402 import X402Config, X402RouteConfig

# FastAPI
from agent_layer.fastapi.x402 import x402_middleware

app.middleware("http")(x402_middleware(X402Config(
    facilitator_url="https://x402.org/facilitator",
    payee_address="0xYourWalletAddress",
    network="base-sepolia",
    routes={
        "/premium/*": X402RouteConfig(price="0.001", description="Premium endpoint"),
    },
)))
```

Protected endpoints return `402 Payment Required` with machine-readable payment instructions.

### Agent Identity

Verify agent credentials per the [IETF agent auth draft](https://datatracker.ietf.org/doc/draft-klrc-aiagent-auth/). Supports JWT-based Workload Identity Tokens, SPIFFE IDs, and scoped authorization.

```python
from agent_layer.agent_identity import AgentIdentityConfig

# FastAPI
from agent_layer.fastapi.agent_identity import agent_identity_middleware

app.middleware("http")(agent_identity_middleware(AgentIdentityConfig(
    issuer="https://my-app.example.com",
    audience="https://my-app.example.com",
    jwks_uri="https://my-app.example.com/.well-known/jwks.json",
)))

# Access verified claims in route handlers
@app.get("/protected")
async def protected(request: Request):
    claims = request.state.agent_identity
    return {"agent": claims.subject, "scopes": claims.scopes}
```

Use `agent_identity_optional_middleware` to extract identity when present without rejecting unauthenticated requests.

### Analytics

Detect AI agent traffic and collect telemetry. Recognizes 17+ agents (ChatGPT, GPTBot, ClaudeBot, Googlebot, PerplexityBot, and more).

```python
from agent_layer.analytics import AnalyticsConfig

# FastAPI
from agent_layer.fastapi.analytics import agent_analytics_middleware

agent_analytics_middleware(app, AnalyticsConfig(
    endpoint="https://dash.lightlayer.dev/api/agent-events/",
    api_key="ll_your_key",
    buffer_size=50,
    flush_interval_seconds=30.0,
))
```

Or via top-level config:

```python
from agent_layer.types import AnalyticsConfigRef

configure_agent_layer(app, AgentLayerConfig(
    analytics=AnalyticsConfigRef(
        endpoint="https://dash.lightlayer.dev/api/agent-events/",
        api_key="ll_your_key",
    ),
))
```

### MCP Server

Expose your API as a [Model Context Protocol](https://modelcontextprotocol.io) server. Auto-generates tool definitions from route metadata, handles JSON-RPC 2.0, and supports Streamable HTTP transport.

```python
from agent_layer.mcp import McpServerConfig, McpToolDefinition
from agent_layer.types import RouteMetadata

# FastAPI
from agent_layer.fastapi.mcp import mcp_routes

app.include_router(mcp_routes(McpServerConfig(
    name="Widget API",
    version="1.0.0",
    routes=[
        RouteMetadata(method="GET", path="/items", summary="List all items"),
        RouteMetadata(method="POST", path="/items", summary="Create an item"),
    ],
)), prefix="/mcp")
```

### Auth

OAuth discovery endpoint at `/.well-known/oauth-authorization-server`:

```python
from agent_layer.types import AgentAuthConfig

configure_agent_layer(app, AgentLayerConfig(
    agent_auth=AgentAuthConfig(
        issuer="https://auth.example.com",
        authorization_url="https://auth.example.com/authorize",
        token_url="https://auth.example.com/token",
        scopes={"read": "Read access", "write": "Write access"},
    ),
))
```

### Meta

Inject agent capability headers into responses:

```python
from agent_layer.types import AgentMetaConfig

configure_agent_layer(app, AgentLayerConfig(
    agent_meta=AgentMetaConfig(
        agent_id_attribute="data-agent-id",
        aria_landmarks=True,
    ),
))
```

### Unified Discovery

Single config, all discovery formats. Generates `/.well-known/ai`, `/.well-known/agent.json`, `/agents.txt`, `/llms.txt`, and `/llms-full.txt` from one configuration object.

```python
from agent_layer.unified_discovery import UnifiedDiscoveryConfig

# FastAPI
from agent_layer.fastapi.unified_discovery import unified_discovery_routes

app.include_router(unified_discovery_routes(UnifiedDiscoveryConfig(
    name="Widget API",
    description="CRUD API for managing widgets",
    url="https://api.example.com",
    skills=[{
        "id": "search",
        "name": "Search",
        "description": "Full-text search across all widgets",
    }],
)))
```

---

## Use Individual Modules

Every module works standalone — no need to use `configure_agent_layer`:

```python
# Just rate limiting
from agent_layer.fastapi import rate_limits_middleware
from agent_layer.types import RateLimitConfig

rate_limits_middleware(app, RateLimitConfig(max=50, window_ms=30_000))

# Just llms.txt
from agent_layer.fastapi.llms_txt import llms_txt_routes
from agent_layer.types import LlmsTxtConfig

app.include_router(llms_txt_routes(LlmsTxtConfig(title="My API")))

# Just A2A
from agent_layer.fastapi.a2a import a2a_routes
from agent_layer.a2a import A2AConfig, A2AAgentCard

app.include_router(a2a_routes(A2AConfig(card=A2AAgentCard(
    name="My Agent", url="https://api.example.com",
))))
```

---

## Testing

417 tests across 23 test files, covering core logic, all three framework adapters, and E2E integration tests.

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

CI runs on Python 3.11, 3.12, and 3.13.

---

## Companion Projects

| Project | Description |
|---------|-------------|
| [**agent-layer-ts**](https://github.com/lightlayer-dev/agent-layer-ts) | TypeScript version (Express / Koa / Hono) |
| [**agent-bench**](https://github.com/lightlayer-dev/agent-bench) | Benchmark your site's agent-readiness score |
| [**LightLayer Dashboard**](https://github.com/lightlayer-dev/lightlayer-dashboard) | Analytics & monitoring UI |

---

## License

MIT — see [LICENSE](./LICENSE).
