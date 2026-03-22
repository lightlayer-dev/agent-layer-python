"""Check: CORS headers for agent access."""

from ..types import CheckResult, ScanConfig
from .utils import safe_fetch


async def check_cors(config: ScanConfig) -> CheckResult:
    base = CheckResult(
        id="cors",
        name="CORS for Agents",
        score=0,
        max_score=10,
        severity="fail",
        message="",
    )

    # OPTIONS preflight
    res = await safe_fetch(
        config.url, config,
        method="OPTIONS",
        headers={
            "Origin": "https://agent.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    # Regular GET with Origin
    get_res = await safe_fetch(
        config.url, config,
        headers={"Origin": "https://agent.example.com"},
    )

    check_res = res or get_res
    if check_res is None:
        base.message = "Could not reach the server"
        return base

    acao = check_res.headers.get("access-control-allow-origin", "")
    acam = check_res.headers.get("access-control-allow-methods", "")
    acah = check_res.headers.get("access-control-allow-headers", "")
    max_age = check_res.headers.get("access-control-max-age", "")

    details = {
        "allowOrigin": acao,
        "allowMethods": acam,
        "allowHeaders": acah,
        "maxAge": max_age,
        "optionsStatus": res.status_code if res else None,
        "getStatus": get_res.status_code if get_res else None,
    }

    if not acao:
        base.message = "No CORS headers found"
        base.suggestion = "Add Access-Control-Allow-Origin headers for browser-based agents and frontend integrations"
        base.details = details
        return base

    score = 5  # Has ACAO
    if acao == "*" or "agent" in acao:
        score += 2
    if acam:
        score += 1
    if acah:
        score += 1
    if max_age:
        score += 1

    score = min(score, 10)

    base.score = score
    base.severity = "pass" if score >= 8 else "warn"
    base.message = f"CORS: Allow-Origin={acao or 'none'}"
    base.details = details
    if score < 10:
        base.suggestion = "Configure CORS with Allow-Methods, Allow-Headers, and Max-Age for optimal agent access"

    return base
