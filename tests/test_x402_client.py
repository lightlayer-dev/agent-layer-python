"""Tests for x402 client-side helpers."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from agent_layer.x402 import (
    HEADER_PAYMENT_REQUIRED,
    HEADER_PAYMENT_SIGNATURE,
    PaymentPayload,
    PaymentRequirements,
)
from agent_layer.x402_client import (
    extract_payment_requirements,
    is_payment_required,
    wrap_request_with_payment,
)


# ── Fixtures ─────────────────────────────────────────────────────────────

SAMPLE_REQUIREMENTS = PaymentRequirements(
    scheme="exact",
    network="eip155:8453",
    asset="USDC",
    amount="0.01",
    payTo="0xabc",
    maxTimeoutSeconds=60,
)

SAMPLE_PAYMENT_REQUIRED = {
    "x402Version": 1,
    "resource": {"url": "https://example.com/api/data"},
    "accepts": [SAMPLE_REQUIREMENTS.to_camel()],
}

SAMPLE_PAYLOAD = PaymentPayload(
    x402Version=1,
    accepted=SAMPLE_REQUIREMENTS,
    payload={"signature": "0xsigned"},
)


def _encode_pr(pr: dict) -> str:
    return base64.b64encode(json.dumps(pr).encode()).decode()


def _make_402_response(pr: dict) -> httpx.Response:
    encoded = _encode_pr(pr)
    return httpx.Response(
        status_code=402,
        headers={HEADER_PAYMENT_REQUIRED: encoded},
        json=pr,
    )


class MockSigner:
    def __init__(self) -> None:
        self.sign = AsyncMock(return_value=SAMPLE_PAYLOAD)


# ── Tests: is_payment_required ───────────────────────────────────────────


def test_is_payment_required_true():
    response = httpx.Response(status_code=402)
    assert is_payment_required(response) is True


def test_is_payment_required_false():
    assert is_payment_required(httpx.Response(status_code=200)) is False
    assert is_payment_required(httpx.Response(status_code=401)) is False
    assert is_payment_required(httpx.Response(status_code=500)) is False


# ── Tests: extract_payment_requirements ──────────────────────────────────


def test_extract_payment_requirements_decodes_header():
    response = _make_402_response(SAMPLE_PAYMENT_REQUIRED)
    result = extract_payment_requirements(response)
    assert result is not None
    assert result.x402_version == 1
    assert result.accepts[0].pay_to == "0xabc"


def test_extract_payment_requirements_none_when_missing():
    response = httpx.Response(status_code=402)
    assert extract_payment_requirements(response) is None


def test_extract_payment_requirements_none_when_invalid():
    response = httpx.Response(
        status_code=402,
        headers={HEADER_PAYMENT_REQUIRED: "not-valid-base64!!!"},
    )
    assert extract_payment_requirements(response) is None


# ── Tests: wrap_request_with_payment ─────────────────────────────────────


@pytest.mark.asyncio
async def test_wrap_passes_through_non_402():
    ok_response = httpx.Response(status_code=200, text="ok")
    client = AsyncMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(return_value=ok_response)
    signer = MockSigner()

    result = await wrap_request_with_payment(client, signer, "GET", "https://example.com/api/data")

    assert result is ok_response
    client.request.assert_called_once()
    signer.sign.assert_not_called()


@pytest.mark.asyncio
async def test_wrap_signs_and_retries_on_402():
    payment_response = _make_402_response(SAMPLE_PAYMENT_REQUIRED)
    success_response = httpx.Response(status_code=200, text="paid content")

    client = AsyncMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(side_effect=[payment_response, success_response])
    signer = MockSigner()

    result = await wrap_request_with_payment(client, signer, "GET", "https://example.com/api/data")

    assert result is success_response
    assert client.request.call_count == 2
    signer.sign.assert_called_once()

    # Verify retry includes payment header
    retry_call = client.request.call_args_list[1]
    retry_headers = retry_call.kwargs.get("headers") or retry_call[1].get("headers", {})
    assert HEADER_PAYMENT_SIGNATURE in retry_headers


@pytest.mark.asyncio
async def test_wrap_returns_402_when_no_header():
    bare_402 = httpx.Response(status_code=402)
    client = AsyncMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(return_value=bare_402)
    signer = MockSigner()

    result = await wrap_request_with_payment(client, signer, "GET", "https://example.com")

    assert result is bare_402
    signer.sign.assert_not_called()


@pytest.mark.asyncio
async def test_wrap_returns_402_when_empty_accepts():
    empty_accepts = {**SAMPLE_PAYMENT_REQUIRED, "accepts": []}
    response = _make_402_response(empty_accepts)
    client = AsyncMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(return_value=response)
    signer = MockSigner()

    result = await wrap_request_with_payment(client, signer, "GET", "https://example.com")

    assert result is response
    signer.sign.assert_not_called()


@pytest.mark.asyncio
async def test_wrap_preserves_existing_headers():
    payment_response = _make_402_response(SAMPLE_PAYMENT_REQUIRED)
    success_response = httpx.Response(status_code=200, text="ok")

    client = AsyncMock(spec=httpx.AsyncClient)
    client.request = AsyncMock(side_effect=[payment_response, success_response])
    signer = MockSigner()

    await wrap_request_with_payment(
        client,
        signer,
        "GET",
        "https://example.com/api/data",
        headers={"Authorization": "Bearer tok"},
    )

    retry_call = client.request.call_args_list[1]
    retry_headers = retry_call.kwargs.get("headers") or retry_call[1].get("headers", {})
    assert retry_headers.get("Authorization") == "Bearer tok"
    assert HEADER_PAYMENT_SIGNATURE in retry_headers
