"""Tests for core x402 payment flow."""

import base64
import json
from unittest.mock import AsyncMock

import pytest

from agent_layer.x402 import (
    PaymentPayload,
    PaymentRequirements,
    SettleResponse,
    VerifyResponse,
    X402Config,
    X402RouteConfig,
    encode_settlement,
    process_x402_request,
)


def _make_config() -> X402Config:
    return X402Config(
        facilitator_url="https://facilitator.example.com",
        routes={
            "GET /api/weather": X402RouteConfig(
                pay_to="0xabc",
                price="$0.01",
                network="eip155:8453",
            )
        },
    )


def _make_payment_header(route_config: X402RouteConfig) -> str:
    from agent_layer.x402 import build_requirements

    req = build_requirements(route_config)
    payload = {
        "x402Version": 1,
        "accepted": req.to_camel(),
        "payload": {"signature": "0xdeadbeef"},
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


class TestEncodeSettlement:
    def test_encode(self):
        sr = SettleResponse(success=True, txHash="0x123", network="eip155:8453")
        encoded = encode_settlement(sr)
        decoded = json.loads(base64.b64decode(encoded))
        assert decoded["success"] is True
        assert decoded["txHash"] == "0x123"


class TestProcessX402Request:
    @pytest.mark.asyncio
    async def test_pass_through(self):
        config = _make_config()
        result = await process_x402_request(
            method="GET", path="/api/other", url="http://example.com/api/other",
            payment_header=None, config=config,
        )
        assert result.action == "pass_through"

    @pytest.mark.asyncio
    async def test_payment_required(self):
        config = _make_config()
        result = await process_x402_request(
            method="GET", path="/api/weather", url="http://example.com/api/weather",
            payment_header=None, config=config,
        )
        assert result.action == "payment_required"
        assert result.status_code == 402
        assert result.payment_required is not None
        assert result.encoded_header is not None

    @pytest.mark.asyncio
    async def test_invalid_payment_header(self):
        config = _make_config()
        result = await process_x402_request(
            method="GET", path="/api/weather", url="http://example.com/api/weather",
            payment_header="invalid-base64!!!", config=config,
        )
        assert result.action == "payment_required"
        assert result.status_code == 402

    @pytest.mark.asyncio
    async def test_successful_payment(self):
        config = _make_config()
        route_config = config.routes["GET /api/weather"]
        payment_header = _make_payment_header(route_config)

        facilitator = AsyncMock()
        facilitator.verify.return_value = VerifyResponse(isValid=True)
        facilitator.settle.return_value = SettleResponse(
            success=True, txHash="0xabc", network="eip155:8453"
        )

        result = await process_x402_request(
            method="GET", path="/api/weather", url="http://example.com/api/weather",
            payment_header=payment_header, config=config, facilitator=facilitator,
        )
        assert result.action == "success"
        assert result.settlement_b64 is not None
        assert result.payment_payload is not None

    @pytest.mark.asyncio
    async def test_verification_failed(self):
        config = _make_config()
        route_config = config.routes["GET /api/weather"]
        payment_header = _make_payment_header(route_config)

        facilitator = AsyncMock()
        facilitator.verify.return_value = VerifyResponse(
            isValid=False, invalidReason="Bad signature"
        )

        result = await process_x402_request(
            method="GET", path="/api/weather", url="http://example.com/api/weather",
            payment_header=payment_header, config=config, facilitator=facilitator,
        )
        assert result.action == "payment_required"
        assert result.status_code == 402

    @pytest.mark.asyncio
    async def test_facilitator_error(self):
        config = _make_config()
        route_config = config.routes["GET /api/weather"]
        payment_header = _make_payment_header(route_config)

        facilitator = AsyncMock()
        facilitator.verify.side_effect = Exception("Network error")

        result = await process_x402_request(
            method="GET", path="/api/weather", url="http://example.com/api/weather",
            payment_header=payment_header, config=config, facilitator=facilitator,
        )
        assert result.action == "error"
        assert result.status_code == 502

    @pytest.mark.asyncio
    async def test_settlement_failed(self):
        config = _make_config()
        route_config = config.routes["GET /api/weather"]
        payment_header = _make_payment_header(route_config)

        facilitator = AsyncMock()
        facilitator.verify.return_value = VerifyResponse(isValid=True)
        facilitator.settle.return_value = SettleResponse(
            success=False, errorReason="Insufficient funds"
        )

        result = await process_x402_request(
            method="GET", path="/api/weather", url="http://example.com/api/weather",
            payment_header=payment_header, config=config, facilitator=facilitator,
        )
        assert result.action == "payment_required"
        assert result.status_code == 402
