"""Check: Response time — fast APIs are more agent-friendly."""

import time

from ..types import CheckResult, ScanConfig
from .utils import safe_fetch


async def check_response_time(config: ScanConfig) -> CheckResult:
    base = CheckResult(
        id="response-time",
        name="Response Time",
        score=0,
        max_score=10,
        severity="fail",
        message="",
    )

    times: list[int] = []

    for _ in range(3):
        start = time.monotonic()
        res = await safe_fetch(config.url, config)
        elapsed = int((time.monotonic() - start) * 1000)
        if res is not None:
            times.append(elapsed)

    if not times:
        base.message = "Could not reach the server"
        return base

    avg = round(sum(times) / len(times))
    details = {"measurements": times, "averageMs": avg}

    severity: str  # will be "pass", "warn", or "fail"
    if avg <= 200:
        score, severity = 10, "pass"
    elif avg <= 500:
        score, severity = 8, "pass"
    elif avg <= 1000:
        score, severity = 6, "warn"
    elif avg <= 2000:
        score, severity = 4, "warn"
    elif avg <= 5000:
        score, severity = 2, "fail"
    else:
        score, severity = 1, "fail"

    base.score = score
    base.severity = severity  # type: ignore[assignment]
    base.message = f"Average response time: {avg}ms"
    base.details = details
    if score < 8:
        base.suggestion = "Agents benefit from fast responses — consider caching, CDN, or optimizing backend queries"

    return base
