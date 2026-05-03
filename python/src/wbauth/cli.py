"""wbauth CLI.

Subcommands:

- ``keygen``  (Phase 1, IDENT-01) — generate an Ed25519 keypair on disk.
- ``inspect`` (Phase 2, CLI-02)   — pre-flight policy check for a URL.
- ``verify``  (Phase 2, CLI-03)   — Cloudflare research-verifier conformance check.

Unified exit-code matrix (CLI-06, D-24, D-25):

==========  ===================================================  ========
Subcommand  Exit codes                                           SIGINT
==========  ===================================================  ========
keygen      0 success / 2 error                                  130
inspect     0 allowed / 1 restricted / 2 forbidden / 3 fetch-err 130
verify      0 pass / 1 partial / 2 fail                          130
==========  ===================================================  ========

Errors and warnings always go to stderr; success output and JSON go to
stdout. The dispatch loop wraps every subcommand in a single
``try/except KeyboardInterrupt`` so Ctrl-C produces exit 130 uniformly
across the surface (no subcommand has to remember to handle it).

Entry point declared in ``python/pyproject.toml``::

    [project.scripts]
    wbauth = "wbauth.cli:main"
"""
from __future__ import annotations

import argparse
import sys

from .identity import DEFAULT_KEY_PATH, Identity


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argparse tree for `wbauth ...`.

    Split out so subcommand wiring stays readable as the surface grows.
    Each subcommand's `_dispatch_<name>` handler in this module reads the
    parsed Namespace and returns an int exit code.
    """
    parser = argparse.ArgumentParser(
        prog="wbauth",
        description="Web Bot Auth (RFC 9421) toolkit for AI agents.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ---- keygen (Phase 1, IDENT-01) ----------------------------------------
    kg = sub.add_parser(
        "keygen",
        help="Generate an Ed25519 keypair and print the kid.",
        description=(
            "Generate a new Ed25519 keypair. Writes the private key in PKCS8 "
            "PEM at the given path with mode 0o600 (POSIX). Refuses to "
            "overwrite an existing file. Prints the RFC 7638 kid to stdout."
        ),
    )
    kg.add_argument(
        "--output",
        default=str(DEFAULT_KEY_PATH),
        help=f"Where to write the private key (default: {DEFAULT_KEY_PATH}).",
    )
    kg.add_argument(
        "--signature-agent-url",
        default="https://example.invalid/placeholder",
        help=(
            "Placeholder URL — `wbauth keygen` only needs the kid; the real "
            "value goes into Identity construction in code."
        ),
    )

    # `inspect` and `verify` subparsers are registered in Plan 02-03 Tasks 2 & 3
    # (this module). They live in the same parser tree so `wbauth --help`
    # surfaces the full surface in one place.

    return parser


def _dispatch_keygen(args: argparse.Namespace) -> int:
    """Phase-1 keygen handler. Preserved 1:1 from the Phase-1 cli.py.

    Exit codes per CLI-06:
      - 0: key written successfully.
      - 2: PermissionError / FileExistsError / TypeError / ValueError —
        anything that prevented us from writing a usable key.

    Stderr discipline: error messages prefixed with ``error:`` go to stderr;
    success lines (path + kid) go to stdout.
    """
    try:
        identity = Identity.load_or_generate(
            args.output,
            signature_agent_url=args.signature_agent_url,
        )
    except (PermissionError, FileExistsError, TypeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"Wrote key to {args.output} (mode 0o600)")
    print(f"kid: {identity.kid}")
    return 0


def _dispatch(args: argparse.Namespace) -> int:
    """Route a parsed Namespace to the per-subcommand handler.

    Subcommand handlers are imported lazily so an `argparse error` doesn't
    pay the import cost of every Phase-2 subsystem (httpx + asyncio + the
    policy inspector all live behind `inspect` / `verify`).
    """
    if args.cmd == "keygen":
        return _dispatch_keygen(args)
    # Future subcommands wired in Tasks 2 & 3.
    return 1


def main(argv: list[str] | None = None) -> int:
    """Dispatch a single subcommand. Returns process exit code.

    `argv` defaults to `sys.argv[1:]` when None — the standard argparse pattern.
    Tests pass an explicit list to avoid touching the global argv.

    All KeyboardInterrupt exits return 130 with an "interrupted" message on
    stderr (CLI-06). This is the single place that catches Ctrl-C — every
    subcommand inherits the behavior; no per-subcommand handler needs its own
    try/except.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
