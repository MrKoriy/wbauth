"""Tests for wbauth.policy.parsers.robots.

Covers RFC 9309 conformance via Protego, plus the Pitfall 1 HTML-200
detection shim (D-19): an HTML body returned for /robots.txt MUST raise
RobotsParseError so the verdict engine maps it to 'forbidden' instead of
silently allowing.
"""
from __future__ import annotations

import pathlib

import pytest

from wbauth.policy.errors import RobotsParseError
from wbauth.policy.parsers import parse_robots

FIX = pathlib.Path(__file__).parent / "fixtures" / "policy" / "robots"


def test_robots_allow_yields_can_fetch_true():
    r = parse_robots(
        (FIX / "allow.txt").read_text(),
        content_type="text/plain",
        target_url="https://example.com/",
    )
    assert r.can_fetch_url is True
    assert "https://example.com/sitemap.xml" in r.sitemaps
    assert r.user_agent_evaluated == "wbauth/0.1"


def test_robots_disallow_blocks_api_path():
    r = parse_robots(
        (FIX / "disallow.txt").read_text(),
        content_type="text/plain",
        target_url="https://example.com/api/users",
    )
    assert r.can_fetch_url is False


def test_robots_disallow_allows_non_blocked_path():
    r = parse_robots(
        (FIX / "disallow.txt").read_text(),
        content_type="text/plain",
        target_url="https://example.com/public/page",
    )
    assert r.can_fetch_url is True


def test_robots_html_200_raises_parse_error():
    """Pitfall 1 anchor: HTML body served as robots.txt → RobotsParseError."""
    with pytest.raises(RobotsParseError):
        parse_robots(
            (FIX / "html_200.txt").read_text(),
            content_type="text/plain",  # origin lies about CT
            target_url="https://example.com/",
        )


def test_robots_html_content_type_raises_parse_error():
    """Even non-HTML body should raise if content-type advertises HTML."""
    with pytest.raises(RobotsParseError):
        parse_robots(
            "User-agent: *\nAllow: /",  # body itself is fine
            content_type="text/html; charset=utf-8",
            target_url="https://example.com/",
        )


def test_robots_malformed_yields_no_directives_no_raise():
    """Random non-robots prose: not HTML, no directives → allow-by-default per RFC 9309."""
    r = parse_robots(
        (FIX / "malformed.txt").read_text(),
        content_type="text/plain",
        target_url="https://example.com/",
    )
    assert r.can_fetch_url is True


def test_robots_empty_yields_can_fetch_true():
    """Empty robots.txt (RFC 9309): no restrictions."""
    r = parse_robots(
        (FIX / "empty.txt").read_text(),
        content_type="text/plain",
        target_url="https://example.com/",
    )
    assert r.can_fetch_url is True


def test_robots_raw_text_preserved():
    text = (FIX / "allow.txt").read_text()
    r = parse_robots(text, content_type="text/plain", target_url="https://example.com/")
    assert r.raw == text
