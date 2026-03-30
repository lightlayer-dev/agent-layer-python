"""Tests for FastAPI robots_txt route."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agent_layer.fastapi.robots_txt import robots_txt_routes
from agent_layer.robots_txt import RobotsTxtConfig


@pytest.fixture
def app() -> FastAPI:
    fa = FastAPI()
    fa.include_router(robots_txt_routes())
    return fa


@pytest.fixture
def custom_app() -> FastAPI:
    fa = FastAPI()
    config = RobotsTxtConfig(
        ai_agent_policy="disallow",
        sitemaps=["https://example.com/sitemap.xml"],
    )
    fa.include_router(robots_txt_routes(config))
    return fa


@pytest.mark.asyncio
async def test_serves_robots_txt(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/robots.txt")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "User-agent: *" in resp.text
    assert "GPTBot" in resp.text


@pytest.mark.asyncio
async def test_cache_control(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/robots.txt")
    assert "max-age=86400" in resp.headers.get("cache-control", "")


@pytest.mark.asyncio
async def test_custom_config(custom_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=custom_app), base_url="http://test"
    ) as client:
        resp = await client.get("/robots.txt")
    assert resp.status_code == 200
    assert "Disallow: /" in resp.text
    assert "Sitemap: https://example.com/sitemap.xml" in resp.text
