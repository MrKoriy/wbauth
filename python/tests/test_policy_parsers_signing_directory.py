"""Tests for wbauth.policy.parsers.signing_directory.

Lightweight parser: surfaces presence + key count + content-type-correctness.
No JWK validation (verifier's job, not inspector's).
"""
from __future__ import annotations

import pathlib

from wbauth.policy.parsers import parse_signing_directory

FIX = pathlib.Path(__file__).parent / "fixtures" / "policy" / "signing_directory"

SPEC_CT = "application/http-message-signatures-directory+json"


def test_signing_directory_present_with_correct_content_type():
    text = (FIX / "present.json").read_text()
    r = parse_signing_directory(text, content_type=SPEC_CT)
    assert r.present is True
    assert len(r.keys) == 1
    assert r.keys[0]["kid"] == "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U"
    assert r.content_type_correct is True
    assert r.raw == text


def test_signing_directory_present_with_wrong_content_type():
    text = (FIX / "present.json").read_text()
    r = parse_signing_directory(text, content_type="application/json")
    assert r.present is True
    assert r.content_type_correct is False


def test_signing_directory_malformed_yields_absent_no_raise():
    """Malformed JSON: parser returns present=False, does NOT raise."""
    text = (FIX / "malformed.json").read_text()
    r = parse_signing_directory(text, content_type=SPEC_CT)
    assert r.present is False
    assert r.keys == []
    assert r.content_type_correct is False  # spec says: malformed → not correct
    assert r.raw == text


def test_signing_directory_no_keys_field_yields_absent():
    """Valid JSON but no `keys` array → present=False."""
    r = parse_signing_directory('{"foo": "bar"}', content_type=SPEC_CT)
    assert r.present is False
    assert r.keys == []
    assert r.content_type_correct is True


def test_signing_directory_empty_keys_yields_absent():
    """`{"keys": []}` → present=False (no keys advertised)."""
    r = parse_signing_directory('{"keys": []}', content_type=SPEC_CT)
    assert r.present is False
    assert r.keys == []


def test_signing_directory_none_content_type_handled():
    text = (FIX / "present.json").read_text()
    r = parse_signing_directory(text, content_type=None)
    assert r.present is True
    assert r.content_type_correct is False
