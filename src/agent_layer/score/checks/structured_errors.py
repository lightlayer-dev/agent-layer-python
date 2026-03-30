"""Check: Structured JSON errors instead of HTML error pages."""

from ..types import CheckResult, ScanConfig
from .utils import safe_fetch, resolve_url


async def check_structured_errors(config: ScanConfig) -> CheckResult:
    base = CheckResult(
        id="structured-errors",
        name="Structured JSON Errors",
        score=0,
        max_score=10,
        severity="fail",
        message="",
    )

    test_paths = [
        "/__agent_layer_probe_404__",
        "/api/__nonexistent__",
        "/v1/__nonexistent__",
    ]

    json_errors = 0
    total_responses = 0
    details: dict = {}

    for path in test_paths:
        url = resolve_url(config.url, path)
        res = await safe_fetch(url, config)
        if res is None:
            continue

        total_responses += 1
        ct = res.headers.get("content-type", "")
        is_json = "application/json" in ct or "application/problem+json" in ct

        details[path] = {"status": res.status_code, "contentType": ct, "isJson": is_json}

        if is_json:
            json_errors += 1

    if total_responses == 0:
        base.message = "Could not reach the server to test error responses"
        base.details = details
        return base

    ratio = json_errors / total_responses
    if ratio >= 1:
        base.score = 10
        base.severity = "pass"
        base.message = "Error responses return structured JSON"
    elif ratio > 0:
        base.score = 5
        base.severity = "warn"
        base.message = (
            f"{json_errors}/{total_responses} error responses return JSON (some return HTML)"
        )
        base.suggestion = (
            "Use agent-layer error middleware to ensure all errors return structured JSON"
        )
    else:
        base.message = "Error responses return HTML instead of structured JSON"
        base.suggestion = "Use agent-layer error middleware to wrap errors in agent-friendly JSON"

    base.details = details
    return base
