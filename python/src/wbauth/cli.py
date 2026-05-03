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
import asyncio
import dataclasses
import json
import sys

from .identity import DEFAULT_KEY_PATH, Identity
# Top-level import so tests can monkeypatch the symbol via
# `patch("wbauth.cli.inspect", ...)` — the most discoverable target.
# Trade-off: pulls in httpx + asyncio at CLI startup. Acceptable: every
# subcommand except `keygen` needs them anyway, and `keygen` is fast enough
# that a few extra imports don't matter.
from .policy import SitePolicy, inspect


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

    # ---- inspect (Phase 2, CLI-02) -----------------------------------------
    insp = sub.add_parser(
        "inspect",
        help="Run pre-flight policy inspector against a URL.",
        description=(
            "Fetch /robots.txt, /ai.txt, /llms.txt, and "
            "/.well-known/http-message-signatures-directory in parallel, "
            "compute a deterministic strict verdict (allowed/restricted/"
            "forbidden), and print a human-readable summary. Exit code "
            "matches the verdict per D-24: 0=allowed, 1=restricted, "
            "2=forbidden, 3=fetch error or unrecoverable exception."
        ),
    )
    insp.add_argument(
        "url",
        help="Target URL (e.g., https://example.com/path).",
    )
    insp.add_argument(
        "--json",
        action="store_true",
        help="Emit the full SitePolicy as JSON to stdout (machine-readable).",
    )

    # ---- verify (Phase 2, CLI-03) ------------------------------------------
    ver = sub.add_parser(
        "verify",
        help="Run Cloudflare research-verifier conformance check.",
        description=(
            "Sign a probe request with the RFC 9421 Appendix B.1.4 test "
            "key and POST it to Cloudflare's open-spec research verifier "
            "(per L-04). Reports pass/fail per D-25: 0=full pass, "
            "1=partial pass with warnings, 2=verifier rejection. v1 ALWAYS "
            "uses the test key (open question #5) — register in Cloudflare's "
            "verified-bots program for verification against your own key "
            "(Phase 3+)."
        ),
    )
    ver.add_argument(
        "--domain",
        required=True,
        help=(
            "Domain to verify (informational in v1; the actual probe targets "
            "Cloudflare's research verifier per L-04 and is independent of "
            "this value). Phase 3 will wire --domain to a domain-specific "
            "verifier path after directory registration."
        ),
    )
    ver.add_argument(
        "--identity",
        default=None,
        help=(
            "Path to identity key. RESERVED for Phase 3 — v1 always uses "
            "the RFC 9421 test key against the research verifier; passing "
            "this in v1 prints a warning and uses the test key anyway."
        ),
    )
    ver.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON to stdout (strips raw signature material).",
    )

    return parser


# ---------- inspect handler (CLI-02, D-24) ----------


def _serialize_policy(policy: SitePolicy) -> dict:
    """Convert a SitePolicy to a JSON-serializable dict.

    `dataclasses.asdict` walks nested frozen dataclasses but two fields
    need custom handling:

      - ``errors``: maps ``str -> Exception``. Exception isn't
        JSON-serializable; we replace each value with
        ``{"type": <class name>, "message": str(exc)}`` so consumers
        can still introspect what went wrong.
      - ``fetched_at``: a ``datetime``. ``json.dumps(default=str)``
        in the caller turns it into the ISO-8601 string.
    """
    d = dataclasses.asdict(policy)
    d["errors"] = {
        name: {"type": type(exc).__name__, "message": str(exc)}
        for name, exc in policy.errors.items()
    }
    return d


def _print_human_summary(policy: SitePolicy) -> None:
    """Pretty-print a SitePolicy to stdout in the RESEARCH §"`wbauth inspect`"
    sample shape. Section order: Verdict / URL / Reasons / Partial / Errors /
    Fetched, ending with a JSON-discovery hint."""
    print(f"Verdict: {policy.verdict}")
    print(f"URL:     {policy.url}")
    print("Reasons:")
    for reason in policy.reasons:
        print(f"  - {reason}")
    # Lowercase boolean to read more like JSON / shell flags than Python's
    # capitalized "True" / "False".
    print(f"Partial: {str(policy.partial).lower()}")
    if policy.errors:
        print("Errors:")
        for name, exc in policy.errors.items():
            print(f"  - {name}: {type(exc).__name__}: {exc}")
    else:
        print("Errors:  none")
    print(f"Fetched: {policy.fetched_at.isoformat()}")
    print()
    print("(For full SitePolicy JSON, re-run with --json)")


def _dispatch_inspect(args: argparse.Namespace) -> int:
    """CLI-02 + D-24 handler.

    Calls ``asyncio.run(inspect(args.url))`` and maps the verdict to an
    exit code. ``ValueError`` from URL parsing → exit 3 with stderr msg;
    any other unexpected exception → exit 3 with stderr msg
    (CLI-06: errors never leak to stdout, even in --json mode, so JSON
    consumers always see a clean parseable document or an empty stdout).
    """
    try:
        policy: SitePolicy = asyncio.run(inspect(args.url))
    except ValueError as e:
        # URL parse errors from inspect() itself (e.g., httpx URL parsing).
        print(f"error: invalid URL: {e}", file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001 — last-resort error path
        # Anything else that escaped the inspector's per-endpoint error
        # isolation (network pool exhaustion, asyncio runtime errors, etc.).
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    if args.json:
        # default=str handles the datetime field (fetched_at).
        print(json.dumps(_serialize_policy(policy), default=str))
    else:
        _print_human_summary(policy)
    return {"allowed": 0, "restricted": 1, "forbidden": 2}.get(policy.verdict, 3)


# ---------- verify handler (CLI-03, D-25) ----------

# T-02-03-02: keys to STRIP from `--json` output. The raw signed-header
# values are useful in the daily-cron failure diagnostic (run() in
# cloudflare_debug.py prints them on FAIL) but must never reach `wbauth
# verify --json` consumers — log shippers / dashboards would happily
# index a header that proves a Web Bot Auth signature against the test key.
_VERIFY_JSON_STRIP_KEYS = ("signature_input", "signature", "signature_agent")


def _print_verify_human(result: dict) -> None:
    """Pretty-print a `_probe_verifier` result to stdout in the
    RESEARCH §"`wbauth verify --domain <domain>`" sample shape.

    The "Identity" line surfaces the v1 caveat (test key) so users
    immediately see why their `--identity` arg, if passed, was ignored.
    """
    print("Identity: test key (RFC 9421 Appendix B.1.4)")
    print(f"Target:   {result['verifier_url']}")
    print(f"Domain:   {result['domain']} (informational in v1)")
    print("Probe:    GET /")
    print(f"Result:   {'PASS' if result['result'] == 'pass' else 'FAIL'}")
    print(f"  Status:  {result['status']}")
    print(f"  Banner:  {result['banner']!r}")
    print(f"  kid:     {result['kid']}")


def _dispatch_verify(args: argparse.Namespace) -> int:
    """CLI-03 + D-25 handler.

    Open question #5 resolution: `--identity` is parsed but always ignored
    in v1 — the Cloudflare research verifier only validates the RFC 9421
    test key. We print a stderr warning so users see why their key wasn't
    used, then proceed with the test key. The warning lands on stderr (not
    stdout) so JSON-consuming pipelines aren't disrupted (CLI-06).
    """
    # Lazy import: keeps `wbauth keygen` (Phase 1) from paying the smoke-module
    # import cost on every CLI invocation.
    from ._smoke.cloudflare_debug import run_against_domain

    if args.identity:
        print(
            "warning: --identity is reserved for Phase 3+ "
            "(registered-key verification); v1 always uses the test key "
            "against Cloudflare's research verifier",
            file=sys.stderr,
        )
    try:
        result = asyncio.run(run_against_domain(args.domain, args.identity))
    except Exception as e:  # noqa: BLE001 — last-resort error path
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    if args.json:
        # T-02-03-02: strip raw signed-header values before serializing.
        clean = {k: v for k, v in result.items() if k not in _VERIFY_JSON_STRIP_KEYS}
        print(json.dumps(clean))
    else:
        _print_verify_human(result)
    return result["exit_code"]


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
    if args.cmd == "inspect":
        return _dispatch_inspect(args)
    if args.cmd == "verify":
        return _dispatch_verify(args)
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
