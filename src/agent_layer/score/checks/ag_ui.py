"""Check: AG-UI (Agent-UI) streaming support."""

from ..types import CheckResult, ScanConfig
from .utils import safe_fetch, resolve_url

AG_UI_PATHS = [
    "/ag-ui",
    "/api/ag-ui",
    "/.well-known/ag-ui",
]


async def check_ag_ui(config: ScanConfig) -> CheckResult:
    base = CheckResult(
        id="ag-ui",
        name="AG-UI Streaming",
        score=0,
        max_score=5,
        severity="fail",
        message="",
    )

    found: list[str] = []
    details: dict[str, object] = {}

    for path in AG_UI_PATHS:
        url = resolve_url(config.url, path)
        res = await safe_fetch(url, config)
        status = res.status_code if res else 0
        # AG-UI endpoints typically return 200 or 405 (POST-only)
        ok = (200 <= status < 400) or status == 405

        details[path] = {"status": status, "found": ok}

        if ok:
            found.append(path)

    if found:
        base.score = 5
        base.severity = "pass"
        base.message = f"AG-UI endpoint found at {', '.join(found)}"
    else:
        base.message = "No AG-UI streaming endpoint detected"
        base.suggestion = (
            "Add AG-UI streaming support for real-time agent communication. "
            "Use @agent-layer ag-ui middleware for FastAPI/Flask/Django."
        )

    base.details = details
    return base
