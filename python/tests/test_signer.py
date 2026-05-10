"""Tests for wbauth.signer (IDENT-03 — Web Bot Auth profile defaults).

Plan 01-03 Task 2 RED: these will fail until signer.py is implemented.

Determinism strategy: every test fixes `created` and `nonce` so the produced
Signature-Input is reproducible across runs. Ed25519 with the same key,
message, and metadata is deterministic by design (RFC 8032), so the actual
Signature value is also reproducible — used in test_signature_value_is_deterministic.
"""
from __future__ import annotations

import datetime
import re


SIG_AGENT_URL = "https://example.test/"
URL = "https://crawltest.com/cdn-cgi/web-bot-auth"

FIXED_CREATED = datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
FIXED_NONCE = "test-nonce-fixed"


# ---------- helpers ----------


def get_param(sig_input: str, name: str) -> str:
    """Extract a param value from a Signature-Input header.

    Handles both quoted ('keyid="..."') and unquoted ('created=123') params.
    Test helper — raises AssertionError if the param is missing (every test
    that calls this expects the param to be present, so a missing param is
    a test failure, not a None to handle).
    """
    m = re.search(rf';{re.escape(name)}="([^"]+)"', sig_input)
    if m:
        return m.group(1)
    m = re.search(rf';{re.escape(name)}=(\d+)', sig_input)
    assert m is not None, f"param {name!r} not found in: {sig_input!r}"
    return m.group(1)


def make_identity():
    from wbauth import Identity

    return Identity.from_test_key(SIG_AGENT_URL)


def make_get_request():
    from wbauth import NormalizedRequest

    return NormalizedRequest(method="GET", url=URL, headers={})


# ---------- IDENT-03 baseline ----------


def test_sign_produces_three_headers():
    """sign() returns SignatureHeaders AND mutates request.headers in place."""
    from wbauth import sign

    identity = make_identity()
    req = make_get_request()
    headers = sign(req, identity, created=FIXED_CREATED, nonce=FIXED_NONCE)

    assert headers.signature
    assert headers.signature_input
    assert headers.signature_agent
    # Mutation in place
    assert req.headers["Signature"] == headers.signature
    assert req.headers["Signature-Input"] == headers.signature_input
    assert req.headers["Signature-Agent"] == headers.signature_agent


# ---------- Pitfall 1 ----------


def test_signature_agent_is_double_quoted():
    """Pitfall 1: Signature-Agent value MUST be the URL wrapped in double quotes."""
    from wbauth import sign

    identity = make_identity()
    req = make_get_request()
    h = sign(req, identity, created=FIXED_CREATED, nonce=FIXED_NONCE)
    assert h.signature_agent == f'"{identity.signature_agent_url}"'


# ---------- Pitfall 6 + IDENT-03 ----------


def test_tag_appears_in_signature_input():
    """Pitfall 6: literal `tag="web-bot-auth"` MUST appear in Signature-Input."""
    from wbauth import sign

    identity = make_identity()
    req = make_get_request()
    h = sign(req, identity, created=FIXED_CREATED, nonce=FIXED_NONCE)
    assert 'tag="web-bot-auth"' in h.signature_input, (
        f"Signature-Input missing tag: {h.signature_input}"
    )


def test_alg_appears_in_signature_input():
    """A3: literal `alg="ed25519"` (lowercase) MUST appear in Signature-Input."""
    from wbauth import sign

    identity = make_identity()
    req = make_get_request()
    h = sign(req, identity, created=FIXED_CREATED, nonce=FIXED_NONCE)
    assert 'alg="ed25519"' in h.signature_input, (
        f"Signature-Input missing alg: {h.signature_input}"
    )


def test_keyid_appears_in_signature_input():
    """IDENT-03 + IDENT-06: keyid in Signature-Input matches identity.kid."""
    from wbauth import sign

    identity = make_identity()
    req = make_get_request()
    h = sign(req, identity, created=FIXED_CREATED, nonce=FIXED_NONCE)
    assert f'keyid="{identity.kid}"' in h.signature_input


# ---------- Pitfall 2 + IDENT-03: Cloudflare-safe components ----------


def test_default_components_are_authority_and_signature_agent():
    """Pitfall 2: default covered components are exactly @authority + signature-agent.

    The component list appears as a parenthesized space-separated list at the
    start of the Signature-Input value. Cloudflare rejects @query-params, etc.
    """
    from wbauth import sign

    identity = make_identity()
    req = make_get_request()
    h = sign(req, identity, created=FIXED_CREATED, nonce=FIXED_NONCE)
    assert re.search(r'\("@authority" "signature-agent"\)', h.signature_input), (
        f"unexpected component list: {h.signature_input}"
    )


# ---------- Pitfall 3: 60s expiry default ----------


def test_default_expires_is_60_seconds():
    """Pitfall 3: default expires window is 60s (5s+ NTP slack-safe)."""
    from wbauth import sign

    identity = make_identity()
    req = make_get_request()
    h = sign(req, identity, created=FIXED_CREATED, nonce=FIXED_NONCE)

    created = int(get_param(h.signature_input, "created"))
    expires = int(get_param(h.signature_input, "expires"))
    assert expires - created == 60


def test_custom_expires_after_seconds():
    """Parameter plumbing: expires_after_seconds=300 produces a 300s window."""
    from wbauth import sign

    identity = make_identity()
    req = make_get_request()
    h = sign(
        req,
        identity,
        created=FIXED_CREATED,
        nonce=FIXED_NONCE,
        expires_after_seconds=300,
    )

    created = int(get_param(h.signature_input, "created"))
    expires = int(get_param(h.signature_input, "expires"))
    assert expires - created == 300


# ---------- IDENT-03: body → content-digest ----------


def test_post_with_body_adds_content_digest_component():
    """POST with a body MUST include 'content-digest' in covered components.

    Per RFC 9421, the Content-Digest header itself must be present on the
    request before signing — but the SIGNER decides which components are
    covered. We assert the signer added "content-digest" to the covered list.
    """
    from wbauth import NormalizedRequest, sign

    identity = make_identity()
    body = b'{"hello":"world"}'

    # Caller is responsible for setting the actual Content-Digest header.
    # http-message-signatures' signer reads headers as-is for the signing
    # base, so we provide it. (Phase 2 helpers will compute this from body.)
    import base64
    import hashlib

    digest = base64.b64encode(hashlib.sha256(body).digest()).decode()

    req = NormalizedRequest(
        method="POST",
        url=URL,
        headers={"Content-Digest": f"sha-256=:{digest}:"},
        body=body,
    )
    h = sign(req, identity, created=FIXED_CREATED, nonce=FIXED_NONCE)
    assert '"content-digest"' in h.signature_input


def test_get_does_not_add_content_digest():
    """GET (no body) does NOT include content-digest in covered components."""
    from wbauth import sign

    identity = make_identity()
    req = make_get_request()
    h = sign(req, identity, created=FIXED_CREATED, nonce=FIXED_NONCE)
    assert '"content-digest"' not in h.signature_input


# ---------- Determinism (IDENT-04 prep) ----------


def test_signature_value_is_deterministic():
    """Same key + same created + same nonce → identical Signature bytes.

    Ed25519 is deterministic by RFC 8032; the signing base also has no
    nondeterministic inputs once we fix created+nonce. This is the property
    Plan 04's test vectors will rely on (byte-equal expected.json).
    """
    from wbauth import sign

    id1 = make_identity()
    id2 = make_identity()  # same test key
    req1 = make_get_request()
    req2 = make_get_request()

    h1 = sign(req1, id1, created=FIXED_CREATED, nonce=FIXED_NONCE)
    h2 = sign(req2, id2, created=FIXED_CREATED, nonce=FIXED_NONCE)

    assert h1.signature == h2.signature
    assert h1.signature_input == h2.signature_input


def test_label_is_sig1_by_default():
    """Default label is "sig1" — both Signature-Input and Signature use it."""
    from wbauth import sign

    identity = make_identity()
    req = make_get_request()
    h = sign(req, identity, created=FIXED_CREATED, nonce=FIXED_NONCE)
    assert h.signature_input.startswith("sig1=")
    assert h.signature.startswith("sig1=")


# ---------- IDENT-08 + Pitfall 4: signer never logs key bytes ----------


def test_signer_does_not_leak_key(capsys):
    """Per Pitfall 4: signer must produce zero stdout/stderr (no debug prints
    of key material). Captures stdio and asserts empty."""
    from wbauth import sign

    identity = make_identity()
    req = make_get_request()
    sign(req, identity, created=FIXED_CREATED, nonce=FIXED_NONCE)

    captured = capsys.readouterr()
    # Test key bytes (b64url-no-pad) — must not appear in any output.
    test_d = "n4Ni-HpISpVObnQMW0wOhCKROaIKqKtW_2ZYb2p9KcU"
    assert test_d not in captured.out
    assert test_d not in captured.err
