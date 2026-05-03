"""wbauth CLI.

Phase 1: only `keygen` subcommand (satisfies IDENT-01 CLI half).
Phase 2 will add `inspect`, `verify`, `register`, `serve` subcommands per
REQUIREMENTS.md CLI-01..05.

Entry point declared in `python/pyproject.toml`:
    [project.scripts]
    wbauth = "wbauth.cli:main"
"""
from __future__ import annotations

import argparse
import sys

from .identity import DEFAULT_KEY_PATH, Identity


def main(argv: list[str] | None = None) -> int:
    """Dispatch a single subcommand. Returns process exit code.

    `argv` defaults to `sys.argv[1:]` when None — the standard argparse pattern.
    Tests pass an explicit list to avoid touching the global argv.
    """
    parser = argparse.ArgumentParser(
        prog="wbauth",
        description="Web Bot Auth (RFC 9421) toolkit for AI agents.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

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

    args = parser.parse_args(argv)

    if args.cmd == "keygen":
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

    return 1


if __name__ == "__main__":
    sys.exit(main())
