"""Agent-readiness scoring types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Literal

CheckSeverity = Literal["pass", "warn", "fail"]


@dataclass
class CheckResult:
    """Result of a single check."""

    id: str
    name: str
    score: int
    max_score: int
    severity: CheckSeverity
    message: str
    suggestion: str | None = None
    details: dict[str, Any] | None = None


@dataclass
class ScoreReport:
    """Overall score report for a URL."""

    url: str
    timestamp: str
    score: int
    checks: list[CheckResult] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class ScanConfig:
    """Configuration for running checks."""

    url: str
    timeout_s: float = 10.0
    user_agent: str = "AgentLayerScore/0.1 (https://company.lightlayer.dev)"


# A check function signature.
CheckFn = Callable[[ScanConfig], Awaitable[CheckResult]]
