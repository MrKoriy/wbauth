"""Tests for wbauth.policy.parsers.ai_txt (ai.txt v1.1.1)."""
from __future__ import annotations

import pathlib

from wbauth.policy.parsers import parse_ai_txt

FIX = pathlib.Path(__file__).parent / "fixtures" / "policy" / "ai_txt"


def test_ai_txt_minimal_parses_identity_permissions_restrictions():
    r = parse_ai_txt((FIX / "minimal.txt").read_text())
    assert r.identity == {"name": "Example Inc", "url": "https://example.com"}
    assert "Summarise publicly available content" in r.permissions
    assert "Cite with attribution" in r.permissions
    assert "Do not generate fake quotes" in r.restrictions
    assert "Do not impersonate the brand" in r.restrictions


def test_ai_txt_with_restrictions_yields_three_restrictions():
    r = parse_ai_txt((FIX / "with_restrictions.txt").read_text())
    assert len(r.restrictions) == 3
    assert r.restrictions[0] == "No AI training without explicit permission"
    assert r.identity == {"name": "Restrictive Site"}
    assert r.permissions == []


def test_ai_txt_malformed_yields_all_empty():
    """Comments only: no sections → all fields empty (no signal)."""
    r = parse_ai_txt((FIX / "malformed.txt").read_text())
    assert r.identity == {}
    assert r.permissions == []
    assert r.restrictions == []
    assert r.attribution == []
    assert r.contact == {}


def test_ai_txt_content_types_returns_empty_dict_per_v1():
    """Assumption A6: v1 parser intentionally returns content_types={}."""
    r = parse_ai_txt((FIX / "minimal.txt").read_text())
    assert r.content_types == {}


def test_ai_txt_raw_preserved():
    text = (FIX / "minimal.txt").read_text()
    r = parse_ai_txt(text)
    assert r.raw == text
