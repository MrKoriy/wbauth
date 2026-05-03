"""Tests for the httpx WebBotAuth adapter (ADAPT-01).

Uses httpx.MockTransport to capture outgoing requests without live network.
"""
from __future__ import annotations

import re

import httpx
import pytest

from wbauth import Identity
from wbauth.adapters import WebBotAuth


SIG_AGENT_URL = "https://example.invalid/test/"


def _make_capturing_client(identity: Identity) -> tuple[httpx.Client, list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, text="ok")

    client = httpx.Client(
        auth=WebBotAuth(identity),
        transport=httpx.MockTransport(handler),
    )
    return client, captured


def test_sync_get_attaches_three_signed_headers():
    """Smoke (sync): every Sig* header is present and non-empty."""
    identity = Identity.from_test_key(signature_agent_url=SIG_AGENT_URL)
    client, captured = _make_capturing_client(identity)
    client.get("https://example.com/")
    assert len(captured) == 1
    headers = captured[0].headers
    assert headers["Signature"], "Signature header missing"
    assert headers["Signature-Input"], "Signature-Input header missing"
    assert headers["Signature-Agent"], "Signature-Agent header missing"


@pytest.mark.anyio
async def test_async_get_attaches_three_signed_headers(anyio_backend):
    """Smoke (async): same instance works with AsyncClient."""
    identity = Identity.from_test_key(signature_agent_url=SIG_AGENT_URL)
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200, text="ok")

    async with httpx.AsyncClient(
        auth=WebBotAuth(identity),
        transport=httpx.MockTransport(handler),
    ) as client:
        await client.get("https://example.com/")
    assert len(captured) == 1
    headers = captured[0].headers
    assert "Signature" in headers
    assert "Signature-Input" in headers
    assert "Signature-Agent" in headers


def test_consecutive_requests_have_different_nonces():
    """Statelessness invariant (D-15): each request gets a fresh nonce."""
    identity = Identity.from_test_key(signature_agent_url=SIG_AGENT_URL)
    client, captured = _make_capturing_client(identity)
    client.get("https://example.com/a")
    client.get("https://example.com/b")
    nonce_pat = re.compile(r'nonce="([^"]+)"')
    n1 = nonce_pat.search(captured[0].headers["Signature-Input"]).group(1)
    n2 = nonce_pat.search(captured[1].headers["Signature-Input"]).group(1)
    assert n1 != n2, "consecutive requests must use distinct nonces (no caching)"


def test_ua_injection_when_absent():
    """Open question #4 (positive branch): identity.user_agent → request UA.

    httpx auto-injects a default `python-httpx/X.Y` User-Agent on every
    request. To verify the adapter's UA-injection branch actually fires
    when the request truly has no UA at signing time, we build the request
    manually and pop the auto-set UA before sending.
    """
    identity = Identity(
        Identity.from_test_key(SIG_AGENT_URL)._active,
        signature_agent_url=SIG_AGENT_URL,
        user_agent="my-bot/1.0 (+https://example.com)",
    )
    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200)

    client = httpx.Client(
        auth=WebBotAuth(identity),
        transport=httpx.MockTransport(handler),
    )
    req = client.build_request("GET", "https://example.com/")
    # Remove httpx's auto-injected default UA so the adapter sees no UA at signing.
    if "User-Agent" in req.headers:
        del req.headers["User-Agent"]
    client.send(req)
    assert captured[0].headers["User-Agent"] == "my-bot/1.0 (+https://example.com)"


def test_ua_preserved_when_caller_set_one():
    """Open question #4 (negative branch): caller's UA wins; adapter does not overwrite."""
    identity = Identity(
        Identity.from_test_key(SIG_AGENT_URL)._active,
        signature_agent_url=SIG_AGENT_URL,
        user_agent="my-bot/1.0",
    )
    client, captured = _make_capturing_client(identity)
    client.get("https://example.com/", headers={"User-Agent": "caller-set/2.0"})
    assert captured[0].headers["User-Agent"] == "caller-set/2.0"


def test_post_with_body_signs_correctly():
    """POST + body: requires_request_body=True must let us read content."""
    identity = Identity.from_test_key(signature_agent_url=SIG_AGENT_URL)
    client, captured = _make_capturing_client(identity)
    client.post("https://example.com/api", content=b'{"hello":"world"}')
    headers = captured[0].headers
    assert "Signature" in headers
    assert "Signature-Input" in headers
    assert "Signature-Agent" in headers
    # Body must have been readable (not consumed/empty by the time we see it)
    assert captured[0].content == b'{"hello":"world"}'


@pytest.fixture
def anyio_backend():
    return "asyncio"
