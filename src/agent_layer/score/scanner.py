"""Core scanner — runs all checks and produces a ScoreReport."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from .types import ScoreReport, ScanConfig, CheckFn
from .checks import all_checks


async def scan(
    url: str,
    *,
    timeout_s: float = 10.0,
    user_agent: str | None = None,
    checks: list[CheckFn] | None = None,
) -> ScoreReport:
    """Scan a URL for agent-readiness and return a score report."""
    # Normalize URL
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    config = ScanConfig(
        url=url,
        timeout_s=timeout_s,
        user_agent=user_agent or "AgentLayerScore/0.1 (https://company.lightlayer.dev)",
    )

    checks_to_run = checks or all_checks
    start = time.monotonic()

    results = await asyncio.gather(*(check(config) for check in checks_to_run))

    total_score = sum(r.score for r in results)
    max_score = sum(r.max_score for r in results)
    normalized = round((total_score / max_score) * 100) if max_score > 0 else 0
    duration_ms = int((time.monotonic() - start) * 1000)

    return ScoreReport(
        url=url,
        timestamp=datetime.now(timezone.utc).isoformat(),
        score=normalized,
        checks=list(results),
        duration_ms=duration_ms,
    )
