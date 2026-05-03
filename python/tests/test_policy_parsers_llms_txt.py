"""Tests for wbauth.policy.parsers.llms_txt (llmstxt.org grammar)."""
from __future__ import annotations

import pathlib

from wbauth.policy.parsers import parse_llms_txt

FIX = pathlib.Path(__file__).parent / "fixtures" / "policy" / "llms_txt"


def test_llms_txt_minimal_parses_title_description_one_section():
    r = parse_llms_txt((FIX / "minimal.txt").read_text())
    assert r.title == "Example Project"
    assert r.description == "A demo of llms.txt for our docs"
    assert len(r.sections) == 1
    section = r.sections[0]
    assert section.name == "Docs"
    assert len(section.links) == 2
    assert section.links[0].title == "Quickstart"
    assert section.links[0].url == "https://example.com/quickstart"
    assert section.links[0].notes == "get started in 5 minutes"
    assert section.links[1].title == "API reference"
    assert section.links[1].notes == ""


def test_llms_txt_full_parses_three_sections():
    r = parse_llms_txt((FIX / "full.txt").read_text())
    assert r.title == "Big Docs Site"
    assert len(r.sections) == 3
    names = [s.name for s in r.sections]
    assert names == ["Getting Started", "Reference", "Optional"]


def test_llms_txt_empty_yields_empty_struct():
    r = parse_llms_txt((FIX / "empty.txt").read_text())
    assert r.title == ""
    assert r.description == ""
    assert r.sections == []


def test_llms_txt_enforcement_is_voluntary_literal():
    """D-21 anchor: LlmsTxtResult.enforcement is the literal 'voluntary'."""
    r = parse_llms_txt((FIX / "minimal.txt").read_text())
    assert r.enforcement == "voluntary"
    r_empty = parse_llms_txt("")
    assert r_empty.enforcement == "voluntary"


def test_llms_txt_raw_preserved():
    text = (FIX / "minimal.txt").read_text()
    r = parse_llms_txt(text)
    assert r.raw == text
