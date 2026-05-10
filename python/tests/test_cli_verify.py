"""Tests for `wbauth verify --domain` CLI subcommand (CLI-03 + D-25).

Mocks the Cloudflare research verifier with `pytest-httpx` so unit tests
don't require live network access (the Phase-1 daily cron at
`.github/workflows/cloudflare-debug.yml` handles the real-network smoke
check separately, on its daily schedule).

Coverage:

  - Exit-code matrix per D-25: 0=pass / 1=warn / 2=fail (130=SIGINT is
    covered uniformly in test_cli_keygen.py).
  - Open-question #5 resolution: `wbauth verify` ALWAYS uses the RFC 9421
    Appendix B.1.4 test key in v1; `--identity` is parsed for forward
    compatibility but a stderr warning fires AND the test key kid still
    appears in the actual Signature-Input header (the user's key is never
    even read).
  - Stderr discipline: warnings + errors → stderr, success/JSON → stdout.
  - JSON output shape: `result`, `exit_code`, `kid`, `status`, `banner`,
    `domain`, `verifier_url` all present; raw signature material stripped
    (T-02-03-02 mitigation).
"""
from __future__ import annotations

import json


from wbauth.cli import main
from wbauth._smoke.cloudflare_debug import (
    CF_RESEARCH_VERIFIER_URL,
    FAILURE_BANNER,
    SUCCESS_BANNER,
)

# RFC 9421 Appendix B.1.4 test key kid — must appear in the Signature-Input
# header on every `wbauth verify` invocation in v1 (open question #5).
TEST_KEY_KID = "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U"


# ---------- Exit code matrix (D-25) ----------


def test_verify_pass_returns_0(capsys, httpx_mock):
    """D-25: success banner in 200 response → exit code 0 + PASS in stdout."""
    httpx_mock.add_response(
        url=CF_RESEARCH_VERIFIER_URL,
        status_code=200,
        text=f"<html><body>{SUCCESS_BANNER}</body></html>",
    )
    rc = main(["verify", "--domain", "example.com"])
    assert rc == 0, f"expected 0 for pass, got {rc}"
    cap = capsys.readouterr()
    assert "PASS" in cap.out
    # The v1 caveat ("test key") must be visible to the user — we never
    # silently use a key they didn't supply.
    assert "test key" in cap.out.lower()


def test_verify_fail_returns_2(capsys, httpx_mock):
    """D-25: failure banner in 200 response → exit code 2 + FAIL in stdout."""
    httpx_mock.add_response(
        url=CF_RESEARCH_VERIFIER_URL,
        status_code=200,
        text=f"<html><body>{FAILURE_BANNER}</body></html>",
    )
    rc = main(["verify", "--domain", "example.com"])
    assert rc == 2, f"expected 2 for fail banner, got {rc}"
    cap = capsys.readouterr()
    assert "FAIL" in cap.out


def test_verify_unknown_banner_returns_2(capsys, httpx_mock):
    """Neither banner in 200 response → fail (defensive default)."""
    httpx_mock.add_response(
        url=CF_RESEARCH_VERIFIER_URL,
        status_code=200,
        text="<html><body>completely unexpected response</body></html>",
    )
    rc = main(["verify", "--domain", "example.com"])
    assert rc == 2


def test_verify_non_200_returns_2(capsys, httpx_mock):
    """Non-200 (CDN/network issue) → exit 2."""
    httpx_mock.add_response(
        url=CF_RESEARCH_VERIFIER_URL,
        status_code=503,
        text="",
    )
    rc = main(["verify", "--domain", "example.com"])
    assert rc == 2


# ---------- Open question #5: --identity is reserved but ignored in v1 ----------


def test_verify_identity_arg_warns_but_uses_test_key(capsys, httpx_mock):
    """Open question #5: `--identity <path>` triggers a stderr warning AND
    the actual signature still uses the RFC 9421 test key kid.

    Two assertions:
      1. stderr contains the "reserved for Phase 3" warning (so the user
         knows their key wasn't used).
      2. The captured outgoing Signature-Input header references the test
         key kid (proves the user's key was never even loaded).
    """
    httpx_mock.add_response(
        url=CF_RESEARCH_VERIFIER_URL,
        status_code=200,
        text=f"<html><body>{SUCCESS_BANNER}</body></html>",
    )
    rc = main(
        [
            "verify",
            "--domain",
            "example.com",
            "--identity",
            "/some/non-existent/path",
        ]
    )
    assert rc == 0  # the test key is still valid → pass
    cap = capsys.readouterr()
    assert "warning:" in cap.err.lower()
    assert "reserved for phase 3" in cap.err.lower()
    # Inspect the outgoing request — pytest-httpx captures it.
    sent = httpx_mock.get_requests()[0]
    sig_input = sent.headers.get("signature-input", "")
    assert TEST_KEY_KID in sig_input, (
        f"expected test-key kid in Signature-Input, got: {sig_input!r}"
    )


# ---------- JSON output shape (T-02-03-02: no raw signature material) ----------


def test_verify_json_output_shape(capsys, httpx_mock):
    """--json: stdout is valid JSON with the documented top-level keys."""
    httpx_mock.add_response(
        url=CF_RESEARCH_VERIFIER_URL,
        status_code=200,
        text=f"<html><body>{SUCCESS_BANNER}</body></html>",
    )
    rc = main(["verify", "--domain", "example.com", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    doc = json.loads(out)
    for key in (
        "result",
        "exit_code",
        "kid",
        "status",
        "banner",
        "domain",
        "verifier_url",
    ):
        assert key in doc, f"missing JSON key: {key}"
    assert doc["result"] == "pass"
    assert doc["exit_code"] == 0
    assert doc["domain"] == "example.com"
    assert doc["kid"] == TEST_KEY_KID
    assert doc["verifier_url"] == CF_RESEARCH_VERIFIER_URL


def test_verify_json_strips_raw_signature_material(capsys, httpx_mock):
    """T-02-03-02 mitigation: --json output must NOT include the raw
    Signature / Signature-Input / Signature-Agent values.

    The internal probe dict carries them for the failure-diagnostic path,
    but JSON consumers should only see the public summary fields. This
    test pins the contract so a future refactor doesn't accidentally
    leak signed-header values into log shippers.
    """
    httpx_mock.add_response(
        url=CF_RESEARCH_VERIFIER_URL,
        status_code=200,
        text=f"<html><body>{SUCCESS_BANNER}</body></html>",
    )
    main(["verify", "--domain", "example.com", "--json"])
    doc = json.loads(capsys.readouterr().out)
    for forbidden in ("signature_input", "signature", "signature_agent"):
        assert forbidden not in doc, (
            f"JSON output must not include {forbidden!r}: {doc!r}"
        )


# ---------- Stderr discipline (CLI-06) ----------


def test_verify_warning_in_stderr_not_stdout(capsys, httpx_mock):
    """The --identity warning must NEVER leak into stdout — JSON consumers
    parsing `wbauth verify --json --identity /x | jq` should always see a
    valid JSON document on stdout."""
    httpx_mock.add_response(
        url=CF_RESEARCH_VERIFIER_URL,
        status_code=200,
        text=f"<html><body>{SUCCESS_BANNER}</body></html>",
    )
    main(
        [
            "verify",
            "--domain",
            "example.com",
            "--identity",
            "/some/path",
            "--json",
        ]
    )
    cap = capsys.readouterr()
    # JSON on stdout, parseable.
    json.loads(cap.out)
    # Warning on stderr, not stdout.
    assert "warning:" in cap.err.lower()
    assert "warning" not in cap.out.lower()
