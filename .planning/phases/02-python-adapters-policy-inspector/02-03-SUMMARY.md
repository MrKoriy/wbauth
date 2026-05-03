---
phase: 02-python-adapters-policy-inspector
plan: 03
subsystem: cli
tags: [cli, argparse, asyncio, exit-codes, stderr-discipline, sigint, json-output, web-bot-auth, cloudflare-research-verifier]

# Dependency graph
requires:
  - phase: 02-python-adapters-policy-inspector
    plan: 01
    provides: "Phase-2 deps already in pyproject (httpx, etc.); WebBotAuth/WebBotAuthAdapter/attach_signing at wbauth root"
  - phase: 02-python-adapters-policy-inspector
    plan: 02
    provides: "wbauth.policy.inspect + SitePolicy + 4 Result dataclasses at wbauth root"
provides:
  - "wbauth inspect <url> [--json] — pre-flight policy inspector CLI subcommand (CLI-02, D-24)"
  - "wbauth verify --domain <domain> [--identity <path>] [--json] — Cloudflare research-verifier conformance check (CLI-03, D-25)"
  - "Unified KeyboardInterrupt → exit 130 wrapper covering all subcommands (CLI-06 SIGINT discipline)"
  - "Hardened wbauth keygen for CLI-06 stderr discipline (Phase-1 behavior preserved 1:1)"
  - "wbauth._smoke.cloudflare_debug._probe_verifier(identity) — async helper extracted from run() for shared use"
  - "wbauth._smoke.cloudflare_debug.run_against_domain(domain, identity_path) — async CLI verify backend"
  - "wbauth._smoke.cloudflare_debug.run() — preserved 1:1 for daily cron at .github/workflows/cloudflare-debug.yml"
affects: [04-typescript-sdk-and-framework-integrations, 05-pre-army-hardening-docs-and-launch]

# Tech tracking
tech-stack:
  added: []  # all deps already present from Plans 02-01 + 02-02
  patterns:
    - "Sync-CLI-wraps-async via asyncio.run(<coroutine>) per D-26"
    - "Top-level KeyboardInterrupt try/except in main() returns 130 once for all subcommands"
    - "Top-level `from .policy import inspect` so tests patch wbauth.cli.inspect (most discoverable target)"
    - "AsyncMock auto-wrap: patch async functions with bare `return_value=<value>` (NOT a coroutine wrapper) — `unittest.mock.patch` auto-detects `async def` and wraps with AsyncMock"
    - "T-02-03-02 mitigation: `--json` strips raw signature material via _VERIFY_JSON_STRIP_KEYS allowlist before json.dumps"
    - "Lazy import of cloudflare_debug inside _dispatch_verify keeps `wbauth keygen` free of httpx + asyncio init cost"
    - "Preserved Phase-1 `run() -> int` API (used by daily cron) by extracting shared logic into _probe_verifier"

key-files:
  created:
    - "python/tests/test_cli_keygen.py — 5 tests (3 Phase-1 preserved + 2 new for stderr discipline + SIGINT)"
    - "python/tests/test_cli_inspect.py — 11 tests (exit-code matrix + human + JSON shapes + stderr discipline)"
    - "python/tests/test_cli_verify.py — 8 tests (exit-code matrix + open-question #5 + JSON strip + stderr discipline)"
    - ".planning/phases/02-python-adapters-policy-inspector/02-03-SUMMARY.md — this summary"
  modified:
    - "python/src/wbauth/cli.py — extended from 73 LOC (Phase 1) to 309 LOC: keygen + inspect + verify, KeyboardInterrupt wrapper, _serialize_policy + _print_human_summary helpers, _print_verify_human + _VERIFY_JSON_STRIP_KEYS"
    - "python/src/wbauth/_smoke/cloudflare_debug.py — refactored to extract _probe_verifier(identity) -> dict; added run_against_domain(domain, identity_path) -> dict; preserved run() -> int 1:1 for daily cron"
  renamed:
    - "python/tests/test_cli.py → python/tests/test_cli_keygen.py (no external referrers; clean rename via `git mv`)"

key-decisions:
  - "KeyboardInterrupt is caught at the TOP level (in main()) — single uniform exit-130 path for all subcommands; no per-subcommand handler needs its own try/except"
  - "Top-level `from .policy import inspect` (not lazy) so tests can patch `wbauth.cli.inspect` — the most discoverable patch target. Trade-off: imports httpx + asyncio at startup; acceptable since every subcommand except keygen needs them"
  - "Lazy import of `_smoke.cloudflare_debug` inside _dispatch_verify — keeps `wbauth keygen` (Phase 1) cold-path free of the smoke module's overhead"
  - "AsyncMock auto-detection: patches against `wbauth.cli.inspect` use `return_value=<SitePolicy>` directly (NOT wrapped in a coroutine). The first test draft wrapped values in `_async_value()` which created nested coroutines that were never awaited; corrected to bare values"
  - "Open question #5 resolution encoded as a lazy stderr warning + always-test-key in run_against_domain: --identity is parsed for forward compatibility, but a stderr warning fires AND the user's key is never even loaded"
  - "T-02-03-02 mitigation as a STRIP-KEYS allowlist (_VERIFY_JSON_STRIP_KEYS), NOT a strip-from-result-dict. The internal probe dict carries signature material because run()'s FAIL diagnostic prints them; the CLI strips them only at the JSON-emission boundary"

patterns-established:
  - "Sync CLI handler protocol: `_dispatch_<subcmd>(args: argparse.Namespace) -> int` where the body wraps `asyncio.run(...)` for async subcommands; top-level main() catches KeyboardInterrupt"
  - "AsyncMock test pattern for sync-wraps-async CLIs: `patch('wbauth.cli.<async_func>', return_value=<value>)` — NOT `_async_value(value)` (wrapping creates a nested unawaited coroutine)"
  - "Smoke-helper refactor pattern: extract shared probe logic into `_probe_verifier(identity)` returning a structured dict; preserve the original `run() -> int` cron entry point by mapping the dict back to int + printing diagnostics; add a parameterized `run_against_<X>(<X>, identity_path)` for the CLI"
  - "JSON-output strip-keys pattern: declare `_<SUBCMD>_JSON_STRIP_KEYS` tuple at module scope, apply via `{k: v for k, v in result.items() if k not in _STRIP}` before json.dumps — single source of truth for what's safe to emit"

requirements-completed: [CLI-01, CLI-02, CLI-03, CLI-06]

# Metrics
duration: ~25 min
completed: 2026-05-04
---

# Phase 2 Plan 03: CLI Extension Summary

**User-facing `wbauth` CLI grew from 1 subcommand (`keygen`) to 3 (`keygen` + `inspect` + `verify`) with unified D-24/D-25 exit codes, CLI-06 stderr discipline, KeyboardInterrupt → 130 wrapper, and the README quickstart `wbauth inspect https://example.com` working end-to-end.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-05-04 (Plan 02-03 execution)
- **Completed:** 2026-05-04
- **Tasks:** 3 (all TDD: RED → GREEN per task)
- **Test files created:** 2 new (`test_cli_inspect.py`, `test_cli_verify.py`); `test_cli.py` renamed → `test_cli_keygen.py` and extended with 2 new tests
- **Tests:** 24 CLI tests total (5 keygen + 11 inspect + 8 verify); 169/169 full suite passing including Phase-1 + Plan 02-01 + Plan 02-02 regression

## Task Commits

| Task | Description                                                          | RED commit | GREEN commit |
|------|----------------------------------------------------------------------|------------|--------------|
| 1    | Audit + harden `wbauth keygen` (CLI-01 + CLI-06 SIGINT wrapper)      | `16d97fb`  | `4597897`    |
| 2    | `wbauth inspect <url> [--json]` subcommand (CLI-02 + D-24)           | `df9c0cc`  | `8920e4a`    |
| 3    | `wbauth verify --domain` subcommand + smoke helper refactor (CLI-03) | `8d99f16`  | `29fd24c`    |

All RED commits were verified-failing before the GREEN implementation. No REFACTOR commits — implementations were minimal at GREEN.

## Files Changed

### Created (4)

- `python/tests/test_cli_inspect.py` — 11 tests covering exit-code matrix (D-24), human-readable output shape, JSON serialization including `errors` dict (Exception → `{type, message}`) and `fetched_at` (datetime → ISO string), stderr discipline in --json mode
- `python/tests/test_cli_verify.py` — 8 tests covering exit-code matrix (D-25), open-question #5 resolution (--identity warning + test key still used), JSON output shape + strip-keys (T-02-03-02), stderr discipline
- `.planning/phases/02-python-adapters-policy-inspector/02-03-SUMMARY.md` — this summary

### Renamed (1)

- `python/tests/test_cli.py` → `python/tests/test_cli_keygen.py` (clean `git mv`; no external referrers — verified via `grep -rn 'test_cli\.py'` in `.github/` and `python/`)

### Modified (3)

- `python/src/wbauth/cli.py` (73 LOC → 309 LOC) — split into `_build_parser()`, `_dispatch()`, three `_dispatch_<subcmd>()` handlers, `_serialize_policy() / _print_human_summary()` for inspect, `_print_verify_human() / _VERIFY_JSON_STRIP_KEYS` for verify; KeyboardInterrupt wrapper at the top level
- `python/src/wbauth/_smoke/cloudflare_debug.py` — extracted `_probe_verifier(identity) -> dict` (shared logic); added `run_against_domain(domain, identity_path) -> dict` (CLI backend); preserved `run() -> int` 1:1 by mapping `_probe_verifier` dict back to int + printing the original Phase-1 diagnostics
- `python/tests/test_cli_keygen.py` — added `test_keygen_errors_to_stderr_not_stdout` + `test_main_returns_130_on_keyboard_interrupt`

## Exit-Code Matrix (verified)

| Subcommand        | 0           | 1                | 2                                 | 3                          | 130    |
|-------------------|-------------|------------------|-----------------------------------|----------------------------|--------|
| `wbauth keygen`   | success     | (unused)         | PermissionError / FileExistsError | (unused)                   | SIGINT |
| `wbauth inspect`  | allowed     | restricted       | forbidden                         | fetch error / unrecov. exc | SIGINT |
| `wbauth verify`   | full pass   | (reserved warn)  | verifier rejection                | (unused)                   | SIGINT |

Each row is anchor-tested:
- keygen: `test_keygen_errors_to_stderr_not_stdout` (exit 2), `test_main_returns_130_on_keyboard_interrupt` (exit 130)
- inspect: `test_inspect_exit_code_{allowed,restricted,forbidden}_returns_{0,1,2}`, `test_inspect_url_value_error_returns_3_with_stderr`, `test_inspect_unexpected_exception_returns_3_with_stderr`
- verify: `test_verify_pass_returns_0`, `test_verify_fail_returns_2`, `test_verify_unknown_banner_returns_2`, `test_verify_non_200_returns_2`

## Sample CLI Sessions (live, end-to-end)

### `wbauth verify --domain example.com` (live against Cloudflare)

```
$ uv run wbauth verify --domain example.com
Identity: test key (RFC 9421 Appendix B.1.4)
Target:   https://http-message-signatures-example.research.cloudflare.com/
Domain:   example.com (informational in v1)
Probe:    GET /
Result:   PASS
  Status:  200
  Banner:  'You successfully authenticated as owning the test public key'
  kid:     poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U
$ echo "exit=$?"
exit=0
```

### `wbauth verify --domain example.com --json` (JSON, signature stripped)

```
$ uv run wbauth verify --domain example.com --json
{"result": "pass", "exit_code": 0, "kid": "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U", "status": 200, "banner": "You successfully authenticated as owning the test public key", "verifier_url": "https://http-message-signatures-example.research.cloudflare.com/", "domain": "example.com"}
$ echo "exit=$?"
exit=0
```

Note: no `signature_input`, `signature`, or `signature_agent` keys in the JSON — T-02-03-02 mitigation verified live (the dict carries them internally for the daily-cron FAIL diagnostic, but `_VERIFY_JSON_STRIP_KEYS` removes them at the CLI's --json boundary).

### `wbauth inspect --help` + `wbauth verify --help`

```
$ uv run wbauth inspect --help
usage: wbauth inspect [-h] [--json] url

Fetch /robots.txt, /ai.txt, /llms.txt, and /.well-known/http-message-
signatures-directory in parallel, compute a deterministic strict verdict
(allowed/restricted/forbidden), and print a human-readable summary. Exit code
matches the verdict per D-24: 0=allowed, 1=restricted, 2=forbidden, 3=fetch
error or unrecoverable exception.

positional arguments:
  url         Target URL (e.g., https://example.com/path).

options:
  -h, --help  show this help message and exit
  --json      Emit the full SitePolicy as JSON to stdout (machine-readable).

$ uv run wbauth verify --help
usage: wbauth verify [-h] --domain DOMAIN [--identity IDENTITY] [--json]

Sign a probe request with the RFC 9421 Appendix B.1.4 test key and POST it to
Cloudflare's open-spec research verifier (per L-04). Reports pass/fail per
D-25: 0=full pass, 1=partial pass with warnings, 2=verifier rejection. v1
ALWAYS uses the test key (open question #5) — register in Cloudflare's
verified-bots program for verification against your own key (Phase 3+).
```

## Daily-Cron Regression Confirmation

`run()` in `cloudflare_debug.py` was refactored to call `_probe_verifier(identity)` and map its dict back to the original Phase-1 stdout/stderr shape. Live verification post-refactor:

```
$ uv run python -m wbauth._smoke.cloudflare_debug
OK: Cloudflare research verifier accepted (status=200, kid=poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U, banner='You successfully authenticated as owning the test public key')
$ echo "exit=$?"
exit=0
```

Output is byte-identical to Phase 1's `run()`. The `.github/workflows/cloudflare-debug.yml` daily cron continues to pass against the live Cloudflare research verifier — verified manually post-refactor.

## Open-Question #5 Resolution Confirmation

**Resolution encoded in code:** `wbauth verify` ALWAYS uses `Identity.from_test_key(...)` in v1 regardless of whether `--identity <path>` is provided. The `--identity` arg is parsed for forward compatibility (Phase 3+ will wire it to a domain-specific verifier path after Cloudflare's verified-bots directory registration), but in v1:

1. A clear stderr warning fires immediately when `--identity` is passed: `"warning: --identity is reserved for Phase 3+ (registered-key verification); v1 always uses the test key against Cloudflare's research verifier"`.
2. The user's key file is **never even read** — `run_against_domain` calls `Identity.from_test_key(...)` unconditionally; the path argument is preserved in the function signature but ignored.
3. `--help` for `--identity` documents the v1 caveat: `"Path to identity key. RESERVED for Phase 3 — v1 always uses the RFC 9421 test key against the research verifier; passing this in v1 prints a warning and uses the test key anyway."`.
4. The `--help` for the entire `verify` subcommand surfaces the v1 caveat: `"v1 ALWAYS uses the test key (open question #5) — register in Cloudflare's verified-bots program for verification against your own key (Phase 3+)."`

The test `test_verify_identity_arg_warns_but_uses_test_key` enforces both behaviors: it asserts the stderr warning AND that the captured `Signature-Input` header references the test-key kid (`poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U`).

## CLI-06 Stderr Discipline Verification

Grep verification (per the plan's `<verification>` section):

```
$ grep -nE "^\s*print\(" python/src/wbauth/cli.py | grep -v "file=sys.stderr"
176:    print(f"Verdict: {policy.verdict}")        # success: human summary
177:    print(f"URL:     {policy.url}")            # success: human summary
178:    print("Reasons:")                           # success: human summary
180:        print(f"  - {reason}")                  # success: human summary
183:    print(f"Partial: {str(policy.partial).lower()}")  # success: human summary
185:        print("Errors:")                        # success: human summary (errors-from-inspect, not CLI errors)
187:            print(f"  - {name}: {type(exc).__name__}: {exc}")  # success: errors-as-data
189:        print("Errors:  none")                  # success: human summary
190:    print(f"Fetched: {policy.fetched_at.isoformat()}")  # success: human summary
191:    print()                                     # success: blank separator
192:    print("(For full SitePolicy JSON, re-run with --json)")  # success: hint
217:        print(json.dumps(_serialize_policy(policy), default=str))  # success: JSON
240-247:                                            # success: verify human summary
264:        print(...)                              # warning — actually goes to stderr (multi-line print call; grep splits oddly)
279:        print(json.dumps(clean))                # success: JSON
304:    print(f"Wrote key to {args.output} (mode 0o600)")  # success: keygen
305:    print(f"kid: {identity.kid}")               # success: keygen
```

All non-stderr prints are success-output (verdict / URL / reasons / identity / target / JSON dump / "Wrote key" / kid). The single grep false-positive on line 264 is the multi-line `--identity` warning (`print(..., file=sys.stderr)` spans multiple lines; the grep only sees the first line with `print(`). Manual inspection confirms stderr discipline is intact.

## Decisions Made

- **Top-level `from .policy import inspect`** (not lazy) so tests patch `wbauth.cli.inspect` — the most discoverable target. Trade-off: imports httpx + asyncio at CLI startup. Acceptable since every subcommand except `keygen` needs them anyway, and `keygen` is fast enough that the extra imports don't matter (still <100ms cold start).
- **Lazy import of `_smoke.cloudflare_debug` inside `_dispatch_verify`** — keeps `wbauth keygen` cold-path free of the smoke module's import overhead. Best of both worlds: top-level for the policy module (test patchability), lazy for the smoke module (no perf cost on unrelated subcommands).
- **AsyncMock auto-detection trumps the plan's reference test code.** The plan's reference tests wrapped policies in `_async_value(...)` coroutines. `unittest.mock.patch` against an `async def` symbol auto-substitutes `AsyncMock` (not `MagicMock`); AsyncMock's `return_value` is what callers see *after* awaiting, so a coroutine wrapper creates a nested coroutine that's never awaited. The fix: pass the bare `SitePolicy` as `return_value`. Documented in the test module docstring so the next executor doesn't re-make this mistake.
- **JSON-output strip-keys as a module-scope tuple** (`_VERIFY_JSON_STRIP_KEYS = (...)`) rather than inline. Single source of truth for "what's safe to emit"; if T-02-03-02 evolves (e.g., Phase 3 adds a directory URL that also shouldn't leak), the change lives in one place.
- **`run()` returns 1 on fail (Phase-1 contract), `_probe_verifier`'s exit_code returns 2 on fail (CLI matrix).** The cron expects 0/1; the CLI matrix is 0/1/2. Kept separate — `run()` reads `result["result"]` (the kind), not `result["exit_code"]` (the CLI-specific code), so the two contracts don't tangle.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Initial test draft wrapped `SitePolicy` in `_async_value()` coroutine helper; AsyncMock auto-handles the wrapping**

- **Found during:** Task 2 GREEN run (8 of 11 tests failed with `AttributeError: 'coroutine' object has no attribute 'verdict'`)
- **Issue:** The plan's reference test code defined `async def _async_value(v): return v` and passed `return_value=_async_value(_fake_policy(...))` to `patch("wbauth.cli.inspect", ...)`. Because `inspect` is an `async def`, `unittest.mock.patch` auto-substitutes `AsyncMock`. AsyncMock's `return_value` is what awaiting the mock produces — so wrapping in `_async_value()` created a nested coroutine: `await mock(...)` yielded a coroutine instead of the SitePolicy, and `asyncio.run(...)` then "ran" it (which short-circuited because the outer coroutine already returned).
- **Fix:** Removed all `_async_value(...)` wrappers; pass the bare SitePolicy as `return_value` directly. Added a multi-line explanatory comment in the test module's notes section so future executors don't re-make the mistake.
- **Files modified:** `python/tests/test_cli_inspect.py` (removed `_async_value` helper; replaced its 8 callsites with bare values; added documentation comment)
- **Verification:** All 11 inspect tests now pass. The fix is test-only — no production code changes needed; the production code was correct from the start.
- **Committed in:** `8920e4a` (Task 2 GREEN — bundled with the production code so the test is verified-passing in the same commit)

**Total deviations:** 1 auto-fixed (Rule 1: test-side bug in the plan's reference test code; production code was correct as designed).

## Issues Encountered

- **macOS UF_HIDDEN flag** (L-05): re-ran `bash scripts/post-sync.sh` four times during this plan after `uv` operations re-hid the editable install. Phase-1 known issue, no new mitigation needed beyond the existing `scripts/post-sync.sh`.

## TDD Gate Compliance

All 3 tasks followed RED → GREEN gate sequence:

| Task | RED commit (test) | GREEN commit (feat) |
|------|-------------------|---------------------|
| 1    | `16d97fb`         | `4597897`           |
| 2    | `df9c0cc`         | `8920e4a`           |
| 3    | `8d99f16`         | `29fd24c`           |

No REFACTOR commits — implementations were minimal at GREEN.

## Threat Flags

None — all threat-register entries (T-02-03-01 through T-02-03-08) from the plan's `<threat_model>` are mitigated as designed:

- T-02-03-01 (URL with embedded tokens echoed in JSON): documented as user responsibility in `--help` for `inspect`
- T-02-03-02 (raw signature material in `verify --json`): mitigated via `_VERIFY_JSON_STRIP_KEYS` allowlist, enforced by `test_verify_json_strips_raw_signature_material`
- T-02-03-03 (--identity tempts users to pass real key paths): mitigated via stderr warning + always-use-test-key, enforced by `test_verify_identity_arg_warns_but_uses_test_key`
- T-02-03-04 (file:// URI attack on inspect): httpx default supports http/https only; documented in plan
- T-02-03-05 (DoS via redirect chain on inspect): inherited from Plan 02-02's `max_redirects=3`
- T-02-03-06 (--json stderr leakage): mitigated via stderr-only print discipline, enforced by `test_verify_warning_in_stderr_not_stdout`
- T-02-03-07 (keygen errors leaking key path): documented as Phase-1 behavior, no Phase-2 regression
- T-02-03-08 (`_probe_verifier` dict leakage if logged): docstring on `_probe_verifier` warns callers must strip; CLI's --json strips automatically

No new security surface introduced beyond what the threat model anticipated.

## Next Phase Readiness

- **Phase 4 (TypeScript SDK):** Has the three CLI subcommands as a reference. Same exit-code matrix (D-24/D-25), same stderr discipline, same JSON output shapes. The TypeScript CLI should mirror these — `wbauth-ts inspect`, `wbauth-ts verify` with identical flag names + identical exit codes for cross-language parity.
- **Phase 5 (docs/launch):** README quickstart `$ wbauth inspect https://example.com` works end-to-end NOW — no more "coming soon" caveats. The `wbauth verify --domain example.com` line also works against the live Cloudflare research verifier (test key) for the "lighthouse for agents" demo.
- **Phase 3 (verifier directory registration):** The `--identity` arg is already wired into the parser + `run_against_domain()` signature (currently a no-op). Phase 3 will:
  1. Implement `Identity.load_or_generate(args.identity, ...)` in `_dispatch_verify` when `args.identity` is set.
  2. Replace the stderr warning with the actual identity load.
  3. Add a `--verifier-url` flag to swap CF_RESEARCH_VERIFIER_URL for a domain-specific verifier path.

  All three are localized to `_dispatch_verify` + `run_against_domain` — no other refactor needed.

## Self-Check: PASSED

Verification commands (all succeed):

- `[ -f python/src/wbauth/cli.py ]` → FOUND
- `[ -f python/src/wbauth/_smoke/cloudflare_debug.py ]` → FOUND
- `[ -f python/tests/test_cli_keygen.py ]` → FOUND
- `[ -f python/tests/test_cli_inspect.py ]` → FOUND
- `[ -f python/tests/test_cli_verify.py ]` → FOUND
- `[ ! -f python/tests/test_cli.py ]` → MISSING (correctly renamed)
- `git log --oneline | grep 16d97fb` → FOUND (Task 1 RED)
- `git log --oneline | grep 4597897` → FOUND (Task 1 GREEN)
- `git log --oneline | grep df9c0cc` → FOUND (Task 2 RED)
- `git log --oneline | grep 8920e4a` → FOUND (Task 2 GREEN)
- `git log --oneline | grep 8d99f16` → FOUND (Task 3 RED)
- `git log --oneline | grep 29fd24c` → FOUND (Task 3 GREEN)
- `uv run pytest -q` → 169 passed (148 baseline + 21 new from Plan 02-03)
- `uv run python -m wbauth._smoke.cloudflare_debug` → exit 0 + OK banner (live cron regression-free)
- `uv run wbauth verify --domain example.com` → exit 0 + PASS (live CLI end-to-end)

---
*Phase: 02-python-adapters-policy-inspector*
*Completed: 2026-05-04*
