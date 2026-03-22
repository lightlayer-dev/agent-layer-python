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
    return f"https://img.shields.io/badge/{quote(label)}-{score}%2F100-{color}"


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
