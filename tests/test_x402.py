"""Tests for x402 payments module."""

import pytest

from agent_layer.core.x402 import (
    X402Config,
    X402RouteConfig,
    build_payment_required,
    build_requirements,
    decode_payment_payload,
    encode_payment_required,
    handle_x402,
    match_route,
    resolve_price,
)


class TestResolvePrice:
    def test_dollar_string(self):
        result = resolve_price("$0.01")
        assert result == {"amount": "0.01", "asset": "USDC"}

    def test_dollar_string_precision(self):
        result = resolve_price("$0.001")
        assert result["amount"] == "0.001"

    def test_invalid_price(self):
        with pytest.raises(ValueError):
            resolve_price("0.01")

    def test_object_passthrough(self):
        price = {"amount": "1.0", "asset": "ETH"}
        assert resolve_price(price) == price


class TestBuildRequirements:
    def test_defaults(self):
        route = X402RouteConfig(pay_to="0xABC", price="$0.01")
        req = build_requirements(route)
        assert req.scheme == "exact"
        assert req.network == "eip155:8453"
        assert req.asset == "USDC"
        assert req.amount == "0.01"
        assert req.pay_to == "0xABC"
        assert req.max_timeout_seconds == 60

    def test_custom(self):
        route = X402RouteConfig(
            pay_to="0xABC", price="$1.00",
            scheme="escrow", network="solana:mainnet",
            max_timeout_seconds=120,
        )
        req = build_requirements(route)
        assert req.scheme == "escrow"
        assert req.network == "solana:mainnet"
        assert req.max_timeout_seconds == 120


class TestBuildPaymentRequired:
    def test_basic(self):
        req = build_requirements(X402RouteConfig(pay_to="0xABC", price="$0.01"))
        body = build_payment_required("https://api.example.com/weather", req)
        assert body["x402Version"] == 1
        assert body["resource"] == "https://api.example.com/weather"
        assert len(body["accepts"]) == 1
        assert body["accepts"][0]["payTo"] == "0xABC"

    def test_with_error(self):
        req = build_requirements(X402RouteConfig(pay_to="0xABC", price="$0.01"))
        body = build_payment_required("https://api.example.com", req, error="Invalid payment")
        assert body["error"] == "Invalid payment"


class TestEncodeDecodRoundtrip:
    def test_roundtrip(self):
        original = {"x402Version": 1, "resource": "https://example.com"}
        encoded = encode_payment_required(original)
        decoded = decode_payment_payload(encoded)
        assert decoded == original


class TestMatchRoute:
    def test_match(self):
        routes = {"GET /api/weather": X402RouteConfig(pay_to="0xABC", price="$0.01")}
        result = match_route("GET", "/api/weather", routes)
        assert result is not None
        assert result.pay_to == "0xABC"

    def test_no_match(self):
        routes = {"GET /api/weather": X402RouteConfig(pay_to="0xABC", price="$0.01")}
        assert match_route("POST", "/api/weather", routes) is None

    def test_case_insensitive_method(self):
        routes = {"GET /api/weather": X402RouteConfig(pay_to="0xABC", price="$0.01")}
        result = match_route("get", "/api/weather", routes)
        assert result is not None


class TestHandleX402:
    @pytest.mark.asyncio
    async def test_skip_unmatched(self):
        config = X402Config()
        result = await handle_x402("GET", "/api/free", "https://example.com/api/free", None, config)
        assert result["action"] == "skip"

    @pytest.mark.asyncio
    async def test_payment_required_no_header(self):
        config = X402Config(
            routes={"GET /api/weather": X402RouteConfig(pay_to="0xABC", price="$0.01")}
        )
        result = await handle_x402(
            "GET", "/api/weather", "https://example.com/api/weather", None, config
        )
        assert result["action"] == "payment_required"
        assert result["status"] == 402

    @pytest.mark.asyncio
    async def test_invalid_payment_header(self):
        config = X402Config(
            routes={"GET /api/weather": X402RouteConfig(pay_to="0xABC", price="$0.01")}
        )
        result = await handle_x402(
            "GET", "/api/weather", "https://example.com/api/weather", "not-valid-base64!!!", config
        )
        assert result["action"] == "payment_required"

    @pytest.mark.asyncio
    async def test_no_facilitator(self):
        import base64, json
        payment = base64.b64encode(json.dumps({"test": True}).encode()).decode()
        config = X402Config(
            routes={"GET /api/weather": X402RouteConfig(pay_to="0xABC", price="$0.01")}
        )
        result = await handle_x402(
            "GET", "/api/weather", "https://example.com/api/weather", payment, config
        )
        assert result["action"] == "error"
        assert result["status"] == 502
