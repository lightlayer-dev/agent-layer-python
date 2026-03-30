"""Check: Rate limit headers on responses."""

from ..types import CheckResult, ScanConfig
from .utils import safe_fetch

RATE_LIMIT_HEADERS = [
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "ratelimit-limit",
    "ratelimit-remaining",
    "ratelimit-reset",
    "ratelimit-policy",
    "retry-after",
    "x-rate-limit-limit",
    "x-rate-limit-remaining",
]


async def check_rate_limits(config: ScanConfig) -> CheckResult:
    base = CheckResult(
        id="rate-limits",
        name="Rate Limit Headers",
        score=0,
        max_score=10,
        severity="fail",
        message="",
    )

    res = await safe_fetch(config.url, config)
    if res is None:
        base.message = "Could not reach the server"
        return base

    found_headers = [h for h in RATE_LIMIT_HEADERS if res.headers.get(h)]
    details = {"foundHeaders": found_headers, "totalChecked": len(RATE_LIMIT_HEADERS)}

    if not found_headers:
        base.message = "No rate limit headers found"
        base.suggestion = "Add rate limit headers so agents can self-throttle — agent-layer rate_limits() middleware handles this"
        base.details = details
        return base

    has_limit = any(
        "limit" in h and "remaining" not in h and "reset" not in h for h in found_headers
    )
    has_remaining = any("remaining" in h for h in found_headers)
    has_reset = any("reset" in h or h == "retry-after" for h in found_headers)

    score = 4
    if has_limit:
        score += 2
    if has_remaining:
        score += 2
    if has_reset:
        score += 2

    score = min(score, 10)

    base.score = score
    base.severity = "pass" if score >= 8 else "warn"
    base.message = f"Found rate limit headers: {', '.join(found_headers)}"
    base.details = details
    if score < 10:
        base.suggestion = (
            "Include limit, remaining, and reset headers for complete agent rate-limit awareness"
        )

    return base
