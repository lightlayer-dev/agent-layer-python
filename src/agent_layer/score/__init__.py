"""Agent-readiness scoring — Lighthouse for AI agents."""

from .types import CheckResult, CheckSeverity, ScoreReport, ScanConfig
from .scanner import scan

__all__ = ["scan", "CheckResult", "CheckSeverity", "ScoreReport", "ScanConfig"]
