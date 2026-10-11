"""Regression tests for defects found in the 2026-10 audit.

Each test pins the fixed behaviour so the bug cannot come back.
"""
from __future__ import annotations

import base64
import hashlib

import httpx
import pytest
import requests
import responses

from wbauth import Identity
from wbauth.adapters import WebBotAuth, WebBotAuthAdapter, attach_signing, signed_session
from wbauth.normalized_request import NormalizedRequest
from wbauth.policy import inspect
from wbauth.policy.cache import PolicyCache
from wbauth.policy.inspector import _reset_cache_for_tests
from wbauth.policy.verdict import compute_verdict
from wbauth.signer import sign

SIG_AGENT_URL = "https://example.invalid/agent/"
ROBOTS = "User-agent: *\nDisallow: /private\n"


@pytest.fixture
def identity():
    return Identity.from_test_key(signature_agent_url=SIG_AGENT_URL)


@pytest.fixture
def ua_identity():
    return Identity.from_test_key(
        signature_agent_url=SIG_AGENT_URL,
        user_agent="MyBot/1.0 (+https://example.invalid/bot)",
    )


@pytest.fixture(autouse=True)
def _clear_cache():
    _reset_cache_for_tests()
    yield
    _reset_cache_for_tests()


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _mock_site(httpx_mock, robots: str = ROBOTS) -> None:
    httpx_mock.add_response(
        url="https://example.com/robots.txt", text=robots,
        headers={"content-type": "text/plain"}, is_reusable=True,
    )
    for p in ("/ai.txt", "/llms.txt", "/.well-known/http-message-signatures-directory"):
        httpx_mock.add_response(
            url=f"https://example.com{p}", status_code=404, is_reusable=True,
        )


# --------------------------------------------------------------------------
# 1. Policy engine correctness
# --------------------------------------------------------------------------

@pytest.mark.anyio
async def test_robots_cache_is_path_specific(httpx_mock):
    _mock_site(httpx_mock)
    first = await inspect("https://example.com/public")
    second = await inspect("https://example.com/private/secret")
    assert first.verdict == "allowed"
    assert second.verdict == "forbidden"


@pytest.mark.anyio
async def test_robots_disallow_without_cache(httpx_mock):
    """Control: the same path evaluated on a cold cache IS forbidden."""
    _mock_site(httpx_mock)
    policy = await inspect("https://example.com/private/secret")
    assert policy.verdict == "forbidden"


@pytest.mark.anyio
async def test_missing_endpoints_are_negatively_cached(httpx_mock):
    _mock_site(httpx_mock)
    await inspect("https://example.com/a")
    before = len(httpx_mock.get_requests())
    await inspect("https://example.com/a")
    assert len(httpx_mock.get_requests()) == before


@pytest.mark.anyio
async def test_cache_key_is_case_insensitive(httpx_mock):
    _mock_site(httpx_mock)
    await inspect("https://example.com/")
    before = len(httpx_mock.get_requests())
    await inspect("https://EXAMPLE.com/")
    assert len(httpx_mock.get_requests()) == before


def _status_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://example.com/robots.txt")
    return httpx.HTTPStatusError("x", request=req, response=httpx.Response(code, request=req))


def test_robots_410_is_unrestricted():
    v, _ = compute_verdict(None, None, None, None, errors={"robots": _status_error(410)}, partial=False)
    assert v == "allowed"


def test_robots_503_is_forbidden():
    v, _ = compute_verdict(None, None, None, None, errors={"robots": _status_error(503)}, partial=True)
    assert v == "forbidden"


def test_cache_respects_short_max_age():
    import time
    cache = PolicyCache()
    cache.set("example.com", "robots", "v", cache_control="max-age=1")
    time.sleep(1.2)
    assert cache.get("example.com", "robots") is None


def test_cache_no_store_is_not_cached():
    cache = PolicyCache()
    cache.set("example.com", "robots", "v", cache_control="no-store")
    assert cache.get("example.com", "robots") is None


# --------------------------------------------------------------------------
# 2. Adapters
# --------------------------------------------------------------------------

@responses.activate
def test_requests_adapter_applies_identity_user_agent(ua_identity):
    responses.add(responses.GET, "https://example.com/", status=200)
    requests.get("https://example.com/", auth=WebBotAuthAdapter(ua_identity))
    assert responses.calls[0].request.headers["User-Agent"] == ua_identity.user_agent


def test_httpx_adapter_applies_identity_user_agent(ua_identity):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["ua"] = req.headers.get("user-agent")
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(handler), auth=WebBotAuth(ua_identity)) as c:
        c.get("https://example.com/")
    assert seen["ua"] == ua_identity.user_agent


def test_httpx_redirect_is_resigned_for_new_authority(identity):
    """Each redirect hop must carry exactly ONE fresh signature."""
    hops: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        hops.append(req)
        if req.url.host == "a.example.com":
            return httpx.Response(302, headers={"location": "https://b.example.com/x"})
        return httpx.Response(200)

    from wbauth.adapters import signed_client

    with signed_client(identity, transport=httpx.MockTransport(handler),
                       follow_redirects=True) as c:
        c.get("https://a.example.com/")
    assert len(hops) == 2
    for h in hops:
        assert h.headers["signature-input"].count("sig1=") == 1
        assert h.headers["signature"].count("sig1=") == 1
        assert h.headers["signature-agent"] == f'"{SIG_AGENT_URL}"'
    # Fresh signature per hop (different @authority → different signature).
    assert hops[0].headers["signature"] != hops[1].headers["signature"]


def test_httpx_post_digest_matches_body(identity):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["req"] = req
        return httpx.Response(200)

    body = b'{"hello":"world"}'
    with httpx.Client(transport=httpx.MockTransport(handler), auth=WebBotAuth(identity)) as c:
        c.post("https://example.com/", content=body)
    expected = base64.b64encode(hashlib.sha256(body).digest()).decode()
    assert seen["req"].headers["content-digest"] == f"sha-256=:{expected}:"
    assert '"content-digest"' in seen["req"].headers["signature-input"]


@responses.activate
def test_requests_streaming_body_is_buffered_and_digested(identity):
    responses.add(responses.POST, "https://example.com/", status=200)
    requests.post("https://example.com/", data=(c for c in [b"a", b"b"]),
                  auth=WebBotAuthAdapter(identity))
    sent = responses.calls[0].request
    expected = base64.b64encode(hashlib.sha256(b"ab").digest()).decode()
    assert sent.headers["Content-Digest"] == f"sha-256=:{expected}:"
    assert sent.body == b"ab"
    assert "Transfer-Encoding" not in sent.headers


# --------------------------------------------------------------------------
# 3. Signer input validation
# --------------------------------------------------------------------------

@pytest.mark.parametrize("secs", [0, -60])
def test_sign_rejects_non_positive_expiry(identity, secs):
    req = NormalizedRequest(method="GET", url="https://example.com/", headers={}, body=None)
    with pytest.raises(ValueError):
        sign(req, identity, expires_after_seconds=secs)


def test_sign_is_deterministic_with_fixed_inputs(identity):
    import datetime
    t = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    out = []
    for _ in range(2):
        req = NormalizedRequest(method="GET", url="https://example.com/", headers={}, body=None)
        out.append(sign(req, identity, created=t, nonce="n"))
    assert out[0] == out[1]


def test_identity_rejects_http_signature_agent():
    with pytest.raises(ValueError):
        Identity.from_test_key(signature_agent_url="http://insecure.example/")


@responses.activate
def test_requests_explicit_user_agent_is_preserved(ua_identity):
    responses.add(responses.GET, "https://example.com/", status=200)
    requests.get("https://example.com/", headers={"User-Agent": "Custom/2"},
                 auth=WebBotAuthAdapter(ua_identity))
    assert responses.calls[0].request.headers["User-Agent"] == "Custom/2"


@responses.activate
def test_signed_session_resigns_every_redirect_hop(identity):
    """requests does not re-run auth= on redirects; signed_session() does."""
    responses.add(responses.GET, "https://a.example.com/", status=302,
                  headers={"Location": "https://b.example.com/x"})
    responses.add(responses.GET, "https://b.example.com/x", status=200)
    signed_session(identity).get("https://a.example.com/")
    sigs = [c.request.headers["Signature"] for c in responses.calls]
    assert len(sigs) == 2 and sigs[0] != sigs[1]
    for c in responses.calls:
        assert c.request.headers["Signature-Input"].count("sig1=") == 1


def test_sign_replaces_stale_lowercase_headers(identity):
    req = NormalizedRequest(
        method="GET", url="https://example.com/",
        headers={"signature": "sig1=:old:", "signature-input": "sig1=()",
                 "signature-agent": '"https://old.example/"'},
        body=None,
    )
    sign(req, identity)
    assert [k.lower() for k in req.headers].count("signature") == 1
    assert req.headers["Signature"] != "sig1=:old:"


# --------------------------------------------------------------------------
# 4. Inspector: user-agent, size caps, redirects
# --------------------------------------------------------------------------

@pytest.mark.anyio
async def test_robots_evaluated_for_callers_user_agent(httpx_mock):
    _mock_site(httpx_mock, robots="User-agent: MyBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
    blocked = await inspect("https://example.com/a", user_agent="MyBot/1.0")
    other = await inspect("https://example.com/a", user_agent="OtherBot/1.0")
    assert blocked.verdict == "forbidden"
    assert other.verdict == "allowed"
    assert blocked.robots.user_agent_evaluated == "MyBot/1.0"
    assert httpx_mock.get_requests()[0].headers["user-agent"] == "MyBot/1.0"


@pytest.mark.anyio
async def test_oversized_robots_is_truncated_not_loaded_whole(httpx_mock):
    big = "User-agent: *\nDisallow: /private\n" + ("# pad\n" * 200_000)
    _mock_site(httpx_mock, robots=big)
    policy = await inspect("https://example.com/private")
    assert policy.verdict == "forbidden"
    assert len(policy.robots.raw) <= 500 * 1024


@pytest.mark.anyio
async def test_oversized_ai_txt_is_rejected(httpx_mock):
    httpx_mock.add_response(url="https://example.com/robots.txt", text="User-agent: *\nAllow: /\n")
    httpx_mock.add_response(url="https://example.com/ai.txt", text="x" * 1_100_000)
    httpx_mock.add_response(url="https://example.com/llms.txt", status_code=404)
    httpx_mock.add_response(
        url="https://example.com/.well-known/http-message-signatures-directory", status_code=404)
    policy = await inspect("https://example.com/")
    assert "ai_txt" in policy.errors
    assert policy.verdict == "restricted"  # partial → strict downgrade


@pytest.mark.anyio
async def test_shared_client_is_reused_and_not_closed(httpx_mock):
    _mock_site(httpx_mock)
    async with httpx.AsyncClient() as client:
        await inspect("https://example.com/", client=client)
        assert not client.is_closed


@pytest.mark.anyio
async def test_inspect_rejects_non_http_scheme():
    with pytest.raises(ValueError, match="http"):
        await inspect("ftp://example.com/")


# --------------------------------------------------------------------------
# 5. Playwright host scoping
# --------------------------------------------------------------------------

@pytest.mark.anyio
async def test_playwright_signs_only_allow_listed_hosts(identity):
    from unittest.mock import AsyncMock, MagicMock

    page = MagicMock()
    handler = {}

    async def fake_route(pattern, h):
        handler["h"] = h

    page.route = fake_route
    await attach_signing(page, identity, hosts=["*.example.com"])

    def req(url):
        r = MagicMock()
        r.method, r.url, r.post_data_buffer = "GET", url, None
        r.all_headers = AsyncMock(return_value={})
        return r

    ok = MagicMock(continue_=AsyncMock(), fallback=AsyncMock())
    await handler["h"](ok, req("https://www.example.com/"))
    assert ok.continue_.call_args.kwargs["headers"]["Signature"]

    skip = MagicMock(continue_=AsyncMock(), fallback=AsyncMock())
    await handler["h"](skip, req("https://cdn.tracker.net/x.js"))
    skip.fallback.assert_awaited_once()
    skip.continue_.assert_not_awaited()

    data = MagicMock(continue_=AsyncMock(), fallback=AsyncMock())
    await handler["h"](data, req("data:text/plain,hi"))
    data.fallback.assert_awaited_once()


def test_cli_inspect_passes_user_agent():
    from unittest.mock import patch

    from wbauth.cli import main

    with patch("wbauth.cli.inspect", side_effect=ValueError("stop")) as m:
        assert main(["inspect", "https://example.com/", "--user-agent", "MyBot/1.0"]) == 3
    assert m.call_args.kwargs["user_agent"] == "MyBot/1.0"
