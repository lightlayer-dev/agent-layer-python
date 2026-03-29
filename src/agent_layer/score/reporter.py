"""Terminal output reporter with colors and badges."""

from __future__ import annotations

import json
from urllib.parse import quote

from .types import ScoreReport


def _icon(severity: str) -> str:
    return {"pass": "✅", "warn": "⚠️ ", "fail": "❌"}.get(severity, "❓")


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 50:
        return "D"
    return "F"


def format_report(report: ScoreReport) -> str:
    """Format a score report for terminal output."""
    lines: list[str] = [""]
    lines.append(f"🤖 Agent-Readiness Score: {report.score}/100 ({_grade(report.score)})")
    lines.append(f"   {report.url} — {report.duration_ms}ms")
    lines.append("")

    for check in report.checks:
        lines.append(f"  {_icon(check.severity)} {check.name} ({check.score}/{check.max_score})")
        lines.append(f"     {check.message}")
        if check.suggestion:
            lines.append(f"     💡 {check.suggestion}")

    lines.append("")

    failing = [c for c in report.checks if c.severity == "fail"]
    if failing:
        lines.append("🔧 Quick wins to improve your score:")
        for check in failing[:3]:
            if check.suggestion:
                lines.append(f"   • {check.suggestion}")
        lines.append("")

    if report.score < 50:
        lines.append("💡 Add agent-layer middleware to instantly improve your score:")
        lines.append("   pip install agent-layer[fastapi]")
        lines.append("")

    return "\n".join(lines)


def badge_url(score: int, label: str = "Agent-Ready") -> str:
    """Generate a shields.io badge URL for the score."""
    color = "brightgreen" if score >= 80 else ("yellow" if score >= 50 else "red")
    logo = (
        "data:image/svg+xml;base64,"
        "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9"
        "IjAgMCAyNCAyNCIgZmlsbD0id2hpdGUiPjxwYXRoIGQ9Ik0xMiAyQzYuNDggMiAy"
        "IDYuNDggMiAxMnM0LjQ4IDEwIDEwIDEwIDEwLTQuNDggMTAtMTBTMTcuNTIgMiAx"
        "MiAyem0wIDE4Yy00LjQyIDAtOC0zLjU4LTgtOHMzLjU4LTggOC04IDggMy41OCA4"
        "IDgtMy41OCA0LTggOHoiLz48L3N2Zz4="
    )
    return (
        f"https://img.shields.io/badge/{quote(label)}-{score}%2F100-{color}"
        f"?logo={logo}"
        f"&link=https://github.com/lightlayer-dev/agent-layer-ts"
    )


def badge_markdown(score: int, label: str = "Agent-Ready") -> str:
    """Generate the full markdown badge with link for READMEs.

    Links back to the agent-layer repo for brand attribution.
    """
    url = badge_url(score, label)
    return (
        f'[![{label}: {score}/100]({url})]'
        f'(https://github.com/lightlayer-dev/agent-layer-ts "Scored by @agent-layer/score")'
    )


def format_json(report: ScoreReport) -> str:
    """Format report as JSON."""
    data = {
        "url": report.url,
        "timestamp": report.timestamp,
        "score": report.score,
        "durationMs": report.duration_ms,
        "checks": [
            {
                "id": c.id,
                "name": c.name,
                "score": c.score,
                "maxScore": c.max_score,
                "severity": c.severity,
                "message": c.message,
                **({"suggestion": c.suggestion} if c.suggestion else {}),
                **({"details": c.details} if c.details else {}),
            }
            for c in report.checks
        ],
    }
    return json.dumps(data, indent=2)
