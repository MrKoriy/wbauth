"""Adapter conformance against spec/test-vectors/ (ADAPT-06, D-29).

Proves byte-equality with the Phase-1 signer baseline by routing through the
adapter code path AND asserting Signature/Signature-Input/Signature-Agent
header values match `expected.json` exactly.

Key seam: we monkeypatch the `sign` symbol the adapter imports so we can fix
`created`/`nonce`/`label`/`expires_after_seconds` from the vector. The
production code path uses signer defaults — this test only freezes them
for vector replay (per the strategy noted in the plan).
"""
from __future__ import annotations

import datetime
import json
import pathlib
from base64 import urlsafe_b64decode

import httpx
import pytest
import requests
import responses
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from wbauth import Identity, KeyPair
from wbauth.identity import _compute_kid
from wbauth.adapters import WebBotAuth, WebBotAuthAdapter
from wbauth import signer as _signer_module
from wbauth.adapters import httpx_auth as _httpx_auth_module
from wbauth.adapters import requests_adapter as _requests_adapter_module


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
VECTORS_DIR = REPO_ROOT / "spec" / "test-vectors"


def _identity_from_vector(vector_dir: pathlib.Path) -> Identity:
    data = json.loads((vector_dir / "input.json").read_text())
    jwk = data["identity"]["private_key_jwk"]
    # Pad the base64url 'd' field for decoding.
    d_b64 = jwk["d"]
    padded = d_b64 + "=" * (-len(d_b64) % 4)
    d_bytes = urlsafe_b64decode(padded)
    priv = Ed25519PrivateKey.from_private_bytes(d_bytes)
    kp = KeyPair(priv, _compute_kid(priv.public_key()))
    return Identity(kp, signature_agent_url=data["identity"]["signature_agent_url"])


def _make_vector_freezing_sign(real_sign, vector: dict):
    sp = vector["signing_params"]
    created_dt = datetime.datetime.fromtimestamp(
        sp["created"], tz=datetime.timezone.utc
    )

    def _patched(req, ident, **_ignored):
        return real_sign(
            req,
            ident,
            created=created_dt,
            nonce=sp["nonce"],
            label=sp["label"],
            expires_after_seconds=sp["expires_after_seconds"],
        )

    return _patched


@pytest.fixture
def vector_01() -> dict:
    vec = VECTORS_DIR / "01-basic-get"
    return {
        "dir": vec,
        "input": json.loads((vec / "input.json").read_text()),
        "expected": json.loads((vec / "expected.json").read_text()),
    }


def test_httpx_matches_vector_01(vector_01, monkeypatch):
    """httpx adapter produces byte-equal headers vs spec/test-vectors/01-basic-get/expected.json."""
    identity = _identity_from_vector(vector_01["dir"])
    real_sign = _signer_module.sign
    patched = _make_vector_freezing_sign(real_sign, vector_01["input"])
    # Patch the symbol the adapter imported (it did `from wbauth import sign`,
    # which is the same object as wbauth.signer.sign at import time, and now
    # lives on the adapter module's namespace as `sign`).
    monkeypatch.setattr(_httpx_auth_module, "sign", patched)

    captured: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return httpx.Response(200)

    r = vector_01["input"]["request"]
    client = httpx.Client(
        auth=WebBotAuth(identity),
        transport=httpx.MockTransport(handler),
    )
    client.request(
        r["method"],
        r["url"],
        headers=r.get("headers") or {},
        content=r.get("body"),
    )
    sent = captured[0]
    expected = vector_01["expected"]
    assert sent.headers["Signature"] == expected["signature_value"], (
        f"signature mismatch:\n  got: {sent.headers['Signature']!r}\n"
        f"  exp: {expected['signature_value']!r}"
    )
    assert sent.headers["Signature-Input"] == expected["signature_input_value"]
    assert sent.headers["Signature-Agent"] == expected["signature_agent_value"]


@responses.activate
def test_requests_matches_vector_01(vector_01, monkeypatch):
    """requests adapter produces byte-equal headers vs spec/test-vectors/01-basic-get/expected.json."""
    identity = _identity_from_vector(vector_01["dir"])
    real_sign = _signer_module.sign
    patched = _make_vector_freezing_sign(real_sign, vector_01["input"])
    monkeypatch.setattr(_requests_adapter_module, "sign", patched)

    r = vector_01["input"]["request"]
    responses.add(getattr(responses, r["method"]), r["url"], json={}, status=200)
    requests.request(
        r["method"],
        r["url"],
        headers=r.get("headers") or {},
        data=r.get("body"),
        auth=WebBotAuthAdapter(identity),
    )
    sent = responses.calls[0].request
    expected = vector_01["expected"]
    assert sent.headers["Signature"] == expected["signature_value"]
    assert sent.headers["Signature-Input"] == expected["signature_input_value"]
    assert sent.headers["Signature-Agent"] == expected["signature_agent_value"]
