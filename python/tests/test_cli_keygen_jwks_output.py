"""Tests for `wbauth keygen --jwks-output PATH` extension (D-51).

Verifies that the new `--jwks-output` flag writes a public-only JWKS
document alongside the existing PEM private key. Backward compatibility:
without the flag, no JWKS file is written (Phase 1 IDENT-01 behavior).

Security guard (T-03-19): the written JWKS must NEVER contain the `d`
(private scalar) field. `Identity.export_jwks` builds via
`KeyPair.public_jwk()` which only emits {kty, crv, kid, x} — but we
assert it directly here as a regression guard against future changes.
"""
from __future__ import annotations

import json

import pytest

from wbauth.cli import _build_parser, _dispatch_keygen
from wbauth.identity import Identity


def test_keygen_jwks_output_writes_valid_jwks(tmp_path):
    """--jwks-output writes a valid JWKS with the right shape + kid."""
    keypath = tmp_path / "k.pem"
    jwks_path = tmp_path / "k.jwks.json"
    parser = _build_parser()
    args = parser.parse_args([
        "keygen",
        "--output", str(keypath),
        "--jwks-output", str(jwks_path),
        "--signature-agent-url", "https://wbauth.silov801.workers.dev/.well-known/...",
    ])
    rc = _dispatch_keygen(args)
    assert rc == 0
    # Both files exist
    assert keypath.exists()
    assert jwks_path.exists()
    # JWKS file is valid JSON with the right shape
    jwks = json.loads(jwks_path.read_text())
    assert "keys" in jwks
    assert len(jwks["keys"]) == 1
    k0 = jwks["keys"][0]
    assert k0["kty"] == "OKP"
    assert k0["crv"] == "Ed25519"
    assert "kid" in k0
    assert "x" in k0
    # T-03-19 GUARD: no private scalar in the public JWKS
    assert "d" not in k0, (
        "JWKS file MUST NOT contain 'd' (private key scalar). "
        "Identity.export_jwks() leaked private material!"
    )
    # kid matches what Identity computes
    identity = Identity.load_or_generate(keypath, signature_agent_url="https://example.com")
    assert k0["kid"] == identity.kid


def test_keygen_without_jwks_output_does_not_write_jwks(tmp_path):
    """Backward compat — Phase 1 IDENT-01 behavior preserved when --jwks-output omitted."""
    keypath = tmp_path / "k.pem"
    parser = _build_parser()
    args = parser.parse_args([
        "keygen",
        "--output", str(keypath),
        "--signature-agent-url", "https://example.com",
    ])
    rc = _dispatch_keygen(args)
    assert rc == 0
    assert keypath.exists()
    # No jwks file should have been created in tmp_path
    assert not (tmp_path / "k.jwks.json").exists()


def test_keygen_jwks_output_content_is_indented_json(tmp_path):
    """Pretty-printed JSON (indent=2) so users can `cat` the JWKS file."""
    keypath = tmp_path / "k.pem"
    jwks_path = tmp_path / "k.jwks.json"
    parser = _build_parser()
    args = parser.parse_args([
        "keygen",
        "--output", str(keypath),
        "--jwks-output", str(jwks_path),
        "--signature-agent-url", "https://example.com",
    ])
    rc = _dispatch_keygen(args)
    assert rc == 0
    text = jwks_path.read_text()
    # Indented JSON has newlines; compact JSON would be a single line.
    assert "\n" in text, "JWKS output should be pretty-printed (indent=2)"
