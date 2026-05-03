"""Tests for `wbauth keygen` CLI (IDENT-01 CLI half).

Uses subprocess to exercise the actual entry point script registered by
`python/pyproject.toml` — the same code path a `pip install wbauth && wbauth ...`
user would hit. Direct main() unit tests would not catch entry-point regressions.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys


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
