# agent-layer-score

**Lighthouse for AI agents** — Score any API or website for agent-readiness.

Part of the [agent-layer](https://github.com/lightlayer-dev/agent-layer-python) Python middleware.

## Quick Start

```bash
pip install agent-layer
agent-layer-score https://your-api.com
```

## Usage

### CLI

```bash
# Basic scan
agent-layer-score https://example.com

# JSON output
agent-layer-score https://example.com --json

# Shields.io badge URL
agent-layer-score https://example.com --badge

# Custom threshold (exit 1 if below)
agent-layer-score https://example.com --threshold 70

# Custom timeout (ms)
agent-layer-score https://example.com --timeout 5000
```

### Programmatic

```python
import asyncio
from agent_layer.score import scan

report = asyncio.run(scan("https://example.com"))
print(f"Score: {report.score}/100")

for check in report.checks:
    print(f"  {check.name}: {check.score}/{check.max_score} ({check.severity})")
    if check.suggestion:
        print(f"    💡 {check.suggestion}")
```

## Checks (11 total)

| Check | What it measures | Max Score |
|-------|-----------------|-----------|
| Structured JSON Errors | JSON error responses vs HTML | 10 |
| Agent Discovery | .well-known/agent-card.json, agent.json, ai-plugin.json | 10 |
| llms.txt | /llms.txt presence and quality | 10 |
| robots.txt Agent Rules | AI agent rules in robots.txt | 10 |
| Rate Limit Headers | Rate limit headers for agent self-throttling | 10 |
| OpenAPI / Swagger | API spec availability and quality | 10 |
| Content-Type | Proper Content-Type headers | 10 |
| CORS | Cross-origin access for agents | 10 |
| Security Headers | Security headers present but not blocking | 10 |
| Response Time | Fast response times | 10 |
| x402 Agent Payments | x402 micropayment protocol support | 10 |

## CI Integration

Use in GitHub Actions:

```yaml
- name: Agent-Readiness Score
  run: |
    pip install agent-layer
    agent-layer-score ${{ env.API_URL }} --threshold 50 --json
```

Or use the TypeScript GitHub Action for richer PR comments:
[`@agent-layer/score` Action](https://github.com/lightlayer-dev/agent-layer-ts/tree/main/packages/score)
