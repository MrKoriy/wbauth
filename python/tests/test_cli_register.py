"""Tests for `wbauth register` CLI subcommand (CLI-04, D-49).

Pattern note: in-process tests via `_build_parser` + `_dispatch_register` +
the module-level async helper `_do_register`. HTTP traffic mocked via
`pytest-httpx`. No live network. The Pitfall 5 regression guard
(`mock_sign.call_count == 1`) ensures the register flow re-uses
`wbauth.signer.sign` rather than re-implementing RFC 9421 inline.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from wbauth.cli import _build_parser, _do_register, _dispatch_register


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_keyfile(tmp_path: Path) -> Path:
    """Generate a real Ed25519 keyfile via Identity.load_or_generate.

    A REAL keypair lets `wbauth.signer.sign` actually run inside `_do_register`
    so we exercise the production code path instead of mocking the signer.
    """
    from wbauth.identity import Identity

    keypath = tmp_path / "key.pem"
    Identity.load_or_generate(keypath, signature_agent_url="https://example.com")
    return keypath


# ---------- argparse wiring ----------


def test_register_help_exits_0():
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["register", "--help"])
    assert exc.value.code == 0


def test_register_default_directory_is_production_worker():
    """D-49: --directory defaults to https://wbauth.silov801.workers.dev."""
    parser = _build_parser()
    args = parser.parse_args(["register", "--identity", "/tmp/k"])
    assert args.directory == "https://wbauth.silov801.workers.dev"


def test_register_requires_identity():
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["register"])  # --identity required


def test_register_optional_args_default_none():
    parser = _build_parser()
    args = parser.parse_args(["register", "--identity", "/tmp/k"])
    assert args.client_name is None
    assert args.purpose is None
    assert args.client_uri is None
    assert args.expected_user_agent is None


# ---------- _do_register happy path + Pitfall 5 regression ----------


async def test_do_register_happy_path_calls_sign_once(tmp_path, httpx_mock):
    """Pitfall 5 regression: register MUST reuse wbauth.sign(), not re-implement.

    Asserts mock_sign.call_count == 1 — exactly one signature per registration
    (we sign the /register/submit POST, nothing else).
    """
    keypath = _make_keyfile(tmp_path)
    httpx_mock.add_response(
        url="https://wbauth.test/register/challenge",
        method="POST",
        json={"challenge": "deadbeef" * 4, "expires_at": 9999999999},
    )
    httpx_mock.add_response(
        url="https://wbauth.test/register/submit",
        method="POST",
        json={
            "kid": "test-kid",
            "directory_url": "https://wbauth.test/.well-known/http-message-signatures-directory/test-kid",
        },
        status_code=201,
    )
    from wbauth import signer as _signer

    with patch.object(_signer, "sign", wraps=_signer.sign) as mock_sign:
        result = await _do_register(
            identity_path=str(keypath),
            directory_url="https://wbauth.test",
            client_name="testbot",
            purpose=None,
            client_uri=None,
            expected_user_agent=None,
        )
    assert result["directory_url"].startswith("https://wbauth.test")
    assert mock_sign.call_count == 1, (
        "register should sign exactly once (the /register/submit POST). "
        "Pitfall 5: do NOT re-implement signing inline in cli.py."
    )


async def test_do_register_submit_post_includes_signature_headers(tmp_path, httpx_mock):
    """The /register/submit POST must carry Signature, Signature-Input, and
    Signature-Agent headers produced by wbauth.signer.sign."""
    keypath = _make_keyfile(tmp_path)
    httpx_mock.add_response(
        url="https://wbauth.test/register/challenge",
        method="POST",
        json={"challenge": "ab" * 16, "expires_at": 9999999999},
    )
    httpx_mock.add_response(
        url="https://wbauth.test/register/submit",
        method="POST",
        json={"kid": "k", "directory_url": "https://wbauth.test/d/k"},
        status_code=201,
    )
    await _do_register(
        identity_path=str(keypath),
        directory_url="https://wbauth.test",
        client_name="bot",
        purpose=None,
        client_uri=None,
        expected_user_agent=None,
    )
    requests = httpx_mock.get_requests()
    submit = [r for r in requests if r.url.path == "/register/submit"]
    assert len(submit) == 1
    req = submit[0]
    assert "signature" in {h.lower() for h in req.headers.keys()}
    assert "signature-input" in {h.lower() for h in req.headers.keys()}
    assert "signature-agent" in {h.lower() for h in req.headers.keys()}


# ---------- _do_register error path ----------


async def test_do_register_rejection_raises_http_status_error(tmp_path, httpx_mock):
    """HTTP 422 (reserved name) propagates as httpx.HTTPStatusError."""
    keypath = _make_keyfile(tmp_path)
    httpx_mock.add_response(
        url="https://wbauth.test/register/challenge",
        method="POST",
        json={"challenge": "ab" * 16, "expires_at": 9999999999},
    )
    httpx_mock.add_response(
        url="https://wbauth.test/register/submit",
        method="POST",
        json={"error": "reserved_name", "blocked_token": "google"},
        status_code=422,
    )
    with pytest.raises(httpx.HTTPStatusError) as exc:
        await _do_register(
            identity_path=str(keypath),
            directory_url="https://wbauth.test",
            client_name="google",
            purpose=None,
            client_uri=None,
            expected_user_agent=None,
        )
    assert exc.value.response.status_code == 422


async def test_do_register_challenge_rejection_raises(tmp_path, httpx_mock):
    """If the /register/challenge step itself rejects (e.g. 429 rate-limit),
    we surface that immediately without proceeding to /submit."""
    keypath = _make_keyfile(tmp_path)
    httpx_mock.add_response(
        url="https://wbauth.test/register/challenge",
        method="POST",
        json={"error": "rate_limited"},
        status_code=429,
    )
    with pytest.raises(httpx.HTTPStatusError) as exc:
        await _do_register(
            identity_path=str(keypath),
            directory_url="https://wbauth.test",
            client_name="bot",
            purpose=None,
            client_uri=None,
            expected_user_agent=None,
        )
    assert exc.value.response.status_code == 429


# ---------- _dispatch_register exit codes (sync — no anyio mark) ----------


def test_dispatch_register_success_returns_0(tmp_path, httpx_mock, capsys):
    """Happy path: exit 0 + 'Registered.' on stdout."""
    keypath = _make_keyfile(tmp_path)
    httpx_mock.add_response(
        url="https://wbauth.test/register/challenge",
        method="POST",
        json={"challenge": "ab" * 16, "expires_at": 9999999999},
    )
    httpx_mock.add_response(
        url="https://wbauth.test/register/submit",
        method="POST",
        json={
            "kid": "test-kid",
            "directory_url": "https://wbauth.test/.well-known/http-message-signatures-directory/test-kid",
        },
        status_code=201,
    )
    parser = _build_parser()
    args = parser.parse_args([
        "register",
        "--identity", str(keypath),
        "--directory", "https://wbauth.test",
        "--client-name", "testbot",
    ])
    rc = _dispatch_register(args)
    assert rc == 0
    cap = capsys.readouterr()
    assert "Registered" in cap.out
    assert "directory_url" in cap.out


def test_dispatch_register_rejection_returns_1(tmp_path, httpx_mock, capsys):
    """HTTP 422 → exit 1, error message on stderr (CLI-06)."""
    keypath = _make_keyfile(tmp_path)
    httpx_mock.add_response(
        url="https://wbauth.test/register/challenge",
        method="POST",
        json={"challenge": "ab" * 16, "expires_at": 9999999999},
    )
    httpx_mock.add_response(
        url="https://wbauth.test/register/submit",
        method="POST",
        json={"error": "reserved_name", "blocked_token": "google"},
        status_code=422,
    )
    parser = _build_parser()
    args = parser.parse_args([
        "register",
        "--identity", str(keypath),
        "--directory", "https://wbauth.test",
        "--client-name", "google",
    ])
    rc = _dispatch_register(args)
    assert rc == 1
    cap = capsys.readouterr()
    assert "error" in cap.err.lower()
    assert "422" in cap.err
    # CLI-06: errors NEVER on stdout
    assert cap.out == "" or "Registered" not in cap.out


def test_dispatch_register_rate_limit_returns_1(tmp_path, httpx_mock, capsys):
    """HTTP 429 (rate_limited) → exit 1."""
    keypath = _make_keyfile(tmp_path)
    httpx_mock.add_response(
        url="https://wbauth.test/register/challenge",
        method="POST",
        json={"error": "rate_limited"},
        status_code=429,
    )
    parser = _build_parser()
    args = parser.parse_args([
        "register",
        "--identity", str(keypath),
        "--directory", "https://wbauth.test",
        "--client-name", "bot",
    ])
    rc = _dispatch_register(args)
    assert rc == 1
    cap = capsys.readouterr()
    assert "429" in cap.err
