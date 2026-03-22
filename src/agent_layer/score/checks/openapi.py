"""Check: OpenAPI / Swagger specification availability."""

import json

from ..types import CheckResult, ScanConfig
from .utils import safe_fetch, resolve_url

OPENAPI_PATHS = [
    "/openapi.json", "/openapi.yaml", "/swagger.json", "/api-docs",
    "/docs/openapi.json", "/v1/openapi.json", "/api/openapi.json", "/.well-known/openapi.json",
]


async def check_openapi(config: ScanConfig) -> CheckResult:
    base = CheckResult(
        id="openapi",
        name="OpenAPI / Swagger Spec",
        score=0,
        max_score=10,
        severity="fail",
        message="",
    )

    found: list[dict] = []
    details: dict = {}

    for path in OPENAPI_PATHS:
        url = resolve_url(config.url, path)
        res = await safe_fetch(url, config)

        if not res or res.status_code >= 400:
            details[path] = {"status": res.status_code if res else 0}
            continue

        ct = res.headers.get("content-type", "")
        if not any(t in ct for t in ("json", "yaml", "text")):
            details[path] = {"status": res.status_code, "contentType": ct, "skipped": True}
            continue

        try:
            text = res.text
            has_descriptions = False
            version = None

            try:
                parsed = json.loads(text)
                version = parsed.get("openapi") or parsed.get("swagger")
                paths_obj = parsed.get("paths", {})
                path_count = len(paths_obj)
                with_desc = sum(
                    1 for p in paths_obj.values()
                    if any(
                        isinstance(op, dict) and (op.get("description") or op.get("summary"))
                        for op in p.values()
                    )
                )
                has_descriptions = path_count > 0 and with_desc / path_count > 0.5
            except (json.JSONDecodeError, ValueError):
                has_descriptions = "description:" in text

            found.append({"path": path, "hasDescriptions": has_descriptions, "version": version})
            details[path] = {"status": res.status_code, "found": True, "version": version, "hasDescriptions": has_descriptions}
        except Exception:
            details[path] = {"status": res.status_code, "error": "Could not read body"}

    base.details = details

    if not found:
        base.message = "No OpenAPI or Swagger spec found"
        base.suggestion = "Serve an OpenAPI spec at /openapi.json so agents can discover your API structure"
        return base

    best = found[0]
    score = 5

    v = best.get("version") or ""
    if str(v).startswith("3"):
        score += 2
    elif v:
        score += 1

    if best["hasDescriptions"]:
        score += 3
    else:
        score += 1

    score = min(score, 10)

    notes = [f"Found at {best['path']}"]
    if best.get("version"):
        notes.append(f"version {best['version']}")
    if best["hasDescriptions"]:
        notes.append("with good descriptions")
    else:
        notes.append("descriptions could be more detailed")

    base.score = score
    base.severity = "pass" if score >= 8 else "warn"
    base.message = "; ".join(notes)
    if score < 10:
        base.suggestion = "Ensure all endpoints have descriptions and summaries for better agent comprehension"

    return base
