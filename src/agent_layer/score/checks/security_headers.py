"""Check: Security headers that don't unnecessarily block agents."""

from ..types import CheckResult, ScanConfig
from .utils import safe_fetch


async def check_security_headers(config: ScanConfig) -> CheckResult:
    base = CheckResult(
        id="security-headers",
        name="Security Headers",
        score=0,
        max_score=10,
        severity="fail",
        message="",
    )

    res = await safe_fetch(config.url, config)
    if res is None:
        base.message = "Could not reach the server"
        return base

    hsts = res.headers.get("strict-transport-security", "")
    xcto = res.headers.get("x-content-type-options", "")
    xfo = res.headers.get("x-frame-options", "")
    csp = res.headers.get("content-security-policy", "")
    referrer = res.headers.get("referrer-policy", "")

    details = {
        "hsts": hsts or None,
        "xContentTypeOptions": xcto or None,
        "xFrameOptions": xfo or None,
        "csp": csp[:200] if csp else None,
        "referrerPolicy": referrer or None,
    }

    score = 0
    present: list[str] = []

    if hsts:
        score += 3
        present.append("HSTS")
    if xcto:
        score += 2
        present.append("X-Content-Type-Options")
    if xfo:
        score += 1
        present.append("X-Frame-Options")
    if referrer:
        score += 2
        present.append("Referrer-Policy")
    if csp:
        score += 2
        present.append("CSP")

    score = min(score, 10)

    base.details = details

    if not present:
        base.message = "No security headers found"
        base.suggestion = "Add HSTS, X-Content-Type-Options, and Referrer-Policy headers"
        return base

    base.score = score
    base.severity = "pass" if score >= 8 else ("warn" if score >= 4 else "fail")
    base.message = f"Security headers: {', '.join(present)}"
    if score < 10:
        all_expected = {"HSTS", "X-Content-Type-Options", "Referrer-Policy", "CSP"}
        missing = all_expected - set(present)
        if missing:
            base.suggestion = f"Missing: {', '.join(sorted(missing))}"

    return base
