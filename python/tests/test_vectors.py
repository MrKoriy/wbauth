"""Cross-language byte-equality test vectors (IDENT-04).

For every directory under ``spec/test-vectors/<name>/`` that has both
``input.json`` and ``expected.json``, run ``wbauth.sign()`` with the input
and assert byte-equality against the expected ``Signature-Input``,
``Signature``, and ``Signature-Agent`` strings.

Ed25519 is deterministic (no per-signature nonce in the cryptography itself —
the only nonce is the RFC 9421 ``nonce=`` parameter which we fix in
``input.json``), so given the same key + same created + same nonce + same
components, the produced signature is identical across runs and across
language implementations. This is the cross-language oracle that catches
spec drift in either runtime.
"""
from __future__ import annotations

import base64
import datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from wbauth import Identity, KeyPair, NormalizedRequest, sign
from wbauth.identity import _compute_kid


def _b64url_decode(s: str) -> bytes:
    """Pad b64url back to a multiple of 4 before decoding (RFC 7515 §2)."""
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _identity_from_input(inp: dict) -> Identity:
    priv = Ed25519PrivateKey.from_private_bytes(
        _b64url_decode(inp["identity"]["private_key_jwk"]["d"])
    )
    active = KeyPair(priv, _compute_kid(priv.public_key()))
    retiring = None
    if rj := inp["identity"].get("retiring_key_jwk"):
        rpriv = Ed25519PrivateKey.from_private_bytes(_b64url_decode(rj["d"]))
        retiring = KeyPair(rpriv, _compute_kid(rpriv.public_key()))
    return Identity(active, inp["identity"]["signature_agent_url"], retiring=retiring)


def _sign_from_input(inp: dict):
    ident = _identity_from_input(inp)
    body_b64 = inp["request"].get("body")
    body = base64.b64decode(body_b64) if body_b64 else None
    req = NormalizedRequest(
        method=inp["request"]["method"],
        url=inp["request"]["url"],
        headers=dict(inp["request"]["headers"]),
        body=body,
    )
    created = datetime.datetime.fromtimestamp(
        inp["signing_params"]["created"], tz=datetime.timezone.utc
    )
    sig = sign(
        req, ident,
        created=created,
        expires_after_seconds=inp["signing_params"]["expires_after_seconds"],
        nonce=inp["signing_params"]["nonce"],
        label=inp["signing_params"]["label"],
    )
    return ident, sig


def test_vector_byte_equal_signature_input(vector):
    _, sig = _sign_from_input(vector["input"])
    assert sig.signature_input == vector["expected"]["signature_input_value"], (
        f"\n  produced: {sig.signature_input}"
        f"\n  expected: {vector['expected']['signature_input_value']}"
    )


def test_vector_byte_equal_signature(vector):
    _, sig = _sign_from_input(vector["input"])
    assert sig.signature == vector["expected"]["signature_value"], (
        f"\n  produced: {sig.signature}"
        f"\n  expected: {vector['expected']['signature_value']}"
    )


def test_vector_byte_equal_signature_agent(vector):
    _, sig = _sign_from_input(vector["input"])
    assert sig.signature_agent == vector["expected"]["signature_agent_value"]


def test_vector_kid_matches(vector):
    ident, _ = _sign_from_input(vector["input"])
    assert ident.kid == vector["expected"]["kid"]


def test_vector_jwks_full_for_multi_key(vector):
    if "jwks_full" not in vector["expected"]:
        return  # vectors without retiring key skip this check
    ident, _ = _sign_from_input(vector["input"])
    assert ident.export_jwks() == vector["expected"]["jwks_full"]
