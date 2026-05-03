"""Tests for `wbauth keygen` CLI (IDENT-01 + CLI-01 + CLI-06).

Uses subprocess to exercise the actual entry point script registered by
`python/pyproject.toml` — the same code path a `pip install wbauth && wbauth ...`
user would hit. Direct main() unit tests would not catch entry-point regressions.

Renamed from `tests/test_cli.py` in Plan 02-03 (Task 1) when the CLI grew
two new subcommands (`inspect`, `verify`) — each gets its own test file.
The Phase-1 keygen tests below are preserved 1:1; the new tests at the
bottom of the file enforce CLI-06's stderr discipline and Ctrl-C exit code.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from unittest.mock import patch

import pytest

from wbauth import cli as cli_module


def _run_keygen(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Spawn `uv run wbauth keygen <args>` and capture its output."""
    return subprocess.run(
        ["uv", "run", "wbauth", "keygen", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def test_keygen_creates_key_at_path(tmp_path):
    """IDENT-01 CLI: --output writes a key file with mode 0o600 on POSIX."""
    keyfile = tmp_path / "key.pem"
    result = _run_keygen("--output", str(keyfile))

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "Wrote key to" in result.stdout
    assert "kid:" in result.stdout
    assert keyfile.exists()

    if sys.platform != "win32":
        mode = stat.S_IMODE(os.stat(keyfile).st_mode)
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


def test_keygen_prints_kid_to_stdout(tmp_path):
    """The printed kid is base64url-no-pad SHA-256: 43 chars from [A-Za-z0-9_-]."""
    keyfile = tmp_path / "key.pem"
    result = _run_keygen("--output", str(keyfile))

    assert result.returncode == 0, f"stderr: {result.stderr}"
    kid_lines = [
        line for line in result.stdout.splitlines() if line.startswith("kid: ")
    ]
    assert len(kid_lines) == 1, f"unexpected stdout: {result.stdout}"
    kid = kid_lines[0].removeprefix("kid: ")
    assert len(kid) == 43, f"kid wrong length: {kid!r}"
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", kid), f"kid wrong chars: {kid!r}"


def test_keygen_existing_file_errors(tmp_path):
    """If --output points at a non-Ed25519 file (or any existing keyfile that
    can't be parsed), exit non-zero with an error message on stderr."""
    keyfile = tmp_path / "key.pem"
    keyfile.write_bytes(b"placeholder")
    if sys.platform != "win32":
        keyfile.chmod(0o600)

    result = _run_keygen("--output", str(keyfile))

    # Existing file with placeholder content is not Ed25519 PEM → exit non-zero
    assert result.returncode != 0
    # Either "error:" prefix from our handler, or any non-empty stderr from
    # the cryptography library bubbling up. Both are acceptable for "informed
    # the user something went wrong."
    assert "error:" in result.stderr.lower() or result.stderr.strip()


# ---------- Plan 02-03: CLI-06 stderr discipline + SIGINT handling ----------


def test_keygen_errors_to_stderr_not_stdout(tmp_path):
    """CLI-06: keygen errors land on stderr; stdout stays empty.

    The Phase-1 handler maps PermissionError/FileExistsError/TypeError/ValueError
    to exit code 2 with `print(..., file=sys.stderr)`. Verify that on the
    "existing non-Ed25519 file" failure path stdout is empty (machine-readable
    pipelines `wbauth keygen ... | jq` only see clean JSON or nothing).
    """
    keyfile = tmp_path / "key.pem"
    keyfile.write_bytes(b"placeholder")
    if sys.platform != "win32":
        keyfile.chmod(0o600)

    result = _run_keygen("--output", str(keyfile))

    # Exit code 2 per the Phase-1 handler taxonomy. The cryptography library
    # itself can also bubble out — but our handler catches ValueError too,
    # so we should always see exit code 2 here.
    assert result.returncode == 2, (
        f"expected 2, got {result.returncode}; stdout={result.stdout!r}; "
        f"stderr={result.stderr!r}"
    )
    assert result.stdout == "", f"stdout should be empty, got: {result.stdout!r}"
    assert "error:" in result.stderr.lower(), (
        f"expected 'error:' on stderr, got: {result.stderr!r}"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signal semantics")
def test_main_returns_130_on_keyboard_interrupt(tmp_path, capsys):
    """CLI-06: Ctrl-C during dispatch returns exit code 130 with stderr msg.

    In-process test (not subprocess): patches the keygen branch's identity
    constructor to raise KeyboardInterrupt. The Plan 02-03 dispatch wrapper
    catches KeyboardInterrupt at the top level and returns 130 uniformly
    across all subcommands. Subprocess SIGINT timing is unreliable in CI
    (keygen is fast); this in-process test is deterministic.
    """
    keyfile = tmp_path / "key.pem"
    with patch(
        "wbauth.cli.Identity.load_or_generate",
        side_effect=KeyboardInterrupt(),
    ):
        rc = cli_module.main(["keygen", "--output", str(keyfile)])

    assert rc == 130, f"expected 130 on KeyboardInterrupt, got {rc}"
    cap = capsys.readouterr()
    assert "interrupted" in cap.err.lower(), (
        f"expected 'interrupted' on stderr, got: {cap.err!r}"
    )
    # Make sure stdout stayed clean — pipelines parsing JSON shouldn't see
    # "interrupted" leak in.
    assert cap.out == "", f"stdout should be empty, got: {cap.out!r}"
