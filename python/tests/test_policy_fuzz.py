"""Property-based fuzzing of the policy parsers and verdict engine.

Invariants: parsers never raise on arbitrary text (other than the documented
RobotsParseError / FetchError), and the verdict is always one of three
literals with a non-empty reasons list.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from wbauth.policy.errors import FetchError, RobotsParseError
from wbauth.policy.parsers import (
    parse_ai_txt,
    parse_llms_txt,
    parse_robots,
    parse_signing_directory,
)
from wbauth.policy.verdict import compute_verdict, restriction_applies

LINE = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)), max_size=80
)
LINES = st.lists(
    st.one_of(
        LINE,
        st.sampled_from([
            "User-agent: *", "Disallow: /", "Allow: /a", "Crawl-delay: 5",
            "[restrictions]", "[permissions]", "- no training", "* /admin/",
            "# Title", "> no automated access", "## Docs", "- [a](https://x/y): z",
            "\ufeff", "Sitemap: https://x/s.xml",
        ]),
    ),
    max_size=40,
)
TEXT = LINES.map("\n".join)


@settings(max_examples=300, deadline=None)
@given(TEXT, st.sampled_from([None, "text/plain", "text/html"]), st.text(max_size=30))
def test_robots_never_crashes(text, ct, path):
    try:
        r = parse_robots(text, ct, "https://s.example/" + path, "FuzzBot/1.0")
    except RobotsParseError:
        return
    assert isinstance(r.can_fetch_url, bool)


@settings(max_examples=300, deadline=None)
@given(TEXT)
def test_ai_txt_and_llms_never_crash(text):
    ai = parse_ai_txt(text)
    assert all(isinstance(x, str) and x for x in ai.restrictions)
    llms = parse_llms_txt(text)
    assert llms.enforcement == "voluntary"


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=200), st.sampled_from([None, "application/json"]))
def test_signing_directory_never_crashes(text, ct):
    assert isinstance(parse_signing_directory(text, ct).present, bool)


@settings(max_examples=300, deadline=None)
@given(TEXT, st.text(max_size=40), st.booleans())
def test_verdict_total(text, path, partial):
    ai = parse_ai_txt(text)
    llms = parse_llms_txt(text)
    verdict, reasons = compute_verdict(None, ai, llms, None, {}, partial, target_path="/" + path)
    assert verdict in ("allowed", "restricted", "forbidden")
    assert reasons


@given(st.text(max_size=80), st.text(max_size=40))
def test_restriction_applies_total(rule, path):
    assert isinstance(restriction_applies(rule, "/" + path), bool)


def test_fetch_error_on_oversized_body():
    import pytest
    with pytest.raises(FetchError):
        parse_ai_txt("x" * 1_000_001)
