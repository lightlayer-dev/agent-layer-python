"""Tests for agent-layer score CLI and scanner."""

from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock

from agent_layer.score.types import CheckResult, ScanConfig, ScoreReport
from agent_layer.score.scanner import scan
from agent_layer.score.reporter import format_report, format_json, badge_url, badge_markdown
from agent_layer.score.checks.utils import resolve_url


# -- Utils --

def test_resolve_url():
    assert resolve_url("https://example.com/foo", "/bar") == "https://example.com/bar"
    assert resolve_url("https://example.com:8080/x", "/.well-known/ai") == "https://example.com:8080/.well-known/ai"


# -- Reporter --

def test_format_report_basic():
    report = ScoreReport(
        url="https://example.com",
        timestamp="2026-01-01T00:00:00Z",
        score=75,
        checks=[
            CheckResult(id="test", name="Test Check", score=7, max_score=10, severity="warn", message="Partial pass"),
        ],
        duration_ms=123,
    )
    output = format_report(report)
    assert "75/100" in output
    assert "Test Check" in output
    assert "Partial pass" in output


def test_format_report_with_suggestions():
    report = ScoreReport(
        url="https://example.com",
        timestamp="2026-01-01T00:00:00Z",
        score=30,
        checks=[
            CheckResult(id="fail1", name="Fail Check", score=0, max_score=10, severity="fail",
                        message="Failed", suggestion="Fix this thing"),
        ],
        duration_ms=50,
    )
    output = format_report(report)
    assert "Quick wins" in output
    assert "Fix this thing" in output
    assert "pip install" in output  # Low score triggers install suggestion


def test_format_json():
    report = ScoreReport(
        url="https://example.com",
        timestamp="2026-01-01T00:00:00Z",
        score=50,
        checks=[
            CheckResult(id="t", name="T", score=5, max_score=10, severity="warn", message="ok"),
        ],
        duration_ms=100,
    )
    data = json.loads(format_json(report))
    assert data["score"] == 50
    assert data["url"] == "https://example.com"
    assert len(data["checks"]) == 1
    assert data["checks"][0]["id"] == "t"


def test_badge_url():
    assert "brightgreen" in badge_url(90)
    assert "yellow" in badge_url(60)
    assert "red" in badge_url(30)
    assert "Agent-Ready" in badge_url(80)
    assert "Custom" in badge_url(80, "Custom")
    # Logo SVG should be present (TS parity)
    assert "logo=" in badge_url(80)
    assert "link=" in badge_url(80)


def test_badge_markdown():
    md = badge_markdown(85)
    assert "[![Agent-Ready: 85/100]" in md
    assert "brightgreen" in md
    assert "https://github.com/lightlayer-dev/agent-layer-ts" in md
    assert 'Scored by @agent-layer/score' in md

    # Custom label
    md2 = badge_markdown(40, "My Score")
    assert "[![My Score: 40/100]" in md2
    assert "red" in md2

    # Yellow range
    md3 = badge_markdown(65)
    assert "yellow" in md3


# -- Scanner --

@pytest.mark.asyncio
async def test_scan_normalizes_url():
    """scan() adds https:// if missing."""
    async def fake_check(config: ScanConfig) -> CheckResult:
        assert config.url.startswith("https://")
        return CheckResult(id="fake", name="Fake", score=10, max_score=10, severity="pass", message="ok")

    report = await scan("example.com", checks=[fake_check])
    assert report.url == "https://example.com"
    assert report.score == 100


@pytest.mark.asyncio
async def test_scan_calculates_score():
    """Score is normalized to 0-100."""
    async def check_a(config: ScanConfig) -> CheckResult:
        return CheckResult(id="a", name="A", score=5, max_score=10, severity="warn", message="")

    async def check_b(config: ScanConfig) -> CheckResult:
        return CheckResult(id="b", name="B", score=10, max_score=10, severity="pass", message="")

    report = await scan("https://example.com", checks=[check_a, check_b])
    assert report.score == 75  # 15/20 = 75%
    assert len(report.checks) == 2
    assert report.duration_ms >= 0


# -- Check: structured errors --

@pytest.mark.asyncio
async def test_structured_errors_json():
    from agent_layer.score.checks.structured_errors import check_structured_errors

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.headers = {"content-type": "application/json"}

    with patch("agent_layer.score.checks.structured_errors.safe_fetch", return_value=mock_response):
        result = await check_structured_errors(ScanConfig(url="https://example.com"))
        assert result.score == 10
        assert result.severity == "pass"


@pytest.mark.asyncio
async def test_structured_errors_html():
    from agent_layer.score.checks.structured_errors import check_structured_errors

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.headers = {"content-type": "text/html"}

    with patch("agent_layer.score.checks.structured_errors.safe_fetch", return_value=mock_response):
        result = await check_structured_errors(ScanConfig(url="https://example.com"))
        assert result.score == 0
        assert result.severity == "fail"


# -- Check: discovery --

@pytest.mark.asyncio
async def test_discovery_found():
    from agent_layer.score.checks.discovery import check_discovery

    call_count = 0
    async def mock_fetch(url, config, **kw):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        # First two discovery paths return 200
        if call_count <= 2:
            resp.status_code = 200
        else:
            resp.status_code = 404
        return resp

    with patch("agent_layer.score.checks.discovery.safe_fetch", side_effect=mock_fetch):
        result = await check_discovery(ScanConfig(url="https://example.com"))
        assert result.score == 10
        assert result.severity == "pass"


# -- Check: content type --

@pytest.mark.asyncio
async def test_content_type_full():
    from agent_layer.score.checks.content_type import check_content_type

    resp = MagicMock()
    resp.headers = {"content-type": "application/json; charset=utf-8"}

    with patch("agent_layer.score.checks.content_type.safe_fetch", return_value=resp):
        result = await check_content_type(ScanConfig(url="https://example.com"))
        assert result.score == 10
        assert result.severity == "pass"


# -- Check: response time --

@pytest.mark.asyncio
async def test_response_time_fast():
    from agent_layer.score.checks.response_time import check_response_time

    resp = MagicMock()

    with patch("agent_layer.score.checks.response_time.safe_fetch", return_value=resp):
        result = await check_response_time(ScanConfig(url="https://example.com"))
        # Mock returns instantly so avg ~0ms -> score 10
        assert result.score == 10
        assert result.severity == "pass"


# -- Check: x402 --

@pytest.mark.asyncio
async def test_x402_no_support():
    from agent_layer.score.checks.x402 import check_x402

    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}

    async def mock_fetch(url, config, **kw):
        r = MagicMock()
        if "x402" in url:
            r.status_code = 404
        elif "x402_probe" in url:
            r.status_code = 404
        else:
            r.status_code = 200
            r.headers = {}
        return r

    with patch("agent_layer.score.checks.x402.safe_fetch", side_effect=mock_fetch):
        result = await check_x402(ScanConfig(url="https://example.com"))
        assert result.score == 0
        assert "cutting-edge" in result.message


# -- Grade labels --

def test_grade_labels():
    from agent_layer.score.reporter import _grade
    assert _grade(95) == "A"
    assert _grade(85) == "B"
    assert _grade(75) == "C"
    assert _grade(55) == "D"
    assert _grade(40) == "F"
