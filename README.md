# agent-layer 🐍

**Python middleware to make your web app AI-agent-friendly** — FastAPI, Flask, Django.

The Python port of [@agent-layer/core](https://github.com/lightlayer-dev/agent-layer-ts). Composable middleware that adds AI agent discovery, access control, and communication standards to your web application.

## Features

| Feature | Description |
|---------|-------------|
| **agents.txt** | Generate, parse, and enforce robots.txt-style access control for AI agents |
| **llms.txt** | Generate LLM-friendly documentation (llms.txt & llms-full.txt) |
| **Discovery** | `/.well-known/ai` manifest + JSON-LD structured data |
| **A2A Agent Card** | `/.well-known/agent.json` per Google's A2A protocol |
| **Structured Errors** | Agent-friendly error envelopes with retry logic |
| **Rate Limiting** | In-memory sliding window rate limiter |
| **MCP Server** | JSON-RPC 2.0 server with tool definitions and streamable HTTP transport |
| **Analytics** | Agent detection via User-Agent, event buffering, pluggable flush |
| **API Keys** | Key generation, validation, scopes, pluggable store |
| **x402 Payments** | HTTP 402 payment verification, headers, middleware |
| **Agent Identity** | SPIFFE ID parsing, JWT claims, authz policies, audit events |
| **Unified Discovery** | Multi-format content negotiation (MCP/A2A/llms.txt/agents.txt from one endpoint) |
| **AG-UI Streaming** | Server-Sent Events streaming for CopilotKit (AG-UI protocol) |
| **OAuth2** | Authorization server metadata, PKCE, token validation |
| **Agent Meta** | HTML transforms for agent accessibility (data attributes, ARIA, meta tags) |

## Install

```bash
# Core only
pip install agent-layer

# With framework adapter
pip install agent-layer[fastapi]
pip install agent-layer[flask]
pip install agent-layer[django]

# Everything
pip install agent-layer[all]
```

## Quick Start

### FastAPI (one-liner)

```python
from fastapi import FastAPI
from agent_layer.fastapi import AgentLayer
from agent_layer.core.agents_txt import AgentsTxtConfig, AgentsTxtRule, Permission
from agent_layer.core.llms_txt import LlmsTxtConfig
from agent_layer.core.discovery import DiscoveryConfig, AIManifest
from agent_layer.core.a2a import A2AConfig, A2AAgentCard, A2ASkill
from agent_layer.core.mcp import McpServerConfig
from agent_layer.core.analytics import AnalyticsConfig
from agent_layer.core.rate_limit import RateLimitConfig

app = FastAPI()

agent = AgentLayer(
    agents_txt=AgentsTxtConfig(
        rules=[
            AgentsTxtRule(agent="*", permission=Permission.ALLOW, paths=["/"]),
            AgentsTxtRule(agent="BadBot", permission=Permission.DISALLOW, paths=["/"]),
        ]
    ),
    llms_txt=LlmsTxtConfig(
        title="My API",
        description="A powerful API for AI agents",
    ),
    discovery=DiscoveryConfig(
        manifest=AIManifest(
            name="My API",
            description="AI-agent-friendly API",
        )
    ),
    a2a=A2AConfig(
        card=A2AAgentCard(
            name="MyAgent",
            url="https://api.example.com",
            skills=[
                A2ASkill(id="search", name="Search", description="Search the web"),
            ],
        )
    ),
    mcp=McpServerConfig(name="My API", version="1.0.0"),
    analytics=AnalyticsConfig(on_event=lambda e: print(f"Agent: {e.agent}")),
    rate_limit=RateLimitConfig(max=100, window_ms=60_000),
)

agent.install(app)  # That's it! All routes + middleware registered.
```

This gives you:
- `GET /agents.txt` — agent access control
- `GET /llms.txt` — LLM-friendly docs
- `GET /llms-full.txt` — full LLM docs with routes
- `GET /.well-known/ai` — AI discovery manifest
- `GET /.well-known/ai/json-ld` — JSON-LD structured data
- `GET /.well-known/agent.json` — A2A Agent Card
- `POST /mcp` — MCP JSON-RPC 2.0 endpoint
- `GET /mcp` — MCP SSE stream
- Rate limiting on all requests with proper headers
- Analytics tracking for AI agent requests
- Structured error handling for `AgentError` exceptions

### Flask

```python
from flask import Flask
from agent_layer.flask import AgentLayer
from agent_layer.core.llms_txt import LlmsTxtConfig

app = Flask(__name__)

agent = AgentLayer(
    llms_txt=LlmsTxtConfig(title="My API", description="Flask-powered API"),
)
agent.install(app)  # Registers blueprint + error handler
```

### Django

```python
# settings.py
from agent_layer.core.llms_txt import LlmsTxtConfig
from agent_layer.core.discovery import DiscoveryConfig, AIManifest

MIDDLEWARE = [
    'agent_layer.django.AgentLayerMiddleware',
    # ... other middleware
]

AGENT_LAYER = {
    'llms_txt': LlmsTxtConfig(title="My API"),
    'discovery': DiscoveryConfig(manifest=AIManifest(name="My API")),
}
```

## Core API

Each feature can be used standalone without a framework adapter:

### MCP Server

```python
from agent_layer.core.mcp import (
    McpServerConfig, generate_server_info, generate_tool_definitions,
    handle_json_rpc, McpToolDefinition,
)

# Auto-generate tools from routes
tools = generate_tool_definitions(routes)

# Or define manually
tools = [McpToolDefinition(name="search", description="Search the web")]

# Handle JSON-RPC requests
result = await handle_json_rpc(request_body, server_info, tools)
```

### Analytics

```python
from agent_layer.core.analytics import detect_agent, AnalyticsConfig, create_analytics

# Detect AI agents
agent = detect_agent("GPTBot/1.0")  # Returns "GPTBot"

# Full analytics with buffering
analytics = create_analytics(AnalyticsConfig(
    endpoint="https://analytics.example.com",
    on_event=lambda e: print(f"Agent {e.agent} hit {e.path}"),
))
```

### API Keys

```python
from agent_layer.core.api_keys import (
    create_api_key, validate_api_key, has_scope,
    MemoryApiKeyStore, ScopedApiKey,
)

# Generate key
result = create_api_key()  # al_<32 hex chars>

# Validate
store = MemoryApiKeyStore()
await store.set(ScopedApiKey(key_id="k1", key=result.key, scopes=["read"]))
validation = await validate_api_key(result.key, store)
```

### x402 Payments

```python
from agent_layer.core.x402 import X402Config, X402RouteConfig, handle_x402

config = X402Config(routes={
    "GET /api/weather": X402RouteConfig(pay_to="0xABC", price="$0.01"),
})
result = await handle_x402("GET", "/api/weather", url, payment_header, config)
```

### Agent Identity

```python
from agent_layer.core.agent_identity import (
    AgentIdentityConfig, AuthzContext, handle_require_identity,
    parse_spiffe_id,
)

config = AgentIdentityConfig(
    trusted_issuers=["https://auth.example.com"],
    default_policy="allow",
)
result = await handle_require_identity(auth_header, config, AuthzContext(method="GET", path="/api"))
```

### AG-UI Streaming

```python
from agent_layer.core.ag_ui import create_ag_ui_emitter, AG_UI_HEADERS

emitter = create_ag_ui_emitter(write_fn)
emitter.run_started()
emitter.text_message("Hello from the agent!")
emitter.run_finished()
```

### OAuth2

```python
from agent_layer.core.oauth2 import (
    generate_pkce, build_authorization_url, validate_access_token,
    OAuth2Config,
)

pkce = generate_pkce()
url = build_authorization_url(config, pkce=pkce)
result = validate_access_token(token, config)
```

### Agent Meta

```python
from agent_layer.core.agent_meta import AgentMetaConfig, transform_html

config = AgentMetaConfig(meta_tags={"ai-purpose": "api-docs"})
html = transform_html("<html><body>...</body></html>", config)
# Adds data-agent-id="root" to <body>, injects meta tags, ARIA landmarks
```

## Python Version

Requires Python 3.10+.

## Ecosystem

| Language | Library | Frameworks |
|----------|---------|------------|
| **TypeScript** | [agent-layer-ts](https://github.com/lightlayer-dev/agent-layer-ts) | Express, Koa, Hono, Fastify |
| **Go** | [agent-layer-go](https://github.com/lightlayer-dev/agent-layer-go) | Gin, Echo, Chi |

## License

MIT — see [LICENSE](LICENSE).
