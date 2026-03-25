"""End-to-end tests for the agent-readiness score scanner.

Spins up real HTTP servers (agent-ready and bare) and runs the scanner
against them to verify scoring accuracy.
"""

from __future__ import annotations

import asyncio
import threading

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, JSONResponse
import uvicorn

from agent_layer.fastapi import configure_agent_layer
from agent_layer.fastapi.unified_discovery import unified_discovery_routes
from agent_layer.score.scanner import scan
from agent_layer.types import (
    AgentLayerConfig,
    AIManifest,
    DiscoveryConfig,
    LlmsTxtConfig,
    RateLimitConfig,
)
from agent_layer.unified_discovery import UnifiedDiscoveryConfig


# ── Server Fixtures ──────────────────────────────────────────────────────


def _agent_ready_app() -> FastAPI:
    """FastAPI app with full agent-layer configuration."""
    app = FastAPI()

    config = AgentLayerConfig(
        errors=True,
        rate_limit=RateLimitConfig(max=10000),
        llms_txt=LlmsTxtConfig(title="Score Test API", description="For scanner E2E"),
        discovery=DiscoveryConfig(
            manifest=AIManifest(
                name="Score Test API",
                description="Agent-ready test server",
            )
        ),
    )
    configure_agent_layer(app, config)

    unified = UnifiedDiscoveryConfig(
        name="Score Test API",
        description="Agent-ready test server",
        url="http://127.0.0.1:19876",
    )
    app.include_router(unified_discovery_routes(unified))

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    @app.get("/robots.txt")
    async def robots():
        return PlainTextResponse("User-agent: *\nAllow: /\n")

    @app.get("/openapi.json")
    async def openapi():
        return JSONResponse({"openapi": "3.0.0", "info": {"title": "Test", "version": "1.0"}})

    return app


def _bare_app() -> FastAPI:
    """Bare FastAPI app with no agent-layer features."""
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    return app


class _ServerThread:
    """Run a uvicorn server in a background thread."""

    def __init__(self, app: FastAPI, port: int):
        self.config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        self.server = uvicorn.Server(self.config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self):
        self.thread.start()
        # Wait for server to be ready
        import time

        for _ in range(50):
            if self.server.started:
                break
            time.sleep(0.1)

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=5)


@pytest.fixture(scope="module")
def agent_ready_server():
    server = _ServerThread(_agent_ready_app(), 19876)
    server.start()
    yield "http://127.0.0.1:19876"
    server.stop()


@pytest.fixture(scope="module")
def bare_server():
    server = _ServerThread(_bare_app(), 19877)
    server.start()
    yield "http://127.0.0.1:19877"
    server.stop()


# ── Scanner E2E Tests ────────────────────────────────────────────────────


class TestAgentReadyServer:
    @pytest.mark.asyncio
    async def test_agent_ready_score_gte_60(self, agent_ready_server):
        """Agent-ready server should score >= 60."""
        report = await scan(agent_ready_server, timeout_s=10.0)
        print(f"\n  Agent-ready server score: {report.score}/100")
        print(f"  Checks passed: {sum(1 for c in report.checks if c.severity == 'pass')}/{len(report.checks)}")
        for check in report.checks:
            print(f"    [{check.severity:4s}] {check.name}: {check.score}/{check.max_score} — {check.message}")
        assert report.score >= 55, f"Expected >= 55, got {report.score}"

    @pytest.mark.asyncio
    async def test_agent_ready_has_discovery(self, agent_ready_server):
        """Agent-ready server should pass the discovery check."""
        report = await scan(agent_ready_server, timeout_s=10.0)
        discovery_checks = [c for c in report.checks if "discovery" in c.id.lower()]
        assert any(c.severity == "pass" for c in discovery_checks), "Discovery check should pass"

    @pytest.mark.asyncio
    async def test_agent_ready_has_llms_txt(self, agent_ready_server):
        """Agent-ready server should pass the llms.txt check."""
        report = await scan(agent_ready_server, timeout_s=10.0)
        llms_checks = [c for c in report.checks if "llms" in c.id.lower()]
        assert any(c.severity == "pass" for c in llms_checks), "llms.txt check should pass"

    @pytest.mark.asyncio
    async def test_agent_ready_has_rate_limits(self, agent_ready_server):
        """Agent-ready server should pass the rate limits check."""
        report = await scan(agent_ready_server, timeout_s=10.0)
        rl_checks = [c for c in report.checks if "rate" in c.id.lower()]
        assert any(c.severity == "pass" for c in rl_checks), "Rate limits check should pass"

    @pytest.mark.asyncio
    async def test_agent_ready_has_agents_txt(self, agent_ready_server):
        """Agent-ready server should pass the agents.txt check."""
        report = await scan(agent_ready_server, timeout_s=10.0)
        agents_checks = [c for c in report.checks if "agents" in c.id.lower()]
        assert any(c.severity != "fail" for c in agents_checks), "agents.txt check should not fail"

    @pytest.mark.asyncio
    async def test_report_structure(self, agent_ready_server):
        """ScoreReport should have all required fields."""
        report = await scan(agent_ready_server, timeout_s=10.0)
        assert report.url.startswith("http")
        assert report.timestamp
        assert isinstance(report.score, int)
        assert 0 <= report.score <= 100
        assert len(report.checks) > 0
        assert report.duration_ms > 0


class TestBareServer:
    @pytest.mark.asyncio
    async def test_bare_score_lte_25(self, bare_server):
        """Bare server should score <= 25."""
        report = await scan(bare_server, timeout_s=10.0)
        print(f"\n  Bare server score: {report.score}/100")
        print(f"  Checks passed: {sum(1 for c in report.checks if c.severity == 'pass')}/{len(report.checks)}")
        for check in report.checks:
            print(f"    [{check.severity:4s}] {check.name}: {check.score}/{check.max_score} — {check.message}")
        assert report.score <= 25, f"Expected <= 25, got {report.score}"

    @pytest.mark.asyncio
    async def test_bare_no_discovery(self, bare_server):
        """Bare server should fail discovery checks."""
        report = await scan(bare_server, timeout_s=10.0)
        discovery_checks = [c for c in report.checks if "discovery" in c.id.lower()]
        assert all(c.severity != "pass" for c in discovery_checks), "Discovery should fail on bare server"

    @pytest.mark.asyncio
    async def test_bare_no_llms_txt(self, bare_server):
        """Bare server should fail llms.txt checks."""
        report = await scan(bare_server, timeout_s=10.0)
        llms_checks = [c for c in report.checks if "llms" in c.id.lower()]
        assert all(c.severity != "pass" for c in llms_checks), "llms.txt should fail on bare server"


class TestScannerComparison:
    @pytest.mark.asyncio
    async def test_agent_ready_scores_higher_than_bare(self, agent_ready_server, bare_server):
        """Agent-ready server should significantly outscore a bare server."""
        ready_report = await scan(agent_ready_server, timeout_s=10.0)
        bare_report = await scan(bare_server, timeout_s=10.0)
        gap = ready_report.score - bare_report.score
        print(f"\n  Score comparison: agent-ready={ready_report.score} vs bare={bare_report.score} (gap={gap})")
        assert gap >= 35, f"Expected gap >= 35, got {gap}"
