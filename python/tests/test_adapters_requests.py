"""Tests for the requests WebBotAuthAdapter (ADAPT-02).

Uses the `responses` library to capture outgoing requests without live network.
"""
from __future__ import annotations

import re

import requests
import responses

from wbauth import Identity
from wbauth.adapters import WebBotAuthAdapter


SIG_AGENT_URL = "https://example.invalid/test/"


@responses.activate
def test_get_attaches_three_signed_headers():
    """Smoke: every Sig* header is present and non-empty."""
    responses.add(responses.GET, "https://example.com/", json={}, status=200)
    identity = Identity.from_test_key(signature_agent_url=SIG_AGENT_URL)
    requests.get("https://example.com/", auth=WebBotAuthAdapter(identity))
    sent = responses.calls[0].request
    assert sent.headers["Signature"]
    assert sent.headers["Signature-Input"]
    assert sent.headers["Signature-Agent"]


@responses.activate
def test_consecutive_requests_have_different_nonces():
    """Statelessness invariant (D-15): each request gets a fresh nonce."""
    responses.add(responses.GET, "https://example.com/a", json={}, status=200)
    responses.add(responses.GET, "https://example.com/b", json={}, status=200)
    identity = Identity.from_test_key(signature_agent_url=SIG_AGENT_URL)
    adapter = WebBotAuthAdapter(identity)
    requests.get("https://example.com/a", auth=adapter)
    requests.get("https://example.com/b", auth=adapter)
    nonce_pat = re.compile(r'nonce="([^"]+)"')
    n1 = nonce_pat.search(responses.calls[0].request.headers["Signature-Input"]).group(1)
    n2 = nonce_pat.search(responses.calls[1].request.headers["Signature-Input"]).group(1)
    assert n1 != n2, "consecutive requests must use distinct nonces (no caching)"


@responses.activate
def test_ua_injection_when_absent():
    """Open question #4 (positive): identity.user_agent → request UA."""
    responses.add(responses.GET, "https://example.com/", json={}, status=200)
    identity = Identity(
        Identity.from_test_key(SIG_AGENT_URL)._active,
        signature_agent_url=SIG_AGENT_URL,
        user_agent="my-bot/1.0",
    )
    # Use a Session whose default UA we can override (otherwise requests' default UA wins).
    session = requests.Session()
    # Wipe the default UA so absence is meaningful for our test.
    session.headers.pop("User-Agent", None)
    session.get("https://example.com/", auth=WebBotAuthAdapter(identity))
    assert responses.calls[0].request.headers["User-Agent"] == "my-bot/1.0"


@responses.activate
def test_ua_preserved_when_caller_set_one():
    """Open question #4 (negative): caller's UA wins."""
    responses.add(responses.GET, "https://example.com/", json={}, status=200)
    identity = Identity(
        Identity.from_test_key(SIG_AGENT_URL)._active,
        signature_agent_url=SIG_AGENT_URL,
        user_agent="my-bot/1.0",
    )
    requests.get(
        "https://example.com/",
        auth=WebBotAuthAdapter(identity),
        headers={"User-Agent": "caller-set/2.0"},
    )
    assert responses.calls[0].request.headers["User-Agent"] == "caller-set/2.0"


@responses.activate
def test_post_with_body_signs_correctly():
    """POST + body: prepared_request.body is bytes by signing time."""
    responses.add(responses.POST, "https://example.com/api", json={}, status=200)
    identity = Identity.from_test_key(signature_agent_url=SIG_AGENT_URL)
    requests.post(
        "https://example.com/api",
        data=b'{"hello":"world"}',
        auth=WebBotAuthAdapter(identity),
    )
    sent = responses.calls[0].request
    assert "Signature" in sent.headers
    assert "Signature-Input" in sent.headers
    assert "Signature-Agent" in sent.headers
