"""Agent-readiness scoring — Lighthouse for AI agents."""

from .types import CheckResult, CheckSeverity, ScoreReport, ScanConfig
from .scanner import scan
from .reporter import badge_url, badge_markdown

__all__ = [
    "scan",
    "CheckResult",
    "CheckSeverity",
    "ScoreReport",
    "ScanConfig",
    "badge_url",
    "badge_markdown",
]
