"""x402 Payment Middleware for Flask."""

from __future__ import annotations

import base64
import json

from flask import Flask, g, request, jsonify, make_response

from agent_layer.x402 import (
    X402Config,
    HttpFacilitatorClient,
    match_route,
    build_payment_required,
    encode_payment_required,
    decode_payment_payload,
    build_requirements,
    HEADER_PAYMENT_REQUIRED,
    HEADER_PAYMENT_SIGNATURE,
    HEADER_PAYMENT_RESPONSE,
)


def x402_extension(app: Flask, config: X402Config) -> None:
    """Register x402 payment middleware on a Flask app."""
    facilitator = config.facilitator or HttpFacilitatorClient(config.facilitator_url)

    @app.before_request
    def check_x402_payment():
        route_config = match_route(request.method, request.path, config.routes)
        if not route_config:
            return None

        payment_header = request.headers.get(HEADER_PAYMENT_SIGNATURE)
        url = request.url

        if not payment_header:
            pr = build_payment_required(url, route_config)
            resp = make_response(jsonify(pr.to_camel()), 402)
            resp.headers[HEADER_PAYMENT_REQUIRED] = encode_payment_required(pr)
            return resp

        try:
            payload = decode_payment_payload(payment_header)
        except ValueError:
            pr = build_payment_required(url, route_config, "Invalid payment signature format")
            resp = make_response(jsonify(pr.to_camel()), 402)
            resp.headers[HEADER_PAYMENT_REQUIRED] = encode_payment_required(pr)
            return resp

        requirements = build_requirements(route_config)

        # Flask is sync — use async facilitator via asyncio
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    verify_result = pool.submit(
                        asyncio.run, facilitator.verify(payload, requirements)
                    ).result()
            else:
                verify_result = asyncio.run(facilitator.verify(payload, requirements))
        except Exception:
            return jsonify({
                "error": "payment_verification_failed",
                "message": "Could not verify payment with facilitator",
            }), 502

        if not verify_result.is_valid:
            pr = build_payment_required(
                url, route_config,
                verify_result.invalid_reason or "Payment verification failed",
            )
            resp = make_response(jsonify(pr.to_camel()), 402)
            resp.headers[HEADER_PAYMENT_REQUIRED] = encode_payment_required(pr)
            return resp

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    settle_result = pool.submit(
                        asyncio.run, facilitator.settle(payload, requirements)
                    ).result()
            else:
                settle_result = asyncio.run(facilitator.settle(payload, requirements))
        except Exception:
            return jsonify({
                "error": "payment_settlement_failed",
                "message": "Could not settle payment with facilitator",
            }), 502

        if not settle_result.success:
            pr = build_payment_required(
                url, route_config,
                settle_result.error_reason or "Payment settlement failed",
            )
            resp = make_response(jsonify(pr.to_camel()), 402)
            resp.headers[HEADER_PAYMENT_REQUIRED] = encode_payment_required(pr)
            return resp

        settlement_b64 = base64.b64encode(
            json.dumps(settle_result.model_dump(by_alias=True)).encode()
        ).decode()

        g.x402 = {
            "payment": payload,
            "settlement": settle_result,
            "requirements": requirements,
        }
        g.x402_settlement_header = settlement_b64

    @app.after_request
    def add_x402_header(response):
        header = getattr(g, "x402_settlement_header", None)
        if header:
            response.headers[HEADER_PAYMENT_RESPONSE] = header
        return response
