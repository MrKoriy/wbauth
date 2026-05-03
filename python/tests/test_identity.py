"""Tests for wbauth.identity (IDENT-01, 02, 06, 07, 08).

Plan 01-03 RED phase: these tests will fail until identity.py is implemented.
"""
from __future__ import annotations

import os
import pickle
import re
import stat
import sys

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key as rsa_generate

# Canonical RFC 9421 Appendix B.1.4 thumbprint — verified live against
# https://http-message-signatures-example.research.cloudflare.com/.well-known/http-message-signatures-directory
RFC9421_TEST_KID = "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U"
SIG_AGENT_URL = "https://example.test/"


# ---------- IDENT-06: kid is RFC 7638 thumbprint ----------

def test_kid_matches_rfc9421_test_key():
    """IDENT-06: kid for the canonical RFC 9421 Appendix B.1.4 key MUST match the
    public thumbprint Cloudflare's debug verifier publishes."""
    from wbauth import Identity

    identity = Identity.from_test_key(SIG_AGENT_URL)
    assert identity.kid == RFC9421_TEST_KID


# ---------- IDENT-01: keygen + 0o600 + race-free creation ----------

def test_load_or_generate_creates_new_key(tmp_path):
    """IDENT-01: against a non-existent path, generate a new keypair on-disk at
    mode 0o600 (POSIX)."""
    from wbauth import Identity

    keyfile = tmp_path / "newdir" / "key.pem"
    assert not keyfile.exists()

    identity = Identity.load_or_generate(keyfile, signature_agent_url=SIG_AGENT_URL)
    assert keyfile.exists()
    assert identity.kid  # something got computed

    if sys.platform != "win32":
        mode = stat.S_IMODE(os.stat(keyfile).st_mode)
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


def test_generate_uses_o_excl_no_overwrite(tmp_path):
    """IDENT-01: _generate_keypair_to refuses to overwrite an existing file
    (O_EXCL race-free)."""
    from wbauth.identity import _generate_keypair_to

    keyfile = tmp_path / "key.pem"
    keyfile.write_bytes(b"placeholder")

    with pytest.raises(FileExistsError):
        _generate_keypair_to(keyfile)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes only")
def test_load_refuses_world_readable(tmp_path):
    """IDENT-01: loader raises PermissionError on a world-readable keyfile and
    surfaces a remediation message."""
    keyfile = tmp_path / "key.pem"
    pem = Ed25519PrivateKey.generate().private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    keyfile.write_bytes(pem)
    keyfile.chmod(0o644)

    from wbauth import Identity

    with pytest.raises(PermissionError) as exc:
        Identity.load_or_generate(keyfile, signature_agent_url=SIG_AGENT_URL)
    assert "0o644" in str(exc.value)
    assert "chmod 600" in str(exc.value)


# ---------- IDENT-02: long-lived Identity round-trips a kid ----------

def test_load_existing_returns_same_kid(tmp_path):
    """IDENT-02: generate, then load — same kid both times."""
    from wbauth import Identity

    keyfile = tmp_path / "key.pem"
    id1 = Identity.load_or_generate(keyfile, signature_agent_url=SIG_AGENT_URL)
    id2 = Identity.load_or_generate(keyfile, signature_agent_url=SIG_AGENT_URL)

    assert id1.kid == id2.kid


# ---------- Pitfall 1: signature_agent_url MUST be https:// ----------

def test_signature_agent_url_must_be_https(tmp_path):
    """Pitfall 1: http:// (or any non-https://) is rejected at construction time."""
    from wbauth import Identity

    keyfile = tmp_path / "key.pem"
    with pytest.raises(ValueError):
        Identity.load_or_generate(keyfile, signature_agent_url="http://example.test/")


# ---------- IDENT-06: JWKS export ----------

def test_export_jwks_one_key_when_no_retiring():
    """IDENT-06: with only an active key, JWKS has exactly one entry whose kid
    matches identity.kid."""
    from wbauth import Identity

    identity = Identity.from_test_key(SIG_AGENT_URL)
    jwks = identity.export_jwks()
    assert "keys" in jwks
    assert len(jwks["keys"]) == 1
    assert jwks["keys"][0]["kid"] == identity.kid
    # JWK shape sanity
    assert jwks["keys"][0]["kty"] == "OKP"
    assert jwks["keys"][0]["crv"] == "Ed25519"
    assert "x" in jwks["keys"][0]


# ---------- IDENT-07: rotate exposes active + retiring ----------

def test_export_jwks_two_keys_after_rotation(tmp_path):
    """IDENT-07: after rotate(), JWKS has 2 keys: new active first, old in retiring."""
    from wbauth import Identity

    keyfile1 = tmp_path / "key1.pem"
    keyfile2 = tmp_path / "key2.pem"

    id1 = Identity.load_or_generate(keyfile1, signature_agent_url=SIG_AGENT_URL)
    original_kid = id1.kid

    id2 = id1.rotate(keyfile2)
    jwks2 = id2.export_jwks()

    assert len(jwks2["keys"]) == 2
    # new active first
    assert jwks2["keys"][0]["kid"] == id2.kid
    assert jwks2["keys"][0]["kid"] != original_kid
    # old kid present as retiring
    assert jwks2["keys"][1]["kid"] == original_kid


def test_double_rotation_drops_oldest(tmp_path):
    """IDENT-07: a second rotation drops the original key entirely."""
    from wbauth import Identity

    kf1 = tmp_path / "k1.pem"
    kf2 = tmp_path / "k2.pem"
    kf3 = tmp_path / "k3.pem"

    id1 = Identity.load_or_generate(kf1, signature_agent_url=SIG_AGENT_URL)
    original_kid = id1.kid

    id2 = id1.rotate(kf2)
    id3 = id2.rotate(kf3)

    jwks3 = id3.export_jwks()
    kids = [k["kid"] for k in jwks3["keys"]]
    assert len(kids) == 2
    assert id3.kid in kids  # active
    assert id2.kid in kids  # retiring (was active in id2)
    assert original_kid not in kids  # dropped


# ---------- IDENT-08: REDACTED repr/str + pickle refusal ----------

def test_repr_returns_REDACTED():
    """IDENT-08: repr(identity) MUST contain literal 'REDACTED' and never key bytes."""
    from wbauth import Identity

    identity = Identity.from_test_key(SIG_AGENT_URL)
    r = repr(identity)
    assert "REDACTED" in r
    assert re.match(
        r"^<Identity REDACTED kid='[A-Za-z0-9_-]{43}' sig_agent='https://[^']+'>$",
        r,
    ), f"unexpected repr: {r!r}"


def test_str_returns_REDACTED():
    """IDENT-08: str(identity) == repr(identity) — both REDACTED."""
    from wbauth import Identity

    identity = Identity.from_test_key(SIG_AGENT_URL)
    assert str(identity) == repr(identity)
    assert "REDACTED" in str(identity)


def test_pickle_raises():
    """IDENT-08: pickle.dumps raises TypeError to refuse serialization."""
    from wbauth import Identity

    identity = Identity.from_test_key(SIG_AGENT_URL)
    with pytest.raises(TypeError):
        pickle.dumps(identity)


# ---------- from_test_key: no side effects ----------

def test_from_test_key_does_not_persist(tmp_path, monkeypatch):
    """IDENT-02: from_test_key MUST NOT write any file to disk."""
    from wbauth import Identity

    # Redirect HOME so any sneaky default-path write would land in tmp_path
    monkeypatch.setenv("HOME", str(tmp_path))
    Identity.from_test_key(SIG_AGENT_URL)

    # No .config/wbauth subdir created
    assert not (tmp_path / ".config" / "wbauth").exists()


# ---------- defensive: refuse non-Ed25519 PEMs ----------

def test_load_non_ed25519_raises_typeerror(tmp_path):
    """Defensive: an RSA PEM at the same path raises TypeError, not silent acceptance."""
    from wbauth import Identity

    keyfile = tmp_path / "rsa.pem"
    rsa_key = rsa_generate(public_exponent=65537, key_size=2048)
    pem = rsa_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    keyfile.write_bytes(pem)
    if sys.platform != "win32":
        keyfile.chmod(0o600)

    with pytest.raises(TypeError) as exc:
        Identity.load_or_generate(keyfile, signature_agent_url=SIG_AGENT_URL)
    assert "Ed25519" in str(exc.value)
