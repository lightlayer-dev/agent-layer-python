"""Tests for Django x402 payment middleware."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        ROOT_URLCONF=__name__,
        ALLOWED_HOSTS=["*"],
        SECRET_KEY="test-secret",
        AGENT_LAYER_X402={
            "facilitator_url": "https://facilitator.example.com",
            "routes": {
                "GET /api/weather": {
                    "pay_to": "0xabc123",
                    "price": "$0.01",
                    "network": "eip155:8453",
                },
            },
        },
    )
    django.setup()
elif not hasattr(settings, "AGENT_LAYER_X402"):
    # Settings already configured by another test file — add x402 config.
    settings.AGENT_LAYER_X402 = {
        "facilitator_url": "https://facilitator.example.com",
        "routes": {
            "GET /api/weather": {
                "pay_to": "0xabc123",
                "price": "$0.01",
                "network": "eip155:8453",
            },
        },
    }

from django.http import HttpResponse
from django.test import RequestFactory

from agent_layer.x402 import (
    HEADER_PAYMENT_REQUIRED,
    HEADER_PAYMENT_RESPONSE,
    HEADER_PAYMENT_SIGNATURE,
    SettleResponse,
    VerifyResponse,
    X402RouteConfig,
    build_requirements,
)
from agent_layer.django.x402 import X402PaymentMiddleware


def _dummy_response(request):  # type: ignore[no-untyped-def]
    return HttpResponse("ok")


def _make_payment_header(route_config: X402RouteConfig) -> str:
    req = build_requirements(route_config)
    payload = {
        "x402Version": 1,
        "accepted": req.to_camel(),
        "payload": {"signature": "0xdeadbeef"},
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


class TestPassThrough:
    """Non-monetized routes should pass through without payment."""

    def test_non_monetized_route(self) -> None:
        middleware = X402PaymentMiddleware(_dummy_response)
        factory = RequestFactory()
        request = factory.get("/api/other")
        resp = middleware(request)
        assert resp.status_code == 200
        assert resp.content == b"ok"

    def test_wrong_method(self) -> None:
        middleware = X402PaymentMiddleware(_dummy_response)
        factory = RequestFactory()
        request = factory.post("/api/weather")
        resp = middleware(request)
        assert resp.status_code == 200
        assert resp.content == b"ok"


class TestPaymentRequired:
    """Monetized routes without payment should return 402."""

    def test_402_without_payment(self) -> None:
        middleware = X402PaymentMiddleware(_dummy_response)
        factory = RequestFactory()
        request = factory.get("/api/weather")
        resp = middleware(request)
        assert resp.status_code == 402
        assert HEADER_PAYMENT_REQUIRED in resp

        # Decode and verify the header
        header_b64 = resp[HEADER_PAYMENT_REQUIRED]
        decoded = json.loads(base64.b64decode(header_b64))
        assert decoded["x402Version"] == 1
        assert len(decoded["accepts"]) == 1
        assert decoded["accepts"][0]["payTo"] == "0xabc123"
        assert decoded["accepts"][0]["network"] == "eip155:8453"

    def test_402_body_is_json(self) -> None:
        middleware = X402PaymentMiddleware(_dummy_response)
        factory = RequestFactory()
        request = factory.get("/api/weather")
        resp = middleware(request)
        body = json.loads(resp.content)
        assert body["x402Version"] == 1
        assert "accepts" in body
        assert "resource" in body


class TestSuccessfulPayment:
    """Valid payments should pass through with settlement header."""

    def test_valid_payment(self) -> None:
        route_config = X402RouteConfig(
            pay_to="0xabc123", price="$0.01", network="eip155:8453"
        )
        payment_header = _make_payment_header(route_config)

        mock_facilitator = AsyncMock()
        mock_facilitator.verify.return_value = VerifyResponse(isValid=True)
        mock_facilitator.settle.return_value = SettleResponse(
            success=True, txHash="0xfeed", network="eip155:8453"
        )

        middleware = X402PaymentMiddleware(_dummy_response)
        middleware.facilitator = mock_facilitator

        factory = RequestFactory()
        header_key = f"HTTP_{HEADER_PAYMENT_SIGNATURE.upper().replace('-', '_')}"
        request = factory.get("/api/weather", **{header_key: payment_header})
        resp = middleware(request)

        assert resp.status_code == 200
        assert resp.content == b"ok"
        assert HEADER_PAYMENT_RESPONSE in resp

        # Verify settlement data
        settlement = json.loads(base64.b64decode(resp[HEADER_PAYMENT_RESPONSE]))
        assert settlement["success"] is True
        assert settlement["txHash"] == "0xfeed"

    def test_payment_data_attached_to_request(self) -> None:
        route_config = X402RouteConfig(
            pay_to="0xabc123", price="$0.01", network="eip155:8453"
        )
        payment_header = _make_payment_header(route_config)

        mock_facilitator = AsyncMock()
        mock_facilitator.verify.return_value = VerifyResponse(isValid=True)
        mock_facilitator.settle.return_value = SettleResponse(
            success=True, txHash="0xfeed", network="eip155:8453"
        )

        captured_request = {}

        def capturing_response(request):  # type: ignore[no-untyped-def]
            captured_request["x402"] = getattr(request, "x402", None)
            return HttpResponse("ok")

        middleware = X402PaymentMiddleware(capturing_response)
        middleware.facilitator = mock_facilitator

        factory = RequestFactory()
        header_key = f"HTTP_{HEADER_PAYMENT_SIGNATURE.upper().replace('-', '_')}"
        request = factory.get("/api/weather", **{header_key: payment_header})
        middleware(request)

        assert captured_request["x402"] is not None
        assert "payment" in captured_request["x402"]
        assert "settlement" in captured_request["x402"]
        assert "requirements" in captured_request["x402"]


class TestVerificationFailed:
    """Invalid payments should be rejected with 402."""

    def test_bad_signature(self) -> None:
        route_config = X402RouteConfig(
            pay_to="0xabc123", price="$0.01", network="eip155:8453"
        )
        payment_header = _make_payment_header(route_config)

        mock_facilitator = AsyncMock()
        mock_facilitator.verify.return_value = VerifyResponse(
            isValid=False, invalidReason="Bad signature"
        )

        middleware = X402PaymentMiddleware(_dummy_response)
        middleware.facilitator = mock_facilitator

        factory = RequestFactory()
        header_key = f"HTTP_{HEADER_PAYMENT_SIGNATURE.upper().replace('-', '_')}"
        request = factory.get("/api/weather", **{header_key: payment_header})
        resp = middleware(request)

        assert resp.status_code == 402


class TestFacilitatorError:
    """Facilitator errors should return 502."""

    def test_network_error(self) -> None:
        route_config = X402RouteConfig(
            pay_to="0xabc123", price="$0.01", network="eip155:8453"
        )
        payment_header = _make_payment_header(route_config)

        mock_facilitator = AsyncMock()
        mock_facilitator.verify.side_effect = Exception("Network error")

        middleware = X402PaymentMiddleware(_dummy_response)
        middleware.facilitator = mock_facilitator

        factory = RequestFactory()
        header_key = f"HTTP_{HEADER_PAYMENT_SIGNATURE.upper().replace('-', '_')}"
        request = factory.get("/api/weather", **{header_key: payment_header})
        resp = middleware(request)

        assert resp.status_code == 502


class TestSettlementFailed:
    """Failed settlement should return 402."""

    def test_settlement_failure(self) -> None:
        route_config = X402RouteConfig(
            pay_to="0xabc123", price="$0.01", network="eip155:8453"
        )
        payment_header = _make_payment_header(route_config)

        mock_facilitator = AsyncMock()
        mock_facilitator.verify.return_value = VerifyResponse(isValid=True)
        mock_facilitator.settle.return_value = SettleResponse(
            success=False, errorReason="Insufficient funds"
        )

        middleware = X402PaymentMiddleware(_dummy_response)
        middleware.facilitator = mock_facilitator

        factory = RequestFactory()
        header_key = f"HTTP_{HEADER_PAYMENT_SIGNATURE.upper().replace('-', '_')}"
        request = factory.get("/api/weather", **{header_key: payment_header})
        resp = middleware(request)

        assert resp.status_code == 402


class TestSettingsConfiguration:
    """Middleware should read config from Django settings."""

    def test_reads_from_settings(self) -> None:
        middleware = X402PaymentMiddleware(_dummy_response)
        assert middleware.config.facilitator_url == "https://facilitator.example.com"
        assert "GET /api/weather" in middleware.config.routes

    def test_invalid_payment_header(self) -> None:
        middleware = X402PaymentMiddleware(_dummy_response)
        factory = RequestFactory()
        header_key = f"HTTP_{HEADER_PAYMENT_SIGNATURE.upper().replace('-', '_')}"
        request = factory.get("/api/weather", **{header_key: "not-valid-base64!!!"})
        resp = middleware(request)
        # Invalid payment header should still return 402 (re-request payment)
        assert resp.status_code == 402
