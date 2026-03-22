"""x402 Payment Middleware for Flask."""

from __future__ import annotations

from flask import Flask, g, request, jsonify, make_response

from agent_layer.async_utils import run_async_in_sync
from agent_layer.x402 import (
    X402Config,
    HttpFacilitatorClient,
    process_x402_request,
    HEADER_PAYMENT_REQUIRED,
    HEADER_PAYMENT_SIGNATURE,
    HEADER_PAYMENT_RESPONSE,
)


def x402_middleware(app: Flask, config: X402Config) -> None:
    """Register x402 payment middleware on a Flask app."""
    facilitator = config.facilitator or HttpFacilitatorClient(config.facilitator_url)

    @app.before_request
    def check_x402_payment():
        result = run_async_in_sync(
            process_x402_request(
                method=request.method,
                path=request.path,
                url=request.url,
                payment_header=request.headers.get(HEADER_PAYMENT_SIGNATURE),
                config=config,
                facilitator=facilitator,
            )
        )

        if result.action == "pass_through":
            return None

        if result.action == "payment_required":
            resp = make_response(jsonify(result.payment_required.to_camel()), 402)
            resp.headers[HEADER_PAYMENT_REQUIRED] = result.encoded_header
            return resp

        if result.action == "error":
            return jsonify(result.error_body), result.status_code

        # success — store settlement info for after_request
        g.x402 = {
            "payment": result.payment_payload,
            "settlement": result.settle_result,
            "requirements": result.requirements,
        }
        g.x402_settlement_header = result.settlement_b64
        return None

    @app.after_request
    def add_x402_header(response):
        header = getattr(g, "x402_settlement_header", None)
        if header:
            response.headers[HEADER_PAYMENT_RESPONSE] = header
        return response
