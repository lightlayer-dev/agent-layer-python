"""Check: x402 (HTTP 402 Payment Required) support for agent micropayments."""

import json

from ..types import CheckResult, ScanConfig
from .utils import safe_fetch, resolve_url

X402_HEADERS = [
    "x-payment-address",
    "x-payment-network",
    "x-payment-amount",
    "x-payment-currency",
    "x-payment-required",
]


async def check_x402(config: ScanConfig) -> CheckResult:
    base = CheckResult(
        id="x402",
        name="x402 Agent Payments",
        score=0,
        max_score=10,
        severity="fail",
        message="",
    )

    main_res = await safe_fetch(config.url, config)
    if main_res is None:
        base.message = "Could not reach the server"
        return base

    main_headers = [h for h in X402_HEADERS if main_res.headers.get(h)]

    # Check .well-known/x402
    wk_url = resolve_url(config.url, "/.well-known/x402")
    wk_res = await safe_fetch(wk_url, config)
    has_well_known = wk_res is not None and 200 <= wk_res.status_code < 300

    # Check for 402 response
    probe_url = resolve_url(config.url, "/api/__x402_probe__")
    probe_res = await safe_fetch(probe_url, config)
    has_402 = probe_res is not None and probe_res.status_code == 402

    payment_body = None
    if has_402 and probe_res is not None:
        try:
            ct = probe_res.headers.get("content-type", "")
            if "json" in ct:
                payment_body = json.loads(probe_res.text)
        except Exception:
            pass

    details = {
        "mainHeaders": main_headers,
        "hasWellKnown": has_well_known,
        "has402": has_402,
        "paymentBody": payment_body,
    }

    if not has_well_known and not main_headers and not has_402:
        base.message = "No x402 payment support detected — this is a cutting-edge feature"
        base.suggestion = "Add x402 micropayment support with agent-layer x402() middleware for monetizing agent API calls"
        base.details = details
        return base

    score = 0
    notes: list[str] = []

    if has_well_known:
        score += 4
        notes.append("/.well-known/x402 endpoint found")
    if main_headers:
        score += 3
        notes.append(f"x402 headers: {', '.join(main_headers)}")
    if has_402:
        score += 3
        notes.append("proper 402 response on protected routes")
        if payment_body:
            notes.append("with structured payment metadata")

    score = min(score, 10)

    base.score = score
    base.severity = "pass" if score >= 8 else ("warn" if score >= 4 else "fail")
    base.message = "; ".join(notes)
    base.details = details
    if score < 10:
        base.suggestion = "Implement the full x402 protocol for seamless agent micropayments"

    return base
