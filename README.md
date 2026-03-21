# agent-layer (Python)

**The agent gateway for Python web apps.**

Composable middleware for **FastAPI**, **Flask**, and **Django** that adds everything AI agents need to interact with your API — discovery, payments, identity, analytics, and error handling.

## Features

| Module | What it does |
|--------|-------------|
| **errors** | Standardized error envelopes that agents can parse |
| **rate_limits** | `X-RateLimit-*` headers + 429 with `Retry-After` |
| **llms_txt** | Auto-serve `/llms.txt` for LLM context |
| **discovery** | `/.well-known/ai` manifest + JSON-LD |
| **a2a** | `/.well-known/agent.json` — Google A2A Agent Card |
| **x402** | HTTP 402 micropayments via [x402 protocol](https://x402.org) (USDC stablecoin) |
| **agent_identity** | Agent credential verification per [IETF draft-klrc-aiagent-auth](https://datatracker.ietf.org/doc/draft-klrc-aiagent-auth/) |
| **analytics** | Detect AI agent traffic, collect telemetry, batch flush |
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

## x402 Payments

Accept micropayments from AI agents via the [x402 protocol](https://x402.org):

```python
from agent_layer.types import X402Config

configure_agent_layer(app, AgentLayerConfig(
    x402=X402Config(
        facilitator_url="https://x402.org/facilitator",
        payee_address="0xYourWalletAddress",
        network="base-sepolia",
    ),
))
```

Protected endpoints return `402 Payment Required` with payment instructions. Agents pay with USDC stablecoin and retry automatically.

## A2A Agent Card

Serve a machine-readable capability advertisement per [Google's A2A protocol](https://github.com/google/A2A):

```python
from agent_layer.a2a import A2AConfig, A2AAgentCard, A2ASkill

configure_agent_layer(app, AgentLayerConfig(
    a2a=A2AConfig(
        card=A2AAgentCard(
            name="My Service",
            description="What my service does for agents",
            skills=[A2ASkill(id="search", name="Search", description="Search things")],
        ),
    ),
))
```

## Agent Identity

Verify agent credentials per the [IETF agent auth draft](https://datatracker.ietf.org/doc/draft-klrc-aiagent-auth/):

```python
from agent_layer.types import AgentIdentityConfig

configure_agent_layer(app, AgentLayerConfig(
    agent_identity=AgentIdentityConfig(
        issuer="https://my-app.example.com",
        audience="https://my-app.example.com",
        jwks_uri="https://my-app.example.com/.well-known/jwks.json",
    ),
))
```

## Use Individual Modules

Each module works standalone:

```python
from agent_layer.fastapi import rate_limits_middleware
from agent_layer.types import RateLimitConfig

rate_limits_middleware(app, RateLimitConfig(max=50, window_ms=30_000))
```

## Framework Support

| Framework | Status |
|-----------|--------|
| FastAPI | ✅ Full support |
| Flask | ✅ Full support |
| Django | ✅ Full support |

## Companion Projects

- **[agent-layer-ts](https://github.com/lightlayer-dev/agent-layer-ts)** — TypeScript (Express/Koa/Hono) version
- **[agent-bench](https://github.com/lightlayer-dev/agent-bench)** — Benchmark your site's agent-readiness score
- **[LightLayer Dashboard](https://github.com/lightlayer-dev/lightlayer-dashboard)** — Analytics & monitoring UI

## License

MIT
