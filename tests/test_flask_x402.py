"""Tests for Flask x402 payment middleware."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock

from flask import Flask

from agent_layer.x402 import (
    HEADER_PAYMENT_REQUIRED,
    HEADER_PAYMENT_RESPONSE,
    HEADER_PAYMENT_SIGNATURE,
    SettleResponse,
    VerifyResponse,
    X402Config,
    X402RouteConfig,
    build_requirements,
)
from agent_layer.flask.x402 import x402_middleware


def _make_app(facilitator=None) -> Flask:
    """Create a Flask app with x402 middleware."""
    app = Flask(__name__)
    config = X402Config(
        facilitator_url="https://facilitator.example.com",
        facilitator=facilitator,
        routes={
            "GET /api/weather": X402RouteConfig(
                pay_to="0xabc123",
                price="$0.01",
                network="eip155:8453",
            ),
        },
    )
    x402_middleware(app, config)

    @app.route("/api/weather")
    def weather():
        return "ok"

    @app.route("/api/other")
    def other():
        return "ok"

    @app.route("/api/weather", methods=["POST"])
    def weather_post():
        return "ok"

    return app


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
        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/other")
            assert resp.status_code == 200
            assert resp.data == b"ok"

    def test_wrong_method(self) -> None:
        app = _make_app()
        with app.test_client() as client:
            resp = client.post("/api/weather")
            assert resp.status_code == 200
            assert resp.data == b"ok"


class TestPaymentRequired:
    """Monetized routes without payment should return 402."""

    def test_402_without_payment(self) -> None:
        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/weather")
            assert resp.status_code == 402
            assert HEADER_PAYMENT_REQUIRED in resp.headers

            header_b64 = resp.headers[HEADER_PAYMENT_REQUIRED]
            decoded = json.loads(base64.b64decode(header_b64))
            assert decoded["x402Version"] == 1
            assert len(decoded["accepts"]) == 1
            assert decoded["accepts"][0]["payTo"] == "0xabc123"
            assert decoded["accepts"][0]["network"] == "eip155:8453"

    def test_402_body_is_json(self) -> None:
        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/weather")
            body = resp.get_json()
            assert body["x402Version"] == 1
            assert "accepts" in body
            assert "resource" in body


class TestSuccessfulPayment:
    """Valid payments should pass through with settlement header."""

    def test_valid_payment(self) -> None:
        route_config = X402RouteConfig(pay_to="0xabc123", price="$0.01", network="eip155:8453")
        payment_header = _make_payment_header(route_config)

        mock_facilitator = AsyncMock()
        mock_facilitator.verify.return_value = VerifyResponse(isValid=True)
        mock_facilitator.settle.return_value = SettleResponse(
            success=True, txHash="0xfeed", network="eip155:8453"
        )

        app = _make_app(facilitator=mock_facilitator)
        with app.test_client() as client:
            resp = client.get(
                "/api/weather",
                headers={HEADER_PAYMENT_SIGNATURE: payment_header},
            )
            assert resp.status_code == 200
            assert resp.data == b"ok"
            assert HEADER_PAYMENT_RESPONSE in resp.headers

            settlement = json.loads(base64.b64decode(resp.headers[HEADER_PAYMENT_RESPONSE]))
            assert settlement["success"] is True
            assert settlement["txHash"] == "0xfeed"


class TestVerificationFailed:
    """Invalid payments should be rejected with 402."""

    def test_bad_signature(self) -> None:
        route_config = X402RouteConfig(pay_to="0xabc123", price="$0.01", network="eip155:8453")
        payment_header = _make_payment_header(route_config)

        mock_facilitator = AsyncMock()
        mock_facilitator.verify.return_value = VerifyResponse(
            isValid=False, invalidReason="Bad signature"
        )

        app = _make_app(facilitator=mock_facilitator)
        with app.test_client() as client:
            resp = client.get(
                "/api/weather",
                headers={HEADER_PAYMENT_SIGNATURE: payment_header},
            )
            assert resp.status_code == 402


class TestFacilitatorError:
    """Facilitator errors should return 502."""

    def test_network_error(self) -> None:
        route_config = X402RouteConfig(pay_to="0xabc123", price="$0.01", network="eip155:8453")
        payment_header = _make_payment_header(route_config)

        mock_facilitator = AsyncMock()
        mock_facilitator.verify.side_effect = Exception("Network error")

        app = _make_app(facilitator=mock_facilitator)
        with app.test_client() as client:
            resp = client.get(
                "/api/weather",
                headers={HEADER_PAYMENT_SIGNATURE: payment_header},
            )
            assert resp.status_code == 502


class TestSettlementFailed:
    """Failed settlement should return 402."""

    def test_settlement_failure(self) -> None:
        route_config = X402RouteConfig(pay_to="0xabc123", price="$0.01", network="eip155:8453")
        payment_header = _make_payment_header(route_config)

        mock_facilitator = AsyncMock()
        mock_facilitator.verify.return_value = VerifyResponse(isValid=True)
        mock_facilitator.settle.return_value = SettleResponse(
            success=False, errorReason="Insufficient funds"
        )

        app = _make_app(facilitator=mock_facilitator)
        with app.test_client() as client:
            resp = client.get(
                "/api/weather",
                headers={HEADER_PAYMENT_SIGNATURE: payment_header},
            )
            assert resp.status_code == 402


class TestInvalidPaymentHeader:
    """Malformed payment headers should return 402."""

    def test_invalid_base64(self) -> None:
        app = _make_app()
        with app.test_client() as client:
            resp = client.get(
                "/api/weather",
                headers={HEADER_PAYMENT_SIGNATURE: "not-valid-base64!!!"},
            )
            assert resp.status_code == 402
