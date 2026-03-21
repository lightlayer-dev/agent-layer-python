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
- Rate limiting on all requests with proper headers
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

### agents.txt

```python
from agent_layer.core.agents_txt import (
    AgentsTxtConfig, AgentsTxtRule, Permission,
    generate_agents_txt, parse_agents_txt, is_agent_allowed,
)

# Generate
config = AgentsTxtConfig(
    comment="AI Agent Access Policy",
    rules=[
        AgentsTxtRule(agent="*", permission=Permission.ALLOW, paths=["/"]),
        AgentsTxtRule(agent="BadBot", permission=Permission.DISALLOW, paths=["/"]),
    ],
)
txt = generate_agents_txt(config)

# Parse
rules = parse_agents_txt(txt)

# Check
is_agent_allowed(rules, "GPTBot", "/api")      # True
is_agent_allowed(rules, "BadBot", "/api")       # False
```

### llms.txt

```python
from agent_layer.core.llms_txt import (
    LlmsTxtConfig, LlmsTxtSection, RouteMetadata, RouteParameter,
    generate_llms_txt, generate_llms_full_txt,
)

config = LlmsTxtConfig(
    title="My API",
    description="A powerful API",
    sections=[
        LlmsTxtSection(title="Authentication", content="Use Bearer tokens."),
    ],
)

# Basic
txt = generate_llms_txt(config)

# With route docs
full = generate_llms_full_txt(config, routes=[
    RouteMetadata(
        method="GET", path="/users",
        summary="List users",
        parameters=[
            RouteParameter(name="limit", location="query", description="Max results"),
        ],
    ),
])
```

### Structured Errors

```python
from agent_layer.core.errors import AgentError, AgentErrorOptions

# Raise in your route handlers — framework adapters catch these automatically
raise AgentError(AgentErrorOptions(
    code="user_not_found",
    message="No user with that ID exists.",
    status=404,
    docs_url="https://docs.example.com/errors/user_not_found",
))

# Response:
# {
#   "error": {
#     "type": "not_found_error",
#     "code": "user_not_found",
#     "message": "No user with that ID exists.",
#     "status": 404,
#     "is_retriable": false,
#     "docs_url": "https://docs.example.com/errors/user_not_found"
#   }
# }
```

### Rate Limiting

```python
from agent_layer.core.rate_limit import RateLimitConfig, create_rate_limiter

check = create_rate_limiter(RateLimitConfig(
    max=100,
    window_ms=60_000,
    key_fn=lambda req: req.client.host,  # Per-IP limiting
))

result = await check(request)
if not result.allowed:
    # Return 429 with result.retry_after seconds
    pass
```

## Python Version

Requires Python 3.10+.

## TypeScript Version

Looking for the TypeScript/Node.js version? See [agent-layer-ts](https://github.com/lightlayer-dev/agent-layer-ts).

## License

MIT — see [LICENSE](LICENSE).
