"""Tests for wbauth.policy.verdict.compute_verdict.

Pure-function tests against the 16-row rule table from RESEARCH §"Verdict
Engine Rule Table". Each test constructs minimal Result/error inputs and
asserts both the verdict literal and that key reason strings are present.
"""
from __future__ import annotations

import httpx
import pytest

from wbauth.policy.errors import RobotsParseError
from wbauth.policy.policy import (
    AiTxtResult,
    LlmsTxtResult,
    LlmsTxtSection,
    RobotsResult,
    SigningDirectoryResult,
)
from wbauth.policy.verdict import compute_verdict


def _robots(can_fetch: bool = True) -> RobotsResult:
    return RobotsResult(
        can_fetch_url=can_fetch,
        sitemaps=[],
        raw="User-agent: *\nAllow: /",
        user_agent_evaluated="wbauth/0.1",
    )


def _ai_txt(restrictions: list[str] | None = None, permissions: list[str] | None = None) -> AiTxtResult:
    return AiTxtResult(
        identity={"name": "Example"},
        permissions=permissions or [],
        restrictions=restrictions or [],
        raw="",
    )


def _llms_txt(description: str = "") -> LlmsTxtResult:
    return LlmsTxtResult(
        title="Example",
        description=description,
        sections=[LlmsTxtSection(name="Docs", links=[])],
        raw="",
    )


def _signing_dir(present: bool = True) -> SigningDirectoryResult:
    return SigningDirectoryResult(
        present=present,
        keys=[{"kid": "x"}] if present else [],
        content_type_correct=True,
        raw="",
    )


def _http_status(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.com/robots.txt")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError(f"{code}", request=request, response=response)


# --- Allowed paths ---------------------------------------------------------

def test_verdict_robots_allow_alone_yields_allowed():
    verdict, reasons = compute_verdict(
        robots=_robots(True), ai_txt=None, llms_txt=None,
        signing_directory=None, errors={}, partial=False,
    )
    assert verdict == "allowed"
    assert any("allows our user-agent" in r for r in reasons)
    # Pitfall 2: UA assumption surfaced
    assert any("wbauth/0.1" in r for r in reasons)


def test_verdict_robots_404_with_no_other_signals_yields_allowed():
    """RFC 9309: robots.txt 404 = no robots-based restriction."""
    verdict, reasons = compute_verdict(
        robots=None, ai_txt=None, llms_txt=None, signing_directory=None,
        errors={"robots": _http_status(404)}, partial=False,
    )
    assert verdict == "allowed"
    assert any("404" in r and "RFC 9309" in r for r in reasons)


def test_verdict_signing_directory_presence_alone_yields_allowed():
    """Pitfall 3 anchor: directory presence ALONE is advisory, NOT restricted."""
    verdict, reasons = compute_verdict(
        robots=_robots(True), ai_txt=None, llms_txt=None,
        signing_directory=_signing_dir(present=True),
        errors={}, partial=False,
    )
    assert verdict == "allowed"
    assert any("signing-directory published" in r for r in reasons)


def test_verdict_robots_allow_plus_ai_permissions_yields_allowed():
    verdict, _ = compute_verdict(
        robots=_robots(True),
        ai_txt=_ai_txt(permissions=["Summarise content"]),
        llms_txt=None, signing_directory=None,
        errors={}, partial=False,
    )
    assert verdict == "allowed"


# --- Restricted paths ------------------------------------------------------

def test_verdict_ai_txt_restrictions_yields_restricted():
    """D-21 anchor: ai.txt restrictions → restricted, NOT forbidden."""
    verdict, reasons = compute_verdict(
        robots=_robots(True),
        ai_txt=_ai_txt(restrictions=["No AI training", "No commercial use"]),
        llms_txt=None, signing_directory=None,
        errors={}, partial=False,
    )
    assert verdict == "restricted"
    assert any("ai.txt restrictions present" in r for r in reasons)


def test_verdict_partial_downgrades_allowed_to_restricted():
    """D-18 tie-break: partial fetch + would-be-allowed → restricted."""
    verdict, reasons = compute_verdict(
        robots=_robots(True), ai_txt=None, llms_txt=None,
        signing_directory=None,
        errors={"ai_txt": httpx.ConnectError("network")},
        partial=True,
    )
    assert verdict == "restricted"
    assert any("partial policy fetch" in r and "downgrades to restricted" in r for r in reasons)


def test_verdict_robots_timeout_yields_restricted():
    verdict, reasons = compute_verdict(
        robots=None, ai_txt=None, llms_txt=None, signing_directory=None,
        errors={"robots": httpx.TimeoutException("3s")}, partial=True,
    )
    assert verdict == "restricted"
    assert any("timed out" in r for r in reasons)


def test_verdict_robots_5xx_yields_restricted():
    verdict, reasons = compute_verdict(
        robots=None, ai_txt=None, llms_txt=None, signing_directory=None,
        errors={"robots": _http_status(503)}, partial=True,
    )
    assert verdict == "restricted"
    assert any("503" in r for r in reasons)


def test_verdict_llms_txt_restrictive_phrase_yields_restricted():
    """llms.txt description matching restrictive regex → restricted."""
    verdict, reasons = compute_verdict(
        robots=_robots(True), ai_txt=None,
        llms_txt=_llms_txt(description="Please do not scrape this site."),
        signing_directory=None,
        errors={}, partial=False,
    )
    assert verdict == "restricted"
    assert any("llms.txt description suggests" in r for r in reasons)


def test_verdict_llms_txt_no_automated_access_yields_restricted():
    verdict, _ = compute_verdict(
        robots=_robots(True), ai_txt=None,
        llms_txt=_llms_txt(description="No automated access permitted."),
        signing_directory=None,
        errors={}, partial=False,
    )
    assert verdict == "restricted"


def test_verdict_no_clean_signals_yields_restricted_insufficient():
    """All endpoints errored non-terminally + robots is None → restricted."""
    verdict, reasons = compute_verdict(
        robots=None, ai_txt=None, llms_txt=None, signing_directory=None,
        errors={
            "robots": httpx.ConnectError("net"),
            "ai_txt": httpx.ConnectError("net"),
            "llms_txt": httpx.ConnectError("net"),
            "signing_directory": httpx.ConnectError("net"),
        },
        partial=True,
    )
    assert verdict == "restricted"
    assert any("insufficient policy signal" in r for r in reasons)


# --- Forbidden paths -------------------------------------------------------

def test_verdict_robots_disallow_yields_forbidden():
    verdict, reasons = compute_verdict(
        robots=_robots(can_fetch=False),
        ai_txt=None, llms_txt=None, signing_directory=None,
        errors={}, partial=False,
    )
    assert verdict == "forbidden"
    assert any("disallows our user-agent" in r for r in reasons)


def test_verdict_robots_html_200_yields_forbidden():
    """Pitfall 1 anchor: HTML body on /robots.txt → RobotsParseError → forbidden."""
    verdict, reasons = compute_verdict(
        robots=None, ai_txt=None, llms_txt=None, signing_directory=None,
        errors={"robots": RobotsParseError("HTML body")},
        partial=True,
    )
    assert verdict == "forbidden"
    assert any("unparseable" in r.lower() for r in reasons)


def test_verdict_robots_disallow_plus_ai_restrictions_still_forbidden():
    """Forbidden short-circuits, but reasons should include both signals."""
    verdict, reasons = compute_verdict(
        robots=_robots(can_fetch=False),
        ai_txt=_ai_txt(restrictions=["No AI training"]),
        llms_txt=None, signing_directory=None,
        errors={}, partial=False,
    )
    assert verdict == "forbidden"
    joined = " ".join(reasons)
    assert "disallows" in joined
    assert "ai.txt restrictions present" in joined


# --- Reason ordering -------------------------------------------------------

def test_verdict_reasons_ordered_robots_first_then_ai_then_llms_then_signdir():
    """Per RESEARCH §"Composition" the reasons list is ordered by source."""
    verdict, reasons = compute_verdict(
        robots=_robots(True),
        ai_txt=_ai_txt(permissions=["Summarise"]),
        llms_txt=_llms_txt(description="A demo"),
        signing_directory=_signing_dir(present=True),
        errors={}, partial=False,
    )
    assert verdict == "allowed"
    # The robots-related reason must precede ai/llms/signdir reasons.
    robots_idx = next(i for i, r in enumerate(reasons) if "robots.txt" in r)
    ai_idx = next(i for i, r in enumerate(reasons) if "ai.txt" in r)
    llms_idx = next(i for i, r in enumerate(reasons) if "llms.txt" in r)
    sign_idx = next(i for i, r in enumerate(reasons) if "signing-directory" in r)
    assert robots_idx < ai_idx < llms_idx < sign_idx
