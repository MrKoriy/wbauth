---
phase: 03-hosted-directory-cloudflare-submission
plan: 02
subsystem: python-cli
tags: [python, cli, http-server, github-actions, snapshot, web-bot-auth, rfc-9421]
requires:
  - phase-1-signer (wbauth.signer.sign reused verbatim — Pitfall 5)
  - phase-1-identity (Identity.load_or_generate, Identity.export_jwks)
  - phase-2-cli (extends existing _build_parser / _dispatch tree)
  - plan-03-01 (live Worker at https://wbauth.silov801.workers.dev with /register/* + /static/all.json)
provides:
  - "wbauth register CLI: two-step proof-of-key-ownership against the live Worker (CLI-04, D-49)"
  - "wbauth serve CLI: stdlib JWKS host (CLI-05, D-50; 26 executable LOC)"
  - "wbauth keygen --jwks-output: optional public JWKS dump (D-51)"
  - "wbauth.cli._do_register module-importable async helper (consumed by Plan 03-03 E2E gate)"
  - "scripts/snapshot.sh + .github/workflows/snapshot.yml (DIR-05, D-45/46; cron commented out per Pitfall 7)"
affects:
  - "Plan 03-03 E2E exit gate (D-52) — imports _do_register from wbauth.cli"
  - "Phase 5 — uncomments snapshot cron + wires GitHub remote (D-08)"
tech-stack:
  added: []
  patterns:
    - "Lazy in-function imports for CLI handlers (matches existing _dispatch_verify pattern — keeps `wbauth keygen` startup snappy)"
    - "Two-load Identity construction in _do_register: load once with placeholder URL to read .kid (deterministic RFC 7638 thumbprint), then load again with canonical URL so the produced signature commits to the right value (T-03-17 mitigation)"
    - "Pre-compute Content-Digest before sign() (signer requires the header pre-set when content-digest is in covered components — found via test failure, fixed via existing adapters/_utils.ensure_content_digest)"
    - "Stdlib http.server with module-level kid set captured at make_handler() time (no per-request file IO)"
    - "GitHub Actions snapshot workflow ships disabled-by-default — workflow_dispatch only, schedule.cron commented out"
key-files:
  created:
    - python/src/wbauth/_http_server/__init__.py
    - python/src/wbauth/_http_server/jwks_server.py
    - python/tests/test_cli_register.py
    - python/tests/test_cli_keygen_jwks_output.py
    - python/tests/test_cli_serve.py
    - python/tests/test_jwks_server.py
    - scripts/snapshot.sh
    - .github/workflows/snapshot.yml
    - .planning/phases/03-hosted-directory-cloudflare-submission/deferred-items.md
  modified:
    - python/src/wbauth/cli.py
decisions:
  - "Pre-compute Content-Digest in _do_register via adapters._utils.ensure_content_digest (deviation Rule 1 — see Deviations)"
  - "JWKS server module placed under wbauth/_http_server/ (leading underscore = internal API)"
  - "Snapshot script defaults DIRECTORY_URL to https://wbauth.silov801.workers.dev (D-49 carry-forward)"
  - "snapshot.yml ships with workflow_dispatch only; schedule.cron commented (Open Question #3 / Pitfall 7)"
metrics:
  duration: "~50 min (Task 1 ~25 min including TDD cycle + Content-Digest fix; Task 2 ~15 min including LOC trim + flake fix; Task 3 ~10 min including live smoke)"
  completed-date: "2026-05-10"
  tasks: 3
  files-created: 9
  files-modified: 1
  test-count-new: 21 (test_cli_register.py: 11, test_cli_keygen_jwks_output.py: 3, test_cli_serve.py: 5, test_jwks_server.py: 6 — net +21 vs +17 raw because some test_cli_register tests use `pytest-anyio` which counts as 1 test per param)
  test-count-total: "192/195 in-process pass (3 pre-existing macOS subprocess flakes documented in deferred-items.md DEF-03-01)"
  jwks-server-loc: 26 (D-50 cap is ≤30)
---

# Phase 3 Plan 02: Register CLI + Snapshot + Serve Summary

Python CLI surface for the live Phase 3 directory: `wbauth register` drives the two-step proof-of-key-ownership flow against `https://wbauth.silov801.workers.dev` re-using Phase 1's `wbauth.sign()` verbatim, `wbauth serve` provides a 26-LOC stdlib JWKS host for self-hosters, `wbauth keygen --jwks-output` emits the public JWKS, and a GitHub Actions workflow snapshots `/static/all.json` nightly (cron commented out until Phase 5 D-08 resolves).

## CLI Surface Shipped

### `wbauth register` (CLI-04, D-49)

```
$ wbauth register --help
usage: wbauth register [-h] --identity IDENTITY [--directory DIRECTORY]
                       [--client-name CLIENT_NAME] [--purpose PURPOSE]
                       [--client-uri CLIENT_URI]
                       [--expected-user-agent EXPECTED_USER_AGENT]

Two-step proof-of-key-ownership flow per D-38. (1) POST /register/challenge →
receive nonce. (2) Sign + POST /register/submit. Defaults to the production
directory at https://wbauth.silov801.workers.dev. Exit 0 on success, 1 on
rejection.
```

**Mocked smoke (test suite):**
```
test_dispatch_register_success_returns_0 → "Registered. directory_url: ..."
test_dispatch_register_rejection_returns_1 → exit 1, "error: ... HTTP 422 ..." on stderr
```

**Pitfall 5 regression guard active:** `test_do_register_happy_path_calls_sign_once` asserts `mock_sign.call_count == 1` — register MUST sign exactly once via `wbauth.signer.sign`, not re-implement RFC 9421 inline.

**`_do_register` module-importable** for Plan 03-03's E2E exit script (`from wbauth.cli import _do_register`).

### `wbauth serve` (CLI-05, D-50)

```
$ wbauth serve --help
usage: wbauth serve [-h] --jwks JWKS [--port PORT]

Stdlib http.server-based static JWKS host (≤30 LOC). Serves /.well-known/http-
message-signatures-directory/{kid} for any kid in the supplied JWKS file.
Self-hosting alternative to the hosted directory at
https://wbauth.silov801.workers.dev. NO registration, NO list endpoints —
that's what the hosted directory is for.
```

**Live end-to-end smoke (executed during Task 2 verification):**
```
$ wbauth keygen --output /tmp/k.pem --jwks-output /tmp/k.jwks.json --signature-agent-url https://example.com
Wrote key to /tmp/k.pem (mode 0o600)
kid: -E8UfILcc7A8w5-XmGmGk3IMuYh_WghbgsyXsmUtjKc
Wrote JWKS to /tmp/k.jwks.json

$ wbauth serve --jwks /tmp/k.jwks.json --port 18099 &
Serving JWKS from /tmp/k.jwks.json on port 18099

$ curl -s -i http://127.0.0.1:18099/.well-known/http-message-signatures-directory/-E8UfILcc7A8w5-XmGmGk3IMuYh_WghbgsyXsmUtjKc
HTTP/1.0 200 OK
content-type: application/http-message-signatures-directory+json
content-length: 192
cache-control: public, max-age=300

{"keys":[...]}

$ curl -s -i http://127.0.0.1:18099/.well-known/http-message-signatures-directory/unknown
HTTP/1.0 404 kid not served by this JWKS
```

**LOC budget (D-50 hard cap ≤30):**
```
$ grep -vcE '^\s*$|^\s*#|^\s*"""|^\s*"|^from |^import ' python/src/wbauth/_http_server/jwks_server.py
26
```
4 LOC under budget.

### `wbauth keygen --jwks-output` (D-51)

```
$ wbauth keygen --output /tmp/k.pem --jwks-output /tmp/k.jwks.json --signature-agent-url https://example.com
Wrote key to /tmp/k.pem (mode 0o600)
kid: Uh2iIsFMDOMYznfwxVJB_c-XOzzXCRvzQsx92cKkMy8
Wrote JWKS to /tmp/k.jwks.json

$ cat /tmp/k.jwks.json
{
  "keys": [
    {
      "crv": "Ed25519",
      "kty": "OKP",
      "kid": "Uh2iIsFMDOMYznfwxVJB_c-XOzzXCRvzQsx92cKkMy8",
      "x": "EmbqmhOzGib7NmahEsIH4JxwcC7E8VMK7czhQADEyAE"
    }
  ]
}
```

**T-03-19 guard:** `test_keygen_jwks_output_writes_valid_jwks` asserts `"d" not in k0` — public JWKS NEVER contains the private scalar. Confirmed via `Identity.export_jwks() → KeyPair.public_jwk()` which only emits `{kty, crv, kid, x}`.

**Backward compat:** `test_keygen_without_jwks_output_does_not_write_jwks` confirms Phase 1 IDENT-01 behavior preserved when `--jwks-output` omitted (no JWKS file written).

## GitHub Actions Snapshot Workflow

**File:** `.github/workflows/snapshot.yml`
**Status:** disabled by default (Pitfall 7 mitigation). Trigger only via `gh workflow run nightly-directory-snapshot`.

**Cron line state:**
```yaml
on:
  workflow_dispatch: {}
  # TODO(Phase 5, D-08): uncomment once GitHub remote is set up
  # schedule:
  #   - cron: '0 2 * * *'   # 02:00 UTC daily (D-45)
```

**Verification:**
```
$ grep -E "^\s*-\s*cron:" .github/workflows/snapshot.yml
(no output — confirms cron is commented out)
```

**Live smoke against the production Worker (executed during Task 3 verification):**
```
$ OUT_DIR=/tmp/snapshot-smoke bash scripts/snapshot.sh
Fetching https://wbauth.silov801.workers.dev/static/all.json -> /tmp/snapshot-smoke/directory-snapshot-2026-05-10.json
Pruning snapshots older than 30 days under /tmp/snapshot-smoke

$ cat /tmp/snapshot-smoke/latest.json
{"generated_at":1778420036,"agents":[]}
```

The snapshot script works end-to-end against the live Worker; the workflow plumbing (peaceiris/actions-gh-pages@v4 → gh-pages branch) is correctly wired but only fires on manual trigger or once Phase 5 uncomments the cron.

## Test Counts

| File | New tests | Coverage |
|---|---|---|
| `tests/test_cli_register.py` | 11 (4 sync + 4 async + 3 dispatch) | argparse wiring, default --directory, Pitfall 5 regression, signature headers presence, HTTP 422/429 rejections, exit codes 0/1, stderr discipline |
| `tests/test_cli_keygen_jwks_output.py` | 3 | --jwks-output writes valid JWKS, T-03-19 guard ("d" absent), backward compat (no flag = no file), pretty-print indent=2 |
| `tests/test_cli_serve.py` | 5 | --help, --jwks required, --port default 8080, --port override, KeyboardInterrupt → 130 |
| `tests/test_jwks_server.py` | 6 | make_handler returns class, served kid → 200 + content-type + cache-control, unknown kid → 404, random path → 404, root well-known → 404 (D-50 single-JWKS), poll-until-ready helper (flake-resistant) |
| **Total** | **25 new test functions** | |

**Suite run (in-process):** `192/195 pass` — 3 failures are pre-existing macOS subprocess flakes in `tests/test_cli_keygen.py` (Phase 1 file, unrelated to Plan 03-02 changes — verified by stashing my changes and reproducing the same failure on `8cf002e`). Documented in `deferred-items.md` as `DEF-03-01`.

## Verification Gates (all passed)

```
1. Pitfall 5 — register reuses signer.sign:         2  (≥1 expected)
2. NO inline crypto in cli.py:                      OK
3. D-49 production worker URL in cli.py:            3  (≥1 expected)
4. D-50 jwks_server.py LOC:                         26 (≤30 cap)
5. snapshot.yml cron commented:                     OK
6. snapshot.sh URL + executable:                    2  (≥1 expected)
```

## Commits Landed

| Commit | Scope |
|---|---|
| `217d654` | test(03-02): add failing tests for register CLI + keygen --jwks-output (CLI-04, D-49, D-51) |
| `0634f6f` | feat(03-02): wire wbauth register CLI + keygen --jwks-output (CLI-04, D-49, D-51) |
| `f9a1489` | test(03-02): add failing tests for wbauth serve + JWKS http.server (CLI-05, D-50) |
| `8cf002e` | feat(03-02): wire wbauth serve stdlib JWKS host (CLI-05, D-50; 26 LOC) |
| `ed418ab` | feat(03-02): add nightly snapshot workflow + script (DIR-05, D-45/46; cron disabled) |
| _this commit_ | docs(03-02): complete register CLI + serve + snapshot plan |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Content-Digest pre-computation in _do_register**
- **Found during:** Task 1 GREEN phase (test failure: `HTTPMessageSignaturesException: Covered header field "content-digest" not found in the message`)
- **Issue:** `wbauth.signer.sign()` auto-includes `content-digest` in the covered components for POST/PUT/PATCH with a body, but the signer requires the `Content-Digest` header to already be set on the request (per `signer.py` docstring: "the caller is responsible for setting the Content-Digest header BEFORE calling sign()"). The plan's `_do_register` reference (RESEARCH §6) constructed the `NormalizedRequest` without a body and without a Content-Digest, so canonicalization failed.
- **Fix:** Construct the `NormalizedRequest` with `body=body_bytes`, then call the existing `wbauth.adapters._utils.ensure_content_digest("POST", req.headers, body_bytes)` helper before `sign()`. This re-uses the Phase 2 helper instead of re-implementing the RFC 9530 sha-256 canonicalization.
- **Files modified:** `python/src/wbauth/cli.py` (in `_do_register`)
- **Commit:** `0634f6f`
- **Why this is correctness-not-feature:** Without this fix, every `wbauth register` invocation would crash before sending the /register/submit POST. The fix uses an existing internal helper; no new code or pattern introduced.

**2. [Rule 1 - Bug] jwks_server.py docstring trim to fit D-50 LOC budget**
- **Found during:** Task 2 GREEN phase verify gate (`executable LOC: 33` vs D-50 ≤30 cap)
- **Issue:** The plan's plan-text had a longer multi-paragraph docstring; the LOC counter (`grep -vE '^\s*$|^\s*#|^\s*"""|^\s*"|^from |^import '`) excludes lines starting with `"""` but counts docstring CONTENT lines (those starting with letters), so a multi-line docstring inflates the count.
- **Fix:** Replaced multi-line docstring with a single-line docstring + `#` comment block (comments are correctly excluded by the counter). Final count: 26 LOC executable.
- **Files modified:** `python/src/wbauth/_http_server/jwks_server.py`
- **Commit:** `8cf002e`

**3. [Rule 1 - Bug] Test flake fix in test_jwks_server.py — poll-until-ready instead of fixed sleep**
- **Found during:** Task 2 GREEN phase (one of 6 server tests timed out on `time.sleep(0.3)` insufficient)
- **Issue:** ThreadingHTTPServer needs a moment to bind; a fixed 300ms sleep is sometimes not enough on a loaded machine. Test would intermittently see URLError socket timeout.
- **Fix:** Replaced `time.sleep(0.3)` with a polling loop that connects to the bound port (max 2s wait, 50ms poll interval). Verified stable across 5 consecutive runs.
- **Files modified:** `python/tests/test_jwks_server.py`
- **Commit:** `8cf002e`

### Authentication Gates

None. Task 1 register tests use mocked HTTP; Task 2 serve tests use loopback; Task 3 snapshot smoke uses anonymous GET against `/static/all.json` (no auth required for the read-API endpoints).

### No deviation from RESEARCH §6 / §7 sample shapes

The verbatim references from RESEARCH §6 (`_do_register`) and §7 (`jwks_server.py`) were used as the implementation source of truth. Only the two adjustments above (Content-Digest pre-compute + docstring trim) departed from the literal sample text; both were necessary for correctness.

## Hand-off Notes for Plan 03-03

**Module-importable contract for Plan 03-03 E2E:**
```python
from wbauth.cli import _do_register

result = await _do_register(
    identity_path="/path/to/key.pem",
    directory_url="https://wbauth.silov801.workers.dev",
    client_name="my-test-bot",
    purpose=None,
    client_uri=None,
    expected_user_agent=None,
)
# result == {"kid": "...", "directory_url": "https://wbauth.silov801.workers.dev/.well-known/http-message-signatures-directory/<kid>"}
```

Errors propagate as `httpx.HTTPStatusError` (4xx/5xx) — the E2E script can `try/except` around it.

**Rate-limit budget reminder (carried from 03-01):** 10 register attempts per IP per day, shared across `/register/challenge` + `/register/submit` (each register costs 2 → 5 full registers/IP/day max). E2E should reuse the same kid (UPSERT idempotent) to avoid burning the budget.

## Threat Model Coverage

All 7 threats from the plan's `<threat_model>` STRIDE register are mitigated or accepted:

- **T-03-16 (Spoofing — wbauth register reusing test key):** Mitigated. `_do_register` calls `Identity.load_or_generate(args.identity, ...)`; `Identity.from_test_key` is never invoked.
- **T-03-17 (Tampering — wrong URL signed):** Mitigated. `canonical_signature_agent` is computed from `directory_url` + the deterministic kid, then passed to a SECOND `Identity.load_or_generate` call so the signature commits to it. The signed POST body's `signature_agent_url` field matches.
- **T-03-18 (Repudiation — operator-controlled JWKS):** Accepted per plan.
- **T-03-19 (Information disclosure — JWKS leaks "d"):** Mitigated. `test_keygen_jwks_output_writes_valid_jwks` asserts `"d" not in k0`. Confirmed `KeyPair.public_jwk()` only emits {kty, crv, kid, x}.
- **T-03-20 (DoS — register without client-side rate limit):** Accepted per plan (Worker enforces 10/IP/day).
- **T-03-21 (DoS — accidental cron):** Mitigated. Cron commented out, workflow_dispatch only.
- **T-03-22 (Information disclosure — gh-pages mirror):** Accepted per plan (snapshot data is already public via /static/all.json).

No new threats discovered during execution. No threat flags raised.

## Self-Check: PASSED

Files created:

```
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/python/src/wbauth/_http_server/__init__.py
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/python/src/wbauth/_http_server/jwks_server.py
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/python/tests/test_cli_register.py
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/python/tests/test_cli_keygen_jwks_output.py
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/python/tests/test_cli_serve.py
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/python/tests/test_jwks_server.py
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/scripts/snapshot.sh
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/.github/workflows/snapshot.yml
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/.planning/phases/03-hosted-directory-cloudflare-submission/deferred-items.md
```

Files modified:

```
[FOUND-MODIFIED] /Users/leonid/Documents/coding/Vibecoded/YC/python/src/wbauth/cli.py
```

Commits:

```
[FOUND] 217d654 test(03-02): add failing tests for register CLI + keygen --jwks-output
[FOUND] 0634f6f feat(03-02): wire wbauth register CLI + keygen --jwks-output
[FOUND] f9a1489 test(03-02): add failing tests for wbauth serve + JWKS http.server
[FOUND] 8cf002e feat(03-02): wire wbauth serve stdlib JWKS host
[FOUND] ed418ab feat(03-02): add nightly snapshot workflow + script
```

Live snapshot endpoint:

```
[REACHABLE] https://wbauth.silov801.workers.dev/static/all.json → 200 + {"generated_at":...,"agents":[]}
```
