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
import json
import os
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
        "--keyring",
        default=None,
        metavar="DIR",
        help="Create DIR/active.pem instead of --output (pair with `wbauth rotate`).",
    )
    kg.add_argument(
        "--signature-agent-url",
        default="https://example.invalid/placeholder",
        help=(
            "Placeholder URL — `wbauth keygen` only needs the kid; the real "
            "value goes into Identity construction in code."
        ),
    )
    # Phase 3, D-51: optional JWKS dump for self-hosters who'll feed it into
    # `wbauth serve` (CLI-05) or publish at their own well-known path. Keeping
    # the flag opt-in preserves Phase 1 IDENT-01 behavior (no extra files
    # written by default).
    kg.add_argument(
        "--jwks-output",
        default=None,
        help=(
            "If set, also write the public JWKS document (no private key) "
            "to this path. Pair with `wbauth serve --jwks <path>` for a "
            "stdlib JWKS host (CLI-05)."
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
            "2=forbidden, 3=invalid URL, unexpected error, or the site was "
            "unreachable (every policy endpoint failed with a network error)."
        ),
    )
    insp.add_argument(
        "url",
        help="Target URL (e.g., https://example.com/path).",
    )
    insp.add_argument(
        "--json",
        action="store_true",
        help="Emit the full SitePolicy as JSON to stdout (alias of --format json).",
    )
    insp.add_argument(
        "--format",
        choices=("text", "table", "json"),
        default=None,
        help="Output format: text (default), table (per-source breakdown, "
        "colored on a TTY; honours NO_COLOR), or json.",
    )
    insp.add_argument(
        "--cache",
        metavar="PATH",
        default=None,
        help="Persist the policy cache in this JSON file between runs "
        "(skips re-downloading fresh policy files).",
    )
    insp.add_argument(
        "--user-agent",
        default=None,
        help="Evaluate robots.txt for this User-Agent (default: wbauth/<version>).",
    )
    insp.add_argument(
        "--include-raw",
        action="store_true",
        help="With --json: also include the raw policy file bodies.",
    )
    insp.add_argument(
        "--no-private",
        action="store_true",
        help="Refuse targets on loopback/private networks (SSRF guard).",
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
    # Deprecated no-op flags kept (hidden) so existing scripts don't break:
    # the probe always targets Cloudflare's research verifier with the test key.
    ver.add_argument("--domain", default="research-verifier", help=argparse.SUPPRESS)
    ver.add_argument("--identity", default=None, help=argparse.SUPPRESS)
    ver.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON to stdout (strips raw signature material).",
    )

    # ---- register (Phase 3, CLI-04, D-49) ----------------------------------
    reg = sub.add_parser(
        "register",
        help="Register an Identity with the hosted directory (proof-of-key-ownership).",
        description=(
            "Two-step proof-of-key-ownership flow per D-38. "
            "(1) POST /register/challenge → receive nonce. "
            "(2) Sign + POST /register/submit. "
            "Defaults to the production directory at "
            "https://wbauth.silov801.workers.dev. "
            "Exit 0 on success, 1 on rejection."
        ),
    )
    reg.add_argument("--identity", required=True,
                     help="Path to an EXISTING private key PEM (never created here).")
    reg.add_argument(
        "--directory",
        default="https://wbauth.silov801.workers.dev",
        help="Directory base URL (default: production Phase 3 Worker).",
    )
    reg.add_argument("--client-name", default=None, help="Public agent name.")
    reg.add_argument("--purpose", default=None, help="Why this agent exists.")
    reg.add_argument("--client-uri", default=None, help="Public homepage URL.")
    reg.add_argument(
        "--expected-user-agent",
        default=None,
        help="The User-Agent string verifiers should expect from this agent.",
    )

    # ---- serve (Phase 3, CLI-05, D-50) -------------------------------------
    sv = sub.add_parser(
        "serve",
        help="Serve a single JWKS file at the well-known path.",
        description=(
            "Stdlib http.server-based static JWKS host (≤30 LOC). "
            "Serves /.well-known/http-message-signatures-directory/{kid} for "
            "any kid in the supplied JWKS file. Self-hosting alternative to "
            "the hosted directory at https://wbauth.silov801.workers.dev. "
            "NO registration, NO list endpoints — that's what the hosted "
            "directory is for."
        ),
    )
    sv.add_argument(
        "--jwks", required=True,
        help="Path to the JWKS JSON file (from `wbauth keygen --jwks-output`).",
    )
    sv.add_argument("--port", type=int, default=8080, help="TCP port (default: 8080).")
    sv.add_argument("--host", default="127.0.0.1",
                    help="Bind address (default: 127.0.0.1; use 0.0.0.0 to expose).")
    sv.add_argument("--sign-key", action="append", default=[], metavar="PEM",
                    help="Sign directory responses with this key (repeat for "
                         "every key in the JWKS, as the directory draft requires).")
    sv.add_argument("--tls-cert", default=None, help="Serve HTTPS with this certificate.")
    sv.add_argument("--tls-key", default=None, help="Private key for --tls-cert.")

    # ---- rotate -------------------------------------------------------------
    rot = sub.add_parser(
        "rotate",
        help="Rotate the keyring: active.pem → retiring.pem, new active.pem.",
    )
    rot.add_argument("--keyring", required=True, metavar="DIR")
    rot.add_argument("--jwks-output", default=None,
                     help="Write the new JWKS (active + retiring) here.")

    return parser


# ---------- inspect handler (CLI-02, D-24) ----------


def _serialize_policy(policy: SitePolicy, include_raw: bool = True) -> dict:
    """Back-compat wrapper around :meth:`SitePolicy.to_dict`."""
    return policy.to_dict(include_raw=include_raw)


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
    absent: list[str] = []
    real: dict[str, Exception] = {}
    for name, exc in policy.errors.items():
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if isinstance(status, int) and 400 <= status < 500 and status != 429:
            absent.append(f"{name} ({status})")
        else:
            real[name] = exc
    if absent:
        print(f"Not published: {', '.join(absent)}")
    if real:
        print("Errors:")
        for name, exc in real.items():
            first_line = str(exc).splitlines()[0] if str(exc) else ""
            print(f"  - {name}: {type(exc).__name__}: {first_line}")
    else:
        print("Errors:  none")
    print(f"Fetched: {policy.fetched_at.isoformat()}")
    print()
    print("(For full SitePolicy JSON, re-run with --json)")


_VERDICT_COLORS = {"allowed": "32", "restricted": "33", "forbidden": "31"}


def _use_color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _paint(text: str, code: str, color: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if color else text


def _source_rows(policy: SitePolicy) -> list[tuple[str, str, str]]:
    """(source, status, detail) for each of the four policy endpoints."""
    rows: list[tuple[str, str, str]] = []
    labels = {
        "robots": "robots.txt", "ai_txt": "ai.txt", "llms_txt": "llms.txt",
        "signing_directory": "signing directory",
    }
    for key, label in labels.items():
        exc = policy.errors.get(key)
        value = getattr(policy, key)
        if exc is not None:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if isinstance(status_code, int) and 400 <= status_code < 500 and status_code != 429:
                rows.append((label, "absent", f"HTTP {status_code}"))
            else:
                first = str(exc).splitlines()[0] if str(exc) else ""
                rows.append((label, "error", f"{type(exc).__name__}: {first}"[:70]))
        elif value is None:
            rows.append((label, "-", ""))
        elif key == "robots":
            detail = "allows this path" if value.can_fetch_url else "DISALLOWS this path"
            if value.crawl_delay:
                detail += f", crawl-delay {value.crawl_delay:g}s"
            rows.append((label, "found", detail))
        elif key == "ai_txt":
            rows.append((label, "found", f"{len(value.restrictions)} restriction(s), "
                                         f"{len(value.permissions)} permission(s)"))
        elif key == "llms_txt":
            rows.append((label, "found", value.title or "(untitled)"))
        else:
            rows.append((label, "found" if value.present else "invalid",
                         f"{len(value.keys)} key(s)"))
    return rows


def _print_table(policy: SitePolicy) -> None:
    color = _use_color()
    verdict = _paint(policy.verdict.upper(), _VERDICT_COLORS.get(policy.verdict, "0") + ";1",
                     color)
    print(f"{verdict}  {policy.url}")
    print()
    rows = _source_rows(policy)
    w1 = max(len(r[0]) for r in rows)
    w2 = max(len(r[1]) for r in rows)
    status_colors = {"found": "32", "absent": "2", "error": "31", "invalid": "33"}
    print(f"{'SOURCE'.ljust(w1)}  {'STATUS'.ljust(w2)}  DETAIL")
    for src, st, detail in rows:
        st_out = _paint(st.ljust(w2), status_colors.get(st, "0"), color)
        print(f"{src.ljust(w1)}  {st_out}  {detail}")
    print()
    print("Why:")
    for reason in policy.reasons:
        print(f"  - {reason}")
    if policy.partial:
        print(_paint("  (partial: some sources failed; strict policy applied)", "33", color))


def _dispatch_inspect(args: argparse.Namespace) -> int:
    """CLI-02 + D-24 handler.

    Calls ``asyncio.run(inspect(args.url))`` and maps the verdict to an
    exit code. ``ValueError`` from URL parsing → exit 3 with stderr msg;
    any other unexpected exception → exit 3 with stderr msg
    (CLI-06: errors never leak to stdout, even in --json mode, so JSON
    consumers always see a clean parseable document or an empty stdout).
    """
    fmt = getattr(args, "format", None) or ("json" if args.json else "text")
    cache_path = getattr(args, "cache", None)
    if cache_path:
        from .policy import load_cache

        load_cache(os.path.expanduser(cache_path))
    try:
        policy: SitePolicy = asyncio.run(
            inspect(args.url, user_agent=args.user_agent,
                    allow_private=not getattr(args, "no_private", False))
        )
    except ValueError as e:
        # URL parse errors from inspect() itself (e.g., httpx URL parsing).
        print(f"error: invalid URL: {e}", file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001 — last-resort error path
        # Anything else that escaped the inspector's per-endpoint error
        # isolation (network pool exhaustion, asyncio runtime errors, etc.).
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    if cache_path:
        from .policy import save_cache

        try:
            path = os.path.expanduser(cache_path)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            save_cache(path)
        except OSError as e:
            print(f"warning: could not write cache {cache_path}: {e}", file=sys.stderr)
    if fmt == "json":
        print(json.dumps(policy.to_dict(include_raw=getattr(args, "include_raw", False)),
                         default=str))
    elif fmt == "table":
        _print_table(policy)
    else:
        _print_human_summary(policy)
    if _site_unreachable(policy):
        return 3
    return {"allowed": 0, "restricted": 1, "forbidden": 2}.get(policy.verdict, 3)


def _site_unreachable(policy: SitePolicy) -> bool:
    """Every endpoint failed with a transport-level error (no HTTP answer)."""
    import httpx

    names = ("robots", "ai_txt", "llms_txt", "signing_directory")
    return all(
        isinstance(policy.errors.get(n), (httpx.TransportError, httpx.TimeoutException))
        for n in names
    )


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

    if args.identity or args.domain != "research-verifier":
        print(
            "warning: --identity/--domain are deprecated no-ops; the probe always "
            "uses the RFC 9421 test key against Cloudflare's research verifier",
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
    from pathlib import Path

    from .identity import KEYRING_ACTIVE

    out = (str(Path(args.keyring).expanduser() / KEYRING_ACTIVE)
           if getattr(args, "keyring", None) else args.output)
    try:
        # generate(), not load_or_generate(): an existing key is an error,
        # never silently reported as "written".
        identity = Identity.generate(out, signature_agent_url=args.signature_agent_url)
    except FileExistsError:
        print(f"error: key already exists at {out}; refusing to overwrite "
              "(use `wbauth rotate --keyring DIR` to rotate)", file=sys.stderr)
        return 2
    except (PermissionError, TypeError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"Wrote key to {out} (mode 0o600)")
    print(f"kid: {identity.kid}")
    # D-51: optional JWKS dump for self-hosters. Only the public material —
    # `Identity.export_jwks()` returns {kty, crv, kid, x} (never `d`), so
    # this file is safe to publish at /.well-known/... or feed into
    # `wbauth serve` (CLI-05). Pretty-printed (indent=2) so users can `cat` it.
    if getattr(args, "jwks_output", None):
        Path(args.jwks_output).write_text(
            json.dumps(identity.export_jwks(), indent=2)
        )
        print(f"Wrote JWKS to {args.jwks_output}")
    return 0


# ---------- serve handler (CLI-05, D-50) ----------


def _dispatch_serve(args: argparse.Namespace) -> int:
    """CLI-05 + D-50 handler.

    Lazy-imports the server module so `wbauth keygen` startup stays fast
    (matches the lazy-import pattern used by `_dispatch_verify`).

    Exit codes:
      - 0: serve_forever returned cleanly (only happens if the caller injects
        a shutdown — practically unreachable from the CLI surface).
      - 130: Ctrl-C / SIGINT. The outer `main()` also catches KeyboardInterrupt
        and returns 130; this explicit handler is belt-and-suspenders so direct
        callers of `_dispatch_serve` (e.g. unit tests) get the right code too.
    """
    from ._http_server.jwks_server import serve

    try:
        serve(
            args.jwks, args.port,
            host=getattr(args, "host", "127.0.0.1"),
            sign_keys=getattr(args, "sign_key", None) or (),
            tls_cert=getattr(args, "tls_cert", None),
            tls_key=getattr(args, "tls_key", None),
        )
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, TypeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


def _dispatch_rotate(args: argparse.Namespace) -> int:
    placeholder = "https://example.invalid/placeholder"
    try:
        ident = Identity.load_keyring(args.keyring, signature_agent_url=placeholder)
        new = ident.rotate_keyring(args.keyring)
    except (OSError, TypeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"Rotated keyring {args.keyring}")
    print(f"active kid:   {new.kid}")
    print(f"retiring kid: {ident.kid}")
    if args.jwks_output:
        from pathlib import Path

        Path(args.jwks_output).write_text(json.dumps(new.export_jwks(), indent=2))
        print(f"Wrote JWKS to {args.jwks_output}")
    return 0


# ---------- register handler (CLI-04, D-49) ----------


async def _do_register(
    *,
    identity_path: str,
    directory_url: str,
    client_name: str,
    purpose: str | None,
    client_uri: str | None,
    expected_user_agent: str | None,
) -> dict:
    """Two-step proof-of-key-ownership flow per D-38.

    Returns the directory's JSON response on success
    (``{"kid": ..., "directory_url": ...}``).
    Raises ``httpx.HTTPStatusError`` on directory rejection (4xx/5xx) — the
    CLI handler turns that into exit 1 + stderr message.

    L-02 / Pitfall 5: re-uses Phase 1's ``wbauth.signer.sign`` primitive
    verbatim. Do NOT re-implement RFC 9421 inline here; the import path is
    discoverable via ``grep "from .signer import sign" python/src/wbauth/cli.py``
    and the audit guard in 03-02-PLAN.md.

    Module-importable for Plan 03-03's E2E exit script — the task's
    ``files_modified.contains: "_do_register"`` is the contract.
    """
    import datetime
    import json as _json

    import httpx

    from .identity import Identity
    from .normalized_request import NormalizedRequest
    from .signer import sign

    # Compute the canonical Signature-Agent URL upfront. The kid is the RFC 7638
    # thumbprint of the public key — deterministic, no server round-trip needed.
    # Strategy: load_or_generate once with a placeholder URL just to read .kid,
    # then re-load with the canonical URL so the produced signature commits to
    # the right value (T-03-17 mitigation). The second load_or_generate hits the
    # existing-file path; cost is one PEM parse, no fresh keygen.
    from pathlib import Path

    from .identity import _load_keypair

    directory_url = directory_url.rstrip("/")
    path = Path(identity_path).expanduser()
    if not path.exists():
        # Never generate here: a typo would silently register a brand-new key.
        raise FileNotFoundError(f"No key at {path}; create one with `wbauth keygen`")
    pair = _load_keypair(path)  # one PEM parse; kid needs no server round-trip
    canonical_signature_agent = (
        f"{directory_url}/.well-known/http-message-signatures-directory/{pair.kid}"
    )
    identity = Identity(pair, canonical_signature_agent)

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Step 1: POST /register/challenge {kid} → {challenge, expires_at}.
        r1 = await client.post(
            f"{directory_url}/register/challenge",
            json={"kid": identity.kid},
        )
        r1.raise_for_status()
        challenge = r1.json()["challenge"]

        # Step 2: build the SubmitBody and sign the POST itself.
        # Web Bot Auth covered components are @authority + signature-agent
        # (+ content-digest because there's a body) — see signer._components_for.
        # Omit None-valued optional fields. The Worker's zod schema declares
        # client_uri / expected_user_agent / purpose as `.optional()` (NOT
        # `.nullable()`), so emitting explicit JSON `null` triggers a 400
        # invalid_type rejection. Dict comprehension drops keys whose value
        # is None; required keys (kid/challenge/client_name/signature_agent_url/
        # keys) and explicitly-empty `contacts: []` always pass through.
        # (Discovered during Plan 03-03 E2E run — Rule 1 deviation.)
        body = {
            k: v
            for k, v in {
                "kid": identity.kid,
                "challenge": challenge,
                "client_name": client_name,
                "client_uri": client_uri,
                "signature_agent_url": canonical_signature_agent,
                "expected_user_agent": expected_user_agent,
                "contacts": [],
                "purpose": purpose,
                "keys": identity.export_jwks(),
            }.items()
            if v is not None
        }
        body_bytes = _json.dumps(body).encode("utf-8")

        submit_url = f"{directory_url}/register/submit"
        # Phase 1's sign() is the SOURCE OF TRUTH (Pitfall 5).
        # Pre-compute Content-Digest before signing — the signer auto-adds
        # `content-digest` to the covered components for POST+body and would
        # otherwise raise "Covered header field 'content-digest' not found".
        # Helper lives in adapters/_utils.py (RFC 9530 sha-256, structured-fields).
        from .adapters._utils import ensure_content_digest

        req = NormalizedRequest(method="POST", url=submit_url, headers={}, body=body_bytes)
        ensure_content_digest("POST", req.headers, body_bytes)
        sig = sign(
            req, identity,
            created=datetime.datetime.now(datetime.timezone.utc),
        )

        # Forward Content-Digest if the signer added one (it does for POST+body).
        outbound_headers = {
            "content-type": "application/json",
            "Signature": sig.signature,
            "Signature-Input": sig.signature_input,
            "Signature-Agent": sig.signature_agent,
        }
        if "Content-Digest" in req.headers:
            outbound_headers["Content-Digest"] = req.headers["Content-Digest"]

        r2 = await client.post(
            submit_url,
            content=body_bytes,
            headers=outbound_headers,
        )
        r2.raise_for_status()
        return r2.json()


def _dispatch_register(args: argparse.Namespace) -> int:
    """CLI-04 + D-49 handler.

    Returns 0 on successful registration, 1 on rejection. Errors and rejection
    reasons go to stderr (CLI-06); the success line goes to stdout.

    Lazy-imports httpx so `wbauth keygen` startup stays fast (matches the
    pattern used by `_dispatch_verify`).
    """
    import httpx

    # If client_name not supplied, prompt interactively. D-49 specifies "prompts
    # for client_name and purpose (or accepts --client-name/--purpose args)".
    client_name = args.client_name
    if not client_name:
        if not sys.stdin.isatty():
            print("error: --client-name is required when stdin is not a terminal",
                  file=sys.stderr)
            return 1
        client_name = input("client_name: ").strip()
    if not client_name:
        print("error: client_name must not be empty", file=sys.stderr)
        return 1
    try:
        result = asyncio.run(_do_register(
            identity_path=args.identity,
            directory_url=args.directory,
            client_name=client_name,
            purpose=args.purpose,
            client_uri=args.client_uri,
            expected_user_agent=args.expected_user_agent,
        ))
    except httpx.HTTPStatusError as e:
        print(
            f"error: registration rejected: HTTP {e.response.status_code} "
            f"{e.response.text}",
            file=sys.stderr,
        )
        return 1
    except Exception as e:  # noqa: BLE001 — last-resort error path (CLI-06)
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(f"Registered. directory_url: {result['directory_url']}")
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
    if args.cmd == "register":
        return _dispatch_register(args)
    if args.cmd == "serve":
        return _dispatch_serve(args)
    if args.cmd == "rotate":
        return _dispatch_rotate(args)
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
