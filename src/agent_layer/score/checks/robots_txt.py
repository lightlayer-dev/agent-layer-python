"""Check: robots.txt presence and AI agent rules."""

from ..types import CheckResult, ScanConfig
from .utils import safe_fetch, resolve_url

AI_AGENTS = [
    "GPTBot", "ChatGPT-User", "Google-Extended", "Anthropic", "ClaudeBot",
    "CCBot", "Amazonbot", "Bytespider", "Applebot-Extended", "PerplexityBot", "Cohere-ai",
]


async def check_robots_txt(config: ScanConfig) -> CheckResult:
    base = CheckResult(
        id="robots-txt",
        name="robots.txt Agent Rules",
        score=0,
        max_score=10,
        severity="fail",
        message="",
    )

    url = resolve_url(config.url, "/robots.txt")
    res = await safe_fetch(url, config)

    if res is None:
        base.message = "Could not reach the server"
        base.details = {"status": 0}
        return base

    if res.status_code >= 400:
        base.score = 3
        base.severity = "warn"
        base.message = "No robots.txt found — agents will assume full access"
        base.suggestion = "Add robots.txt with explicit AI agent rules to signal intentional access control"
        base.details = {"status": res.status_code}
        return base

    text = res.text
    lines = text.lower()

    mentioned_agents = [a for a in AI_AGENTS if a.lower() in lines]
    has_wildcard = "user-agent: *" in lines
    has_sitemap = "sitemap:" in lines

    details = {
        "hasRobotsTxt": True,
        "mentionedAiAgents": mentioned_agents,
        "hasWildcardRule": has_wildcard,
        "hasSitemap": has_sitemap,
        "length": len(text),
    }

    score = 4  # Has robots.txt
    if mentioned_agents:
        score += min(len(mentioned_agents), 3)
    if has_sitemap:
        score += 1
    if has_wildcard:
        score += 1
    if len(mentioned_agents) >= 3:
        score += 1

    score = min(score, 10)

    messages = ["robots.txt found"]
    if mentioned_agents:
        messages.append(f"mentions {len(mentioned_agents)} AI agents")
    else:
        messages.append("no AI-specific agent rules")

    base.score = score
    base.severity = "pass" if score >= 8 else ("warn" if score >= 5 else "fail")
    base.message = "; ".join(messages)
    base.details = details
    if score < 10:
        base.suggestion = "Add explicit rules for AI agents (GPTBot, ClaudeBot, etc.) to communicate your access policy"

    return base
