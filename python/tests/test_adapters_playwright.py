"""Tests for the Playwright attach_signing helper (ADAPT-03).

Uses unittest.mock.AsyncMock for Route + Request + Page so no browser
launch is required. Per D-13 + RESEARCH §"Environment Availability"
the live-browser path is verified separately in Phase 4.
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from wbauth import Identity
from wbauth.adapters import attach_signing


SIG_AGENT_URL = "https://example.invalid/test/"


@pytest.fixture
def anyio_backend():
    return "asyncio"


pytestmark = pytest.mark.anyio


async def test_attach_signing_registers_route_pattern():
    page = MagicMock()
    page.route = AsyncMock()
    identity = Identity.from_test_key(signature_agent_url=SIG_AGENT_URL)
    await attach_signing(page, identity)
    page.route.assert_awaited_once()
    args, _ = page.route.call_args
    assert args[0] == "**/*"
    assert callable(args[1])


def _make_request_mock(method="GET", url="https://example.com/path",
                       headers=None, body=None):
    request = MagicMock()
    request.method = method
    request.url = url
    request.all_headers = AsyncMock(return_value=dict(headers or {}))
    request.post_data_buffer = body
    return request


async def test_handler_signs_and_continues():
    page = MagicMock()
    captured_handler = None

    async def fake_route(pattern, handler):
        nonlocal captured_handler
        captured_handler = handler

    page.route = fake_route
    identity = Identity.from_test_key(signature_agent_url=SIG_AGENT_URL)
    await attach_signing(page, identity)

    route = MagicMock()
    route.continue_ = AsyncMock()
    request = _make_request_mock(headers={"x-existing": "1"})

    await captured_handler(route, request)

    route.continue_.assert_awaited_once()
    sent_headers = route.continue_.call_args.kwargs["headers"]
    assert sent_headers["Signature"]
    assert sent_headers["Signature-Input"]
    assert sent_headers["Signature-Agent"]
    assert sent_headers["x-existing"] == "1", "original headers must be preserved"


async def test_handler_consecutive_requests_have_different_nonces():
    """Statelessness invariant (D-15): each request gets a fresh nonce."""
    page = MagicMock()
    captured_handler = None

    async def fake_route(pattern, handler):
        nonlocal captured_handler
        captured_handler = handler

    page.route = fake_route
    identity = Identity.from_test_key(signature_agent_url=SIG_AGENT_URL)
    await attach_signing(page, identity)

    nonces = []
    nonce_pat = re.compile(r'nonce="([^"]+)"')
    for url in ("https://example.com/a", "https://example.com/b"):
        route = MagicMock()
        route.continue_ = AsyncMock()
        request = _make_request_mock(url=url)
        await captured_handler(route, request)
        sig_input = route.continue_.call_args.kwargs["headers"]["Signature-Input"]
        nonces.append(nonce_pat.search(sig_input).group(1))
    assert nonces[0] != nonces[1]


async def test_handler_ua_injection_when_absent():
    """Open question #4 positive: identity.user_agent → headers when absent."""
    page = MagicMock()
    captured_handler = None

    async def fake_route(pattern, handler):
        nonlocal captured_handler
        captured_handler = handler

    page.route = fake_route
    identity = Identity(
        Identity.from_test_key(SIG_AGENT_URL)._active,
        signature_agent_url=SIG_AGENT_URL,
        user_agent="my-bot/1.0",
    )
    await attach_signing(page, identity)

    route = MagicMock()
    route.continue_ = AsyncMock()
    # Original request has NO UA (default Chromium UA isn't simulated).
    request = _make_request_mock(headers={})
    await captured_handler(route, request)
    sent_headers = route.continue_.call_args.kwargs["headers"]
    assert sent_headers["User-Agent"] == "my-bot/1.0"


async def test_handler_ua_preserved_when_present():
    """Open question #4 negative: do not overwrite an existing UA."""
    page = MagicMock()
    captured_handler = None

    async def fake_route(pattern, handler):
        nonlocal captured_handler
        captured_handler = handler

    page.route = fake_route
    identity = Identity(
        Identity.from_test_key(SIG_AGENT_URL)._active,
        signature_agent_url=SIG_AGENT_URL,
        user_agent="my-bot/1.0",
    )
    await attach_signing(page, identity)

    route = MagicMock()
    route.continue_ = AsyncMock()
    request = _make_request_mock(headers={"User-Agent": "browser-default/1.0"})
    await captured_handler(route, request)
    sent_headers = route.continue_.call_args.kwargs["headers"]
    assert sent_headers["User-Agent"] == "browser-default/1.0"


async def test_handler_signs_post_with_body():
    """POST with body: all three Sig* headers attached; body flows in."""
    page = MagicMock()
    captured_handler = None

    async def fake_route(pattern, handler):
        nonlocal captured_handler
        captured_handler = handler

    page.route = fake_route
    identity = Identity.from_test_key(signature_agent_url=SIG_AGENT_URL)
    await attach_signing(page, identity)

    route = MagicMock()
    route.continue_ = AsyncMock()
    request = _make_request_mock(
        method="POST",
        url="https://example.com/api",
        headers={},
        body=b'{"hello":"world"}',
    )
    await captured_handler(route, request)
    sent_headers = route.continue_.call_args.kwargs["headers"]
    assert sent_headers["Signature"]
    assert sent_headers["Signature-Input"]
    assert sent_headers["Signature-Agent"]
