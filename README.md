# agent-layer (Python)

**Make your Python web app AI-agent-friendly.**

Composable middleware for FastAPI (Django and Flask coming soon) that adds everything AI agents need to interact with your API reliably.

## Features

| Module | What it does |
|--------|-------------|
| **errors** | Standardized error envelopes that agents can parse |
| **rate_limits** | `X-RateLimit-*` headers + 429 with `Retry-After` |
| **llms_txt** | Auto-serve `/llms.txt` for LLM context |
| **discovery** | `/.well-known/ai` manifest + JSON-LD |
| **auth** | OAuth discovery endpoint for agents |
| **meta** | Agent capability headers |

## Quick Start

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

Your API now has:
- Structured error envelopes on all errors
- Rate limiting with proper headers
- `/llms.txt` endpoint
- And agents can discover all of it

## Use Individual Modules

Each module works standalone:

```python
from agent_layer.fastapi import rate_limits_middleware
from agent_layer.types import RateLimitConfig

rate_limits_middleware(app, RateLimitConfig(max=50, window_ms=30_000))
```

## Companion Projects

- **[agent-layer-ts](https://github.com/lightlayer-dev/agent-layer-ts)** — TypeScript/Express version
- **[agent-bench](https://github.com/lightlayer-dev/agent-bench)** — Benchmark your site's agent-readiness score

## License

MIT
