"""Check: /llms.txt presence and quality."""

from ..types import CheckResult, ScanConfig
from .utils import safe_fetch, resolve_url


async def check_llms_txt(config: ScanConfig) -> CheckResult:
    base = CheckResult(
        id="llms-txt",
        name="llms.txt",
        score=0,
        max_score=10,
        severity="fail",
        message="",
    )

    paths = ["/llms.txt", "/llms-full.txt"]
    found: list[dict] = []
    details: dict = {}

    for path in paths:
        url = resolve_url(config.url, path)
        res = await safe_fetch(url, config)

        if res and 200 <= res.status_code < 300:
            text = res.text
            has_structure = "#" in text or ">" in text
            found.append({"path": path, "length": len(text), "hasStructure": has_structure})
            details[path] = {"status": res.status_code, "length": len(text), "hasStructure": has_structure}
        else:
            details[path] = {"status": res.status_code if res else 0, "found": False}

    base.details = details

    if not found:
        base.message = "No llms.txt found"
        base.suggestion = "Add /llms.txt to describe your site for LLMs — agent-layer llms_txt() middleware generates it automatically"
        return base

    best = found[0]
    score = 5
    notes = [f"Found {best['path']} ({best['length']} chars)"]

    if best["hasStructure"]:
        score += 2
        notes.append("has markdown structure")
    if best["length"] > 200:
        score += 1
        notes.append("good content length")
    if len(found) > 1:
        score += 2
        notes.append("has llms-full.txt variant too")

    base.score = min(score, 10)
    base.severity = "pass" if base.score >= 8 else "warn"
    base.message = "; ".join(notes)
    if base.score < 10:
        base.suggestion = "Consider adding both /llms.txt and /llms-full.txt with structured markdown content"

    return base
