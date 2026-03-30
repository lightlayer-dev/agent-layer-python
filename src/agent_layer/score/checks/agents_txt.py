"""Check: agents.txt — robots.txt-style permission system for AI agents."""

from ..types import CheckResult, ScanConfig
from .utils import safe_fetch, resolve_url


async def check_agents_txt(config: ScanConfig) -> CheckResult:
    base = CheckResult(
        id="agents-txt",
        name="agents.txt Permissions",
        score=0,
        max_score=10,
        severity="fail",
        message="",
    )

    url = resolve_url(config.url, "/agents.txt")
    res = await safe_fetch(url, config)

    if res is None or res.status_code >= 400:
        base.message = "No agents.txt found — AI agents can't discover permissions"
        base.suggestion = (
            "Add /agents.txt to declare which agents can access your site "
            "and what they're allowed to do. Use @agent-layer agents-txt middleware."
        )
        base.details = {"status": res.status_code if res else 0}
        return base

    body = res.text
    lines = [
        line.strip()
        for line in body.split("\n")
        if line.strip() and not line.strip().startswith("#")
    ]

    has_user_agent = any(line.lower().startswith("user-agent:") for line in lines)
    has_allow = any(line.lower().startswith("allow:") for line in lines)
    has_disallow = any(line.lower().startswith("disallow:") for line in lines)
    has_auth = any(line.lower().startswith("auth:") for line in lines)
    has_rate_limit = any(line.lower().startswith("rate-limit:") for line in lines)

    features: list[str] = []
    if has_user_agent:
        features.append("agent targeting")
    if has_allow or has_disallow:
        features.append("path rules")
    if has_auth:
        features.append("auth requirements")
    if has_rate_limit:
        features.append("rate limits")

    details = {
        "status": res.status_code,
        "lineCount": len(lines),
        "hasUserAgent": has_user_agent,
        "hasAllow": has_allow,
        "hasDisallow": has_disallow,
        "hasAuth": has_auth,
        "hasRateLimit": has_rate_limit,
    }

    if len(features) >= 3:
        base.score = 10
        base.severity = "pass"
        base.message = f"agents.txt with {', '.join(features)}"
    elif len(features) >= 1:
        base.score = 6
        base.severity = "warn"
        base.message = (
            f"agents.txt found with {', '.join(features)} — consider adding more directives"
        )
        base.suggestion = (
            "Add auth requirements and rate limits to give agents clear usage boundaries"
        )
    else:
        base.score = 3
        base.severity = "warn"
        base.message = "agents.txt exists but contains no recognized directives"
        base.suggestion = (
            "Add User-Agent, Allow/Disallow, and rate-limit directives. See @agent-layer docs."
        )

    base.details = details
    return base
