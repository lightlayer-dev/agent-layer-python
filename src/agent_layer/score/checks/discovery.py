"""Check: Agent discovery endpoints."""

from ..types import CheckResult, ScanConfig
from .utils import safe_fetch, resolve_url

DISCOVERY_PATHS = [
    ("/.well-known/agent-card.json", "A2A Agent Card"),
    ("/.well-known/agent.json", "Agent JSON"),
    ("/.well-known/ai", "Well-Known AI"),
    ("/.well-known/ai-plugin.json", "AI Plugin (ChatGPT)"),
]


async def check_discovery(config: ScanConfig) -> CheckResult:
    base = CheckResult(
        id="discovery",
        name="Agent Discovery Endpoints",
        score=0,
        max_score=10,
        severity="fail",
        message="",
    )

    found: list[str] = []
    details: dict = {}

    for path, name in DISCOVERY_PATHS:
        url = resolve_url(config.url, path)
        res = await safe_fetch(url, config)
        status = res.status_code if res else 0
        ok = 200 <= status < 300

        details[path] = {"status": status, "found": ok}
        if ok:
            found.append(name)

    base.details = details

    if len(found) >= 2:
        base.score = 10
        base.severity = "pass"
        base.message = f"Found discovery endpoints: {', '.join(found)}"
    elif len(found) == 1:
        base.score = 7
        base.severity = "warn"
        base.message = f"Found: {found[0]}. Consider adding more discovery formats."
        base.suggestion = "Use agent-layer unified-discovery middleware to serve all formats from a single config"
    else:
        base.message = "No agent discovery endpoints found"
        base.suggestion = "Add /.well-known/agent-card.json (A2A) and /.well-known/agent.json — agent-layer makes this one line of config"

    return base
