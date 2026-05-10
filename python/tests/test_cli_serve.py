"""Tests for `wbauth serve` argparse + dispatcher (CLI-05, D-50).

The actual stdlib server is exercised end-to-end in test_jwks_server.py;
these tests cover the CLI surface only:
  - argparse wiring (--jwks required, --port default 8080)
  - SIGINT during serve → exit 130 (CLI-06)
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from wbauth.cli import _build_parser, _dispatch_serve


def test_serve_help_exits_0():
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["serve", "--help"])
    assert exc.value.code == 0


def test_serve_requires_jwks():
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["serve"])  # --jwks required


def test_serve_default_port_8080():
    parser = _build_parser()
    args = parser.parse_args(["serve", "--jwks", "/tmp/x.json"])
    assert args.port == 8080


def test_serve_port_can_be_overridden():
    parser = _build_parser()
    args = parser.parse_args(["serve", "--jwks", "/tmp/x.json", "--port", "9000"])
    assert args.port == 9000


def test_dispatch_serve_keyboard_interrupt_returns_130():
    """SIGINT during the serve_forever loop returns 130 per CLI-06.

    The outer main() also catches KeyboardInterrupt and returns 130, so the
    explicit handler in _dispatch_serve is belt-and-suspenders. We assert
    here that calling _dispatch_serve directly (no main() wrapper) still
    returns 130.
    """
    parser = _build_parser()
    args = parser.parse_args(["serve", "--jwks", "/tmp/x.json"])
    with patch("wbauth._http_server.jwks_server.serve", side_effect=KeyboardInterrupt):
        rc = _dispatch_serve(args)
    assert rc == 130
