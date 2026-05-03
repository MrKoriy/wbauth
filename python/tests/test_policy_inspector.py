"""Tests for wbauth.policy.inspector.inspect.

Uses pytest-httpx to mock HTTP traffic to the four well-known endpoints.
No live HTTP traffic — fully deterministic in CI.

Anchors:
  - test_html_200_robots_yields_forbidden — Pitfall 1 end-to-end
  - test_only_user_supplied_host_is_fetched — POLICY-08
  - test_cache_hit_avoids_second_fetch — D-22 cache-singleton behavior
"""
from __future__ import annotations

import pathlib

import httpx
import pytest

from wbauth.policy import inspect
from wbauth.policy.inspector import _reset_cache_for_tests

FIX = pathlib.Path(__file__).parent / "fixtures" / "policy"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _clear_cache():
    _reset_cache_for_tests()
    yield
    _reset_cache_for_tests()


pytestmark = pytest.mark.anyio


def _add_404_for(httpx_mock, url: str) -> None:
    httpx_mock.add_response(url=url, status_code=404)


async def test_happy_path_all_four_endpoints(httpx_mock):
    httpx_mock.add_response(
        url="https://example.com/robots.txt",
        text=(FIX / "robots/allow.txt").read_text(),
        headers={"content-type": "text/plain"},
    )
    httpx_mock.add_response(
        url="https://example.com/ai.txt",
        text=(FIX / "ai_txt/minimal.txt").read_text(),
        headers={"content-type": "text/plain"},
    )
    httpx_mock.add_response(
        url="https://example.com/llms.txt",
        text=(FIX / "llms_txt/minimal.txt").read_text(),
        headers={"content-type": "text/plain"},
    )
    httpx_mock.add_response(
        url="https://example.com/.well-known/http-message-signatures-directory",
        text=(FIX / "signing_directory/present.json").read_text(),
        headers={"content-type": "application/http-message-signatures-directory+json"},
    )
    policy = await inspect("https://example.com/")
    assert policy.robots is not None
    assert policy.ai_txt is not None
    assert policy.llms_txt is not None
    assert policy.signing_directory is not None
    assert policy.partial is False
    assert policy.errors == {}
    # ai_txt minimal fixture has restrictions → restricted (NOT allowed) per D-21
    assert policy.verdict == "restricted"


async def test_happy_path_no_restrictions_yields_allowed(httpx_mock):
    httpx_mock.add_response(
        url="https://example.com/robots.txt",
        text="User-agent: *\nAllow: /",
        headers={"content-type": "text/plain"},
    )
    _add_404_for(httpx_mock, "https://example.com/ai.txt")
    _add_404_for(httpx_mock, "https://example.com/llms.txt")
    _add_404_for(
        httpx_mock,
        "https://example.com/.well-known/http-message-signatures-directory",
    )
    policy = await inspect("https://example.com/")
    assert policy.verdict == "allowed"
    assert policy.partial is False  # 404s are NOT errors per RFC 9309


async def test_html_200_robots_yields_forbidden(httpx_mock):
    """Pitfall 1 anchor end-to-end."""
    httpx_mock.add_response(
        url="https://example.com/robots.txt",
        text=(FIX / "robots/html_200.txt").read_text(),
        headers={"content-type": "text/html"},
    )
    _add_404_for(httpx_mock, "https://example.com/ai.txt")
    _add_404_for(httpx_mock, "https://example.com/llms.txt")
    _add_404_for(
        httpx_mock,
        "https://example.com/.well-known/http-message-signatures-directory",
    )
    policy = await inspect("https://example.com/")
    assert policy.verdict == "forbidden"
    assert any("unparseable" in r.lower() for r in policy.reasons)
    assert "robots" in policy.errors


async def test_only_user_supplied_host_is_fetched(httpx_mock):
    """POLICY-08 anchor: every fetch targets the user-supplied origin."""
    httpx_mock.add_response(
        url="https://example.com/robots.txt",
        text="User-agent: *\nAllow: /",
        headers={"content-type": "text/plain"},
    )
    _add_404_for(httpx_mock, "https://example.com/ai.txt")
    _add_404_for(httpx_mock, "https://example.com/llms.txt")
    _add_404_for(
        httpx_mock,
        "https://example.com/.well-known/http-message-signatures-directory",
    )
    await inspect("https://example.com/")
    hosts = {req.url.host for req in httpx_mock.get_requests()}
    assert hosts == {"example.com"}, f"non-user-host fetched: {hosts}"


async def test_cache_hit_avoids_second_fetch(httpx_mock):
    """D-22: parsed robots is cached; second inspect() call doesn't re-fetch it."""
    httpx_mock.add_response(
        url="https://example.com/robots.txt",
        text="User-agent: *\nAllow: /",
        headers={"content-type": "text/plain"},
    )
    # 404 endpoints — errors are NOT cached, so they may be re-fetched.
    # Register multiple times to allow the second inspect() call to re-hit them.
    for _ in range(2):
        _add_404_for(httpx_mock, "https://example.com/ai.txt")
        _add_404_for(httpx_mock, "https://example.com/llms.txt")
        _add_404_for(
            httpx_mock,
            "https://example.com/.well-known/http-message-signatures-directory",
        )

    await inspect("https://example.com/")
    await inspect("https://example.com/")
    robots_calls = sum(
        1 for r in httpx_mock.get_requests() if r.url.path == "/robots.txt"
    )
    assert robots_calls == 1, f"robots.txt re-fetched: {robots_calls} calls"


async def test_ai_txt_timeout_yields_partial(httpx_mock):
    """POLICY-02: per-endpoint timeout isolates failure to that endpoint."""
    httpx_mock.add_response(
        url="https://example.com/robots.txt",
        text="User-agent: *\nAllow: /",
        headers={"content-type": "text/plain"},
    )
    httpx_mock.add_exception(
        httpx.ReadTimeout("simulated"), url="https://example.com/ai.txt"
    )
    _add_404_for(httpx_mock, "https://example.com/llms.txt")
    _add_404_for(
        httpx_mock,
        "https://example.com/.well-known/http-message-signatures-directory",
    )
    policy = await inspect("https://example.com/")
    assert policy.partial is True
    assert "ai_txt" in policy.errors
    assert policy.robots is not None
    # Tentative-allowed downgraded to restricted by partial
    assert policy.verdict == "restricted"


async def test_inspect_raises_on_url_without_host(httpx_mock):
    with pytest.raises(ValueError, match="no host"):
        await inspect("not-a-url")


async def test_user_agent_is_wbauth_0_1(httpx_mock):
    """D-20: every fetch uses User-Agent: wbauth/0.1."""
    httpx_mock.add_response(
        url="https://example.com/robots.txt",
        text="User-agent: *\nAllow: /",
        headers={"content-type": "text/plain"},
    )
    _add_404_for(httpx_mock, "https://example.com/ai.txt")
    _add_404_for(httpx_mock, "https://example.com/llms.txt")
    _add_404_for(
        httpx_mock,
        "https://example.com/.well-known/http-message-signatures-directory",
    )
    await inspect("https://example.com/")
    for req in httpx_mock.get_requests():
        assert req.headers.get("user-agent") == "wbauth/0.1"


async def test_public_surface_re_exports():
    """Package root re-exports inspect + SitePolicy + the four Result types."""
    from wbauth import (
        AiTxtResult,
        LlmsTxtResult,
        RobotsResult,
        SigningDirectoryResult,
        SitePolicy,
        inspect as inspect_top,
    )
    assert inspect_top is inspect
    assert SitePolicy.__name__ == "SitePolicy"
    assert RobotsResult.__name__ == "RobotsResult"
    assert AiTxtResult.__name__ == "AiTxtResult"
    assert LlmsTxtResult.__name__ == "LlmsTxtResult"
    assert SigningDirectoryResult.__name__ == "SigningDirectoryResult"
