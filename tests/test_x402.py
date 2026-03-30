"""Tests for x402 payment protocol — core + FastAPI integration."""

from __future__ import annotations

import base64
import json

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from agent_layer.x402 import (
    X402_VERSION,
    HEADER_PAYMENT_REQUIRED,
    HEADER_PAYMENT_SIGNATURE,
    HEADER_PAYMENT_RESPONSE,
    VerifyResponse,
    SettleResponse,
    X402Config,
    X402RouteConfig,
    resolve_price,
    build_requirements,
    build_payment_required,
    encode_payment_required,
    decode_payment_payload,
    match_route,
)
from agent_layer.fastapi.x402 import x402_middleware


# ── Core helpers ─────────────────────────────────────────────────────────


class TestResolvePrice:
    def test_dollar_string(self):
        result = resolve_price("$0.001")
        assert result == {"amount": "0.001", "asset": "USDC"}

    def test_dollar_string_whole(self):
        result = resolve_price("$5")
        assert result == {"amount": "5", "asset": "USDC"}

    def test_invalid_string(self):
        with pytest.raises(ValueError, match="Invalid price string"):
            resolve_price("0.001")

    def test_dict_passthrough(self):
        p = {"amount": "100", "asset": "ETH"}
        assert resolve_price(p) == p


class TestBuildRequirements:
    def test_defaults(self):
        config = X402RouteConfig(
            pay_to="0xABC",
            price="$0.01",
            network="eip155:8453",
        )
        req = build_requirements(config)
        assert req.scheme == "exact"
        assert req.asset == "USDC"
        assert req.amount == "0.01"
        assert req.pay_to == "0xABC"
        assert req.max_timeout_seconds == 60


class TestEncodeDecodePipeline:
    def test_round_trip(self):
        config = X402RouteConfig(pay_to="0xABC", price="$1", network="eip155:8453")
        pr = build_payment_required("https://example.com/api", config)
        encoded = encode_payment_required(pr)
        decoded = json.loads(base64.b64decode(encoded))
        assert decoded["x402Version"] == X402_VERSION
        assert decoded["accepts"][0]["payTo"] == "0xABC"

    def test_decode_payment_payload(self):
        payload_data = {
            "x402Version": 1,
            "accepted": {
                "scheme": "exact",
                "network": "eip155:8453",
                "asset": "USDC",
                "amount": "0.01",
                "payTo": "0xABC",
                "maxTimeoutSeconds": 60,
                "extra": {},
            },
            "payload": {"signature": "0xSig"},
        }
        header = base64.b64encode(json.dumps(payload_data).encode()).decode()
        result = decode_payment_payload(header)
        assert result.x402_version == 1
        assert result.accepted.pay_to == "0xABC"

    def test_decode_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid"):
            decode_payment_payload("not-base64!!!")


class TestMatchRoute:
    def test_match(self):
        routes = {
            "GET /api/weather": X402RouteConfig(pay_to="0x1", price="$0.01", network="eip155:8453")
        }
        assert match_route("GET", "/api/weather", routes) is not None
        assert match_route("POST", "/api/weather", routes) is None
        assert match_route("GET", "/other", routes) is None


# ── FastAPI integration ──────────────────────────────────────────────────


def _make_payment_header() -> str:
    payload = {
        "x402Version": 1,
        "accepted": {
            "scheme": "exact",
            "network": "eip155:8453",
            "asset": "USDC",
            "amount": "0.001",
            "payTo": "0xPayee",
            "maxTimeoutSeconds": 60,
            "extra": {},
        },
        "payload": {"signature": "0xSig"},
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


class MockFacilitator:
    def __init__(self):
        self.verify_result = VerifyResponse(isValid=True)
        self.settle_result = SettleResponse(success=True, txHash="0xabc123")
        self.verify_called = False
        self.settle_called = False

    async def verify(self, payload, requirements):
        self.verify_called = True
        return self.verify_result

    async def settle(self, payload, requirements):
        self.settle_called = True
        return self.settle_result


def _make_app(facilitator=None) -> FastAPI:
    fac = facilitator or MockFacilitator()
    config = X402Config(
        facilitator_url="https://facilitator.example.com",
        facilitator=fac,
        routes={
            "GET /api/weather": X402RouteConfig(
                pay_to="0xPayee",
                price="$0.001",
                network="eip155:8453",
                description="Weather data",
            ),
        },
    )
    app = FastAPI()
    app.middleware("http")(x402_middleware(config))

    @app.get("/api/weather")
    async def weather():
        return {"temp": 72}

    @app.get("/free")
    async def free():
        return {"status": "ok"}

    return app


@pytest.mark.asyncio
async def test_free_route_passes_through():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/free")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_402_when_no_payment():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/weather")
    assert res.status_code == 402
    body = res.json()
    assert body["x402Version"] == 1
    assert body["accepts"][0]["asset"] == "USDC"
    assert HEADER_PAYMENT_REQUIRED in res.headers


@pytest.mark.asyncio
async def test_successful_payment():
    fac = MockFacilitator()
    app = _make_app(fac)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/api/weather",
            headers={HEADER_PAYMENT_SIGNATURE: _make_payment_header()},
        )
    assert res.status_code == 200
    assert res.json() == {"temp": 72}
    assert fac.verify_called
    assert fac.settle_called
    assert HEADER_PAYMENT_RESPONSE in res.headers


@pytest.mark.asyncio
async def test_invalid_payment_header():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/api/weather",
            headers={HEADER_PAYMENT_SIGNATURE: "not-valid!!!"},
        )
    assert res.status_code == 402
    assert "Invalid payment signature" in res.json().get("error", "")


@pytest.mark.asyncio
async def test_verification_fails():
    fac = MockFacilitator()
    fac.verify_result = VerifyResponse(isValid=False, invalidReason="Insufficient funds")
    app = _make_app(fac)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/api/weather",
            headers={HEADER_PAYMENT_SIGNATURE: _make_payment_header()},
        )
    assert res.status_code == 402
    assert "Insufficient funds" in res.json().get("error", "")


@pytest.mark.asyncio
async def test_settlement_fails():
    fac = MockFacilitator()
    fac.settle_result = SettleResponse(success=False, errorReason="Timeout")
    app = _make_app(fac)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/api/weather",
            headers={HEADER_PAYMENT_SIGNATURE: _make_payment_header()},
        )
    assert res.status_code == 402
    assert "Timeout" in res.json().get("error", "")


@pytest.mark.asyncio
async def test_facilitator_verify_error():
    fac = MockFacilitator()

    async def bad_verify(p, r):
        raise ConnectionError("Network down")

    fac.verify = bad_verify  # type: ignore
    app = _make_app(fac)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/api/weather",
            headers={HEADER_PAYMENT_SIGNATURE: _make_payment_header()},
        )
    assert res.status_code == 502
    assert res.json()["error"] == "payment_verification_failed"


@pytest.mark.asyncio
async def test_facilitator_settle_error():
    fac = MockFacilitator()

    async def bad_settle(p, r):
        raise ConnectionError("Network down")

    fac.settle = bad_settle  # type: ignore
    app = _make_app(fac)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/api/weather",
            headers={HEADER_PAYMENT_SIGNATURE: _make_payment_header()},
        )
    assert res.status_code == 502
    assert res.json()["error"] == "payment_settlement_failed"
