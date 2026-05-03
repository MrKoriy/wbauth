"""Tests for `wbauth inspect <url>` CLI subcommand (CLI-02 + D-24).

In-process tests via `wbauth.cli.main([...])` with `wbauth.policy.inspector.inspect`
monkeypatched to return canned `SitePolicy` instances. No live HTTP — the
inspector itself is exercised end-to-end by `tests/test_policy_inspector.py`
(via httpx_mock); these tests cover the CLI surface only:

  - exit-code matrix per D-24 (0=allowed, 1=restricted, 2=forbidden,
    3=fetch error / unexpected exception, 130=SIGINT — covered separately
    in test_cli_keygen.py).
  - human-readable output shape (Verdict / URL / Reasons / Partial / Errors /
    Fetched).
  - JSON output is valid JSON, contains all SitePolicy fields, and the
    `errors` dict gets serialized to {"type", "message"} per-exception
    (since Exception is not JSON-serializable by default).
  - stderr discipline: errors go to stderr, success/JSON to stdout (CLI-06).
"""
from __future__ import annotations

import datetime
import json

from unittest.mock import patch

import pytest

from wbauth.cli import main
from wbauth.policy import SitePolicy


def _fake_policy(
    verdict: str = "allowed",
    *,
    partial: bool = False,
    errors: dict | None = None,
    reasons: list[str] | None = None,
) -> SitePolicy:
    """Construct a minimal SitePolicy fixture for CLI tests.

    All four per-endpoint Result slots are None — the CLI doesn't render their
    contents in the human summary (it only renders verdict + reasons + errors),
    and the JSON test verifies dataclasses.asdict() handles None gracefully.
    """
    return SitePolicy(
        url="https://example.com/",
        robots=None,
        ai_txt=None,
        llms_txt=None,
        signing_directory=None,
        verdict=verdict,
        reasons=reasons or ["test reason"],
        partial=partial,
        errors=errors or {},
        fetched_at=datetime.datetime(
            2026, 5, 4, 12, 0, 0, tzinfo=datetime.timezone.utc
        ),
    )


# NOTE on patching async functions:
# `unittest.mock.patch("wbauth.cli.inspect", ...)` auto-detects that the
# original `inspect` is an `async def` and substitutes `AsyncMock` (not
# MagicMock). AsyncMock's `return_value` is what callers see *after*
# awaiting the resulting coroutine. So we pass the bare SitePolicy as
# `return_value` and `asyncio.run(inspect(url))` produces it directly.
# Wrapping the value in another coroutine (e.g. `_async_value`) creates a
# nested coroutine that's never awaited — caused 8 failures the first time
# this file was written.


# ---------- Exit code matrix (D-24) ----------


def test_inspect_exit_code_allowed_returns_0(capsys):
    """D-24: `verdict="allowed"` → exit code 0."""
    with patch(
        "wbauth.cli.inspect",
        return_value=_fake_policy("allowed"),
    ):
        rc = main(["inspect", "https://example.com/"])
    assert rc == 0, f"expected 0 for 'allowed', got {rc}"
    cap = capsys.readouterr()
    assert "Verdict: allowed" in cap.out
    assert cap.err == "", f"stderr should be empty, got: {cap.err!r}"


def test_inspect_exit_code_restricted_returns_1(capsys):
    """D-24: `verdict="restricted"` → exit code 1."""
    with patch(
        "wbauth.cli.inspect",
        return_value=_fake_policy("restricted"),
    ):
        rc = main(["inspect", "https://example.com/"])
    assert rc == 1, f"expected 1 for 'restricted', got {rc}"
    cap = capsys.readouterr()
    assert "Verdict: restricted" in cap.out


def test_inspect_exit_code_forbidden_returns_2(capsys):
    """D-24: `verdict="forbidden"` → exit code 2."""
    with patch(
        "wbauth.cli.inspect",
        return_value=_fake_policy("forbidden"),
    ):
        rc = main(["inspect", "https://example.com/"])
    assert rc == 2, f"expected 2 for 'forbidden', got {rc}"
    cap = capsys.readouterr()
    assert "Verdict: forbidden" in cap.out


def test_inspect_url_value_error_returns_3_with_stderr(capsys):
    """D-24: ValueError from `inspect()` (bad URL) → exit 3 + stderr msg.

    The verdict engine returns *some* verdict on every successful inspect;
    exit 3 is reserved for the case where `inspect()` itself raises (URL
    parse failure, unrecoverable network error). This is the catch-all for
    "we couldn't even produce a SitePolicy".
    """
    with patch(
        "wbauth.cli.inspect",
        side_effect=ValueError("URL has no host"),
    ):
        rc = main(["inspect", "not-a-url"])
    assert rc == 3, f"expected 3 for ValueError, got {rc}"
    cap = capsys.readouterr()
    assert cap.out == "", f"stdout should be empty, got: {cap.out!r}"
    assert "error: invalid URL:" in cap.err
    assert "URL has no host" in cap.err


def test_inspect_unexpected_exception_returns_3_with_stderr(capsys):
    """Generic exception from `inspect()` (e.g., unrecoverable network) → exit 3."""
    with patch(
        "wbauth.cli.inspect",
        side_effect=RuntimeError("connection pool exhausted"),
    ):
        rc = main(["inspect", "https://example.com/"])
    assert rc == 3
    cap = capsys.readouterr()
    assert cap.out == ""
    assert "error: RuntimeError:" in cap.err
    assert "connection pool exhausted" in cap.err


# ---------- Human-readable output shape ----------


def test_inspect_human_summary_contains_all_sections(capsys):
    """Default (no --json) output: Verdict + URL + Reasons + Partial + Errors + Fetched."""
    policy = _fake_policy(
        "restricted",
        partial=True,
        errors={"ai_txt": TimeoutError("3s exceeded")},
        reasons=[
            "evaluated against User-Agent='wbauth/0.1'",
            "robots.txt allows our user-agent for this path",
            "ai.txt fetch failed (partial)",
        ],
    )
    with patch("wbauth.cli.inspect", return_value=policy):
        rc = main(["inspect", "https://example.com/"])
    assert rc == 1
    out = capsys.readouterr().out
    # Section headers per the RESEARCH §"`wbauth inspect <url>`" sample format.
    assert "Verdict: restricted" in out
    assert "URL:" in out and "https://example.com/" in out
    assert "Reasons:" in out
    assert "evaluated against User-Agent='wbauth/0.1'" in out
    assert "robots.txt allows our user-agent for this path" in out
    assert "Partial: true" in out
    assert "Errors:" in out
    assert "ai_txt:" in out and "TimeoutError" in out and "3s exceeded" in out
    assert "Fetched:" in out and "2026-05-04" in out
    # JSON hint on the last line so users can discover the machine-readable mode.
    assert "--json" in out


def test_inspect_human_summary_no_errors_says_none(capsys):
    """When `errors={}`, the human summary prints "Errors:  none" (not an empty bullet list)."""
    with patch(
        "wbauth.cli.inspect",
        return_value=_fake_policy("allowed"),
    ):
        rc = main(["inspect", "https://example.com/"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Errors:" in out
    assert "none" in out.lower()


# ---------- JSON output ----------


def test_inspect_json_serializes_full_policy(capsys):
    """--json: stdout is valid JSON containing all SitePolicy top-level fields."""
    with patch(
        "wbauth.cli.inspect",
        return_value=_fake_policy("restricted"),
    ):
        rc = main(["inspect", "https://example.com/", "--json"])
    assert rc == 1
    out = capsys.readouterr().out
    doc = json.loads(out)  # must parse cleanly
    for key in (
        "url",
        "robots",
        "ai_txt",
        "llms_txt",
        "signing_directory",
        "verdict",
        "reasons",
        "partial",
        "errors",
        "fetched_at",
    ):
        assert key in doc, f"missing JSON key: {key}"
    assert doc["verdict"] == "restricted"
    assert doc["url"] == "https://example.com/"
    assert doc["partial"] is False


def test_inspect_json_serializes_errors_dict_with_type_and_message(capsys):
    """--json: Exception in errors[endpoint] becomes {"type", "message"}.

    Exception objects aren't JSON-serializable by default; the CLI's
    _serialize_policy helper must turn them into a stable dict shape so
    downstream tooling (jq, log shippers, dashboards) can introspect them.
    """
    err = {"ai_txt": TimeoutError("3s exceeded")}
    with patch(
        "wbauth.cli.inspect",
        return_value=_fake_policy("restricted", partial=True, errors=err)
        ,
    ):
        rc = main(["inspect", "https://example.com/", "--json"])
    assert rc == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["partial"] is True
    assert doc["errors"]["ai_txt"] == {
        "type": "TimeoutError",
        "message": "3s exceeded",
    }


def test_inspect_json_datetime_serializes_to_iso_string(capsys):
    """--json: fetched_at is a datetime → must serialize to a string (ISO 8601)."""
    with patch(
        "wbauth.cli.inspect",
        return_value=_fake_policy("allowed"),
    ):
        main(["inspect", "https://example.com/", "--json"])
    doc = json.loads(capsys.readouterr().out)
    assert isinstance(doc["fetched_at"], str)
    # The fixture sets 2026-05-04 noon UTC.
    assert "2026-05-04" in doc["fetched_at"]


def test_inspect_json_value_error_still_uses_stderr(capsys):
    """Even in --json mode, errors go to stderr (CLI-06: machine-readable
    pipelines should never see error noise in stdout)."""
    with patch(
        "wbauth.cli.inspect",
        side_effect=ValueError("bad url"),
    ):
        rc = main(["inspect", "not-a-url", "--json"])
    assert rc == 3
    cap = capsys.readouterr()
    assert cap.out == "", f"stdout must be empty in --json error path, got: {cap.out!r}"
    assert "error: invalid URL:" in cap.err
