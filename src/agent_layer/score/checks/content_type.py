"""Check: Proper Content-Type headers on responses."""

from ..types import CheckResult, ScanConfig
from .utils import safe_fetch


async def check_content_type(config: ScanConfig) -> CheckResult:
    base = CheckResult(
        id="content-type",
        name="Content-Type Headers",
        score=0,
        max_score=10,
        severity="fail",
        message="",
    )

    res = await safe_fetch(config.url, config)
    if res is None:
        base.message = "Could not reach the server"
        return base

    ct = res.headers.get("content-type", "")
    has_charset = "charset=" in ct
    has_media_type = len(ct) > 0
    is_specific = "application/octet-stream" not in ct

    details = {
        "contentType": ct,
        "hasCharset": has_charset,
        "hasMediaType": has_media_type,
        "isSpecific": is_specific,
    }

    if not has_media_type:
        base.message = "No Content-Type header in response"
        base.suggestion = (
            "Always include Content-Type headers so agents know how to parse responses"
        )
        base.details = details
        return base

    score = 5  # Has Content-Type
    if has_charset:
        score += 3
    if is_specific:
        score += 2

    score = min(score, 10)

    notes = [f"Content-Type: {ct}"]
    if not has_charset:
        notes.append("missing charset")

    base.score = score
    base.severity = "pass" if score >= 8 else "warn"
    base.message = "; ".join(notes)
    base.details = details
    if score < 10:
        base.suggestion = "Include charset in Content-Type (e.g. application/json; charset=utf-8)"

    return base
