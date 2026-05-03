---
phase: 02-python-adapters-policy-inspector
plan: 02
subsystem: policy
tags: [policy-inspector, robots-txt, ai-txt, llms-txt, signing-directory, asyncio, httpx, protego, cachetools, strict-verdict]

# Dependency graph
requires:
  - phase: 02-python-adapters-policy-inspector
    plan: 01
    provides: "Phase-2 deps already in pyproject (protego, cachetools, httpx, pytest-httpx); WebBotAuth/WebBotAuthAdapter/attach_signing already at wbauth root"
provides:
  - "wbauth.inspect — async public entry point: await inspect(url) -> SitePolicy"
  - "wbauth.SitePolicy — frozen dataclass envelope per D-17 (url, robots, ai_txt, llms_txt, signing_directory, verdict, reasons, partial, errors, fetched_at)"
  - "wbauth.RobotsResult / AiTxtResult / LlmsTxtResult / SigningDirectoryResult — per-endpoint frozen dataclasses"
  - "wbauth.policy.parsers.{parse_robots, parse_ai_txt, parse_llms_txt, parse_signing_directory} — pure parsers, no I/O"
  - "wbauth.policy.verdict.compute_verdict — pure function implementing the 16-row strict verdict rule table"
  - "wbauth.policy.cache.PolicyCache — per-(host, endpoint) LRU cache with origin Cache-Control honoring (no-store / no-cache / private / max-age=0 → skip)"
  - "wbauth.policy.errors.{PolicyError, RobotsParseError, FetchError, VerdictError} — exception taxonomy"
  - "12-file fixture corpus under python/tests/fixtures/policy/ exercising every verdict-engine branch"
affects: [02-03-cli, 04-typescript-sdk-and-framework-integrations, 05-pre-army-hardening-docs-and-launch]

# Tech tracking
tech-stack:
  added: []  # all deps were frontloaded in Plan 02-01; no new deps in 02-02
  patterns:
    - "Module-level PolicyCache singleton (D-23) with leading-underscore _reset_cache_for_tests test seam"
    - "asyncio.gather(*[wait_for(c, 3.0) for c in coros], return_exceptions=True) for per-task isolation (POLICY-02 + Pitfall 4)"
    - "Inspector treats HTTPStatusError(404) as 'absent' (neutral) — only timeouts / 5xx / parse errors / network errors count toward partial"
    - "Per-endpoint TTL approximation via one cachetools.TTLCache bucket per endpoint (Assumption A7)"
    - "Defensive 1 MB body cap in ai.txt + llms.txt parsers (T-02-02-02 DoS bound)"
    - "Pitfall 1 detection: HTML body OR text/html content-type → RobotsParseError → forbidden verdict"

key-files:
  created:
    - "python/src/wbauth/policy/__init__.py — re-exports inspect + 5 dataclasses + errors module"
    - "python/src/wbauth/policy/policy.py — SitePolicy + RobotsResult/AiTxtResult/LlmsTxtResult(+Section/Link)/SigningDirectoryResult frozen dataclasses (D-17, D-21)"
    - "python/src/wbauth/policy/errors.py — PolicyError base + RobotsParseError + FetchError + VerdictError (D-31)"
    - "python/src/wbauth/policy/inspector.py — async inspect(url) orchestrator + module-level cache singleton + _reset_cache_for_tests"
    - "python/src/wbauth/policy/verdict.py — pure compute_verdict implementing the 16-row strict rule table"
    - "python/src/wbauth/policy/cache.py — PolicyCache + _parse_cache_control helper (Pitfall 5)"
    - "python/src/wbauth/policy/parsers/__init__.py — re-exports four parser functions"
    - "python/src/wbauth/policy/parsers/robots.py — protego wrapper with HTML-200 detection (Pitfall 1)"
    - "python/src/wbauth/policy/parsers/ai_txt.py — ai.txt v1.1.1 line-based parser, content_types={} per A6"
    - "python/src/wbauth/policy/parsers/llms_txt.py — llmstxt.org H1+blockquote+H2+link-list parser, enforcement='voluntary'"
    - "python/src/wbauth/policy/parsers/signing_directory.py — lightweight JSON parse, no JWK validation (Pitfall 3)"
    - "python/tests/fixtures/policy/robots/{allow,disallow,html_200,malformed,empty}.txt"
    - "python/tests/fixtures/policy/ai_txt/{minimal,with_restrictions,malformed}.txt"
    - "python/tests/fixtures/policy/llms_txt/{minimal,full,empty}.txt"
    - "python/tests/fixtures/policy/signing_directory/{present,malformed}.json"
    - "python/tests/test_policy_parsers_robots.py — 8 tests"
    - "python/tests/test_policy_parsers_ai_txt.py — 5 tests"
    - "python/tests/test_policy_parsers_llms_txt.py — 5 tests"
    - "python/tests/test_policy_parsers_signing_directory.py — 6 tests"
    - "python/tests/test_policy_verdict.py — 15 tests covering all rule-table branches + 6 anchor cases"
    - "python/tests/test_policy_cache.py — 22 tests including parametrized _parse_cache_control sweep"
    - "python/tests/test_policy_inspector.py — 9 tests including Pitfall 1 + POLICY-08 + cache anchor"
  modified:
    - "python/src/wbauth/__init__.py — APPEND-only edit re-exporting inspect + SitePolicy + 4 Result types alongside Plan 02-01 adapter exports"

key-decisions:
  - "partial=True is computed from non-404 errors only — 404 on ai.txt/llms.txt/signing-directory is 'absent' (neutral) and 404 on robots.txt is allow-leaning per RFC 9309. Treating 404s as partial would silently downgrade every well-behaved minimal site to 'restricted' via the D-18 tie-break, defeating the purpose of the strict-but-fair verdict."
  - "Module-level PolicyCache singleton in inspector.py persists across inspect() calls within a single process (D-23). _reset_cache_for_tests is exported as a leading-underscore test-only seam — autouse pytest fixture clears between tests to keep cases independent."
  - "Inspector parser exceptions (RobotsParseError) land in errors[endpoint] without re-raising so the verdict engine can handle them deterministically (Pitfall 1 → forbidden). Other parser exceptions also land in errors via a generic except clause to preserve isolation."
  - "asyncio.TimeoutError from wait_for is normalized to httpx.TimeoutException in the errors dict so the verdict engine's robots-timeout branch matches uniformly regardless of where the timeout originated."
  - "Reasons list ordering enforced by verdict.py: UA-assumption (Pitfall 2) inserted at position 0 whenever robots was evaluated, then robots reason, then ai_txt, then llms_txt, then signing_directory, then partial-downgrade reason last."

patterns-established:
  - "Pitfall 1 detection: parser sniffs first non-whitespace byte AND content-type for HTML signals before invoking protego — guards against SPA catch-all routes that silently parse as 'no rules → allow'."
  - "Cache-Control parsing checks no-store/no-cache/private BEFORE max-age (Pitfall 5) — origins that send 'no-store, no-cache, max-age=0' are correctly treated as uncacheable."
  - "Inspector grep gate: `grep -nE \"<wbauth-owned hostname pattern>\" inspector.py` returns 0 non-comment matches — POLICY-08 enforcement is mechanical, not just runtime."
  - "Verdict engine is pure: no I/O imports beyond httpx for exception type-checks. Tests live in test_policy_verdict.py with constructed Result/error inputs — no HTTP machinery needed."

requirements-completed: [POLICY-01, POLICY-02, POLICY-03, POLICY-04, POLICY-05, POLICY-06, POLICY-07, POLICY-08]

# Metrics
duration: ~30 min
completed: 2026-05-03
---

# Phase 2 Plan 02: Policy Inspector Summary

**Pre-flight policy inspector — `await wbauth.inspect(url) -> SitePolicy` with parallel-fetched robots.txt / ai.txt / llms.txt / signing-directory, deterministic strict verdict engine, in-process per-host LRU cache, and zero hard cloud dependency.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-05-03 (Plan 02-02 execution)
- **Completed:** 2026-05-03
- **Tasks:** 3 (all TDD: RED → GREEN per task)
- **Test files created:** 6 (24 parser + 15 verdict + 22 cache + 9 inspector = 70 new tests; 148/148 total passing including Phase-1 + Plan 02-01 regression)

## Accomplishments

- `await wbauth.inspect("https://example.com/path")` returns a frozen `SitePolicy` with all 9 fields populated per D-17 (url, robots, ai_txt, llms_txt, signing_directory, verdict, reasons, partial, errors, fetched_at).
- Four well-known endpoints fetched in parallel via `asyncio.gather(*[wait_for(c, 3.0) for c in coros], return_exceptions=True)` — per-endpoint failures isolated (POLICY-02 + Pitfall 4).
- HTML body served as `/robots.txt` (Pitfall 1) is detected by content-type sniffing AND first-byte check, raises `RobotsParseError`, and produces `verdict="forbidden"` end-to-end. Verified by `test_html_200_robots_yields_forbidden`.
- POLICY-08 invariant verified two ways: (a) grep gate `grep -nE "wbauth\.dev|agentpassport" inspector.py` returns 0 non-comment matches; (b) `test_only_user_supplied_host_is_fetched` asserts every captured request URL has the user-supplied host.
- Per-(host, endpoint) cache singleton avoids re-fetching `/robots.txt` across `inspect()` calls. Origin `Cache-Control: no-store / no-cache / private / max-age=0` correctly skip caching (Pitfall 5).
- Strict verdict engine implements all 16 RESEARCH rule-table rows; D-18 tie-break (partial → downgrade allowed-to-restricted) verified by anchor test.
- Open-question resolutions encoded in inspector docstring: redirects (`max=3`), robots-evaluation against input path, cache key `(host, endpoint)`.

## Task Commits

1. **Task 1: Build parsers, fixtures, dataclasses** — RED `bcebade` (test+fixtures), GREEN `69e6c75` (feat: 5 dataclasses + errors taxonomy + 4 parsers)
2. **Task 2: Verdict engine + per-host cache** — RED `c32c826` (test), GREEN `31f4647` (feat: pure compute_verdict + PolicyCache)
3. **Task 3: Async inspector + package-root re-exports** — RED `6024e0e` (test), GREEN `69ee50c` (feat: inspect orchestrator + wbauth re-exports)

## Files Created/Modified

### Created (24 files)

**Source modules (10):**
- `python/src/wbauth/policy/__init__.py` — re-exports inspect + 5 dataclasses + errors module
- `python/src/wbauth/policy/policy.py` — SitePolicy + RobotsResult / AiTxtResult / LlmsTxtResult (+Section/Link) / SigningDirectoryResult frozen dataclasses
- `python/src/wbauth/policy/errors.py` — PolicyError base + RobotsParseError + FetchError + VerdictError
- `python/src/wbauth/policy/inspector.py` — async `inspect(url)` orchestrator + module-level `_CACHE` singleton + `_reset_cache_for_tests`
- `python/src/wbauth/policy/verdict.py` — pure `compute_verdict` implementing the 16-row strict rule table
- `python/src/wbauth/policy/cache.py` — `PolicyCache` + `_parse_cache_control`
- `python/src/wbauth/policy/parsers/__init__.py` — re-exports four parser functions
- `python/src/wbauth/policy/parsers/robots.py` — protego wrapper with HTML-200 detection
- `python/src/wbauth/policy/parsers/ai_txt.py` — ai.txt v1.1.1 line-based parser
- `python/src/wbauth/policy/parsers/llms_txt.py` — llmstxt.org H1+blockquote+H2+link-list parser
- `python/src/wbauth/policy/parsers/signing_directory.py` — lightweight JSON parse, no JWK validation

**Fixture corpus (12 files):**
- `python/tests/fixtures/policy/robots/{allow, disallow, html_200, malformed, empty}.txt`
- `python/tests/fixtures/policy/ai_txt/{minimal, with_restrictions, malformed}.txt`
- `python/tests/fixtures/policy/llms_txt/{minimal, full, empty}.txt`
- `python/tests/fixtures/policy/signing_directory/{present, malformed}.json`

**Test files (6):**
- `python/tests/test_policy_parsers_robots.py` — 8 tests
- `python/tests/test_policy_parsers_ai_txt.py` — 5 tests
- `python/tests/test_policy_parsers_llms_txt.py` — 5 tests
- `python/tests/test_policy_parsers_signing_directory.py` — 6 tests
- `python/tests/test_policy_verdict.py` — 15 tests
- `python/tests/test_policy_cache.py` — 22 tests
- `python/tests/test_policy_inspector.py` — 9 tests

### Modified (1)

- `python/src/wbauth/__init__.py` — APPEND-only edit (preserved Plan 02-01 adapter exports verbatim; added `inspect`, `SitePolicy`, `RobotsResult`, `AiTxtResult`, `LlmsTxtResult`, `SigningDirectoryResult` to imports + `__all__`)

## Sample `inspect()` Call Output

Run against a mocked origin where `robots.txt` allows everything, `ai.txt` lists permissions only, `llms.txt` returns 404, and the signing-directory advertises one Ed25519 key:

```
URL:      https://demo.example/page
Verdict:  allowed
Partial:  False
Errors:   ['llms_txt']
Reasons:
  - evaluated against User-Agent='wbauth/0.1'
  - robots.txt allows our user-agent for this path
  - ai.txt permissions present, no restrictions
  - signing-directory published: signing supported (optional)
Robots can_fetch_url: True
AI permissions: ['Summarise content']
Signing directory present: True
Fetched at: 2026-05-03T22:09:59.915485+00:00
```

Note: `partial=False` despite `errors['llms_txt']` being set — llms.txt 404 is "absent" (neutral) per the verdict rule table, not an error that triggers the D-18 downgrade.

## Test Fixture Corpus

Verbatim from RESEARCH §"Test Fixture Corpus" (12 files):

| Endpoint           | Fixtures                                               | Expected verdict contribution |
| ------------------ | ------------------------------------------------------ | ----------------------------- |
| robots             | allow, disallow, html_200, malformed, empty            | allow / forbidden / forbidden / allow / allow |
| ai_txt             | minimal, with_restrictions, malformed                  | restricted / restricted / neutral |
| llms_txt           | minimal, full, empty                                   | neutral / neutral / neutral   |
| signing_directory  | present.json, malformed.json                           | allow-advisory / neutral       |

The `absent` case for signing_directory is exercised via HTTP 404 (no fixture file).

## Anchor Test Results

All 4 anchor tests from the plan PASS:

```
tests/test_policy_inspector.py::test_html_200_robots_yields_forbidden               PASSED  (Pitfall 1 anchor)
tests/test_policy_inspector.py::test_only_user_supplied_host_is_fetched             PASSED  (POLICY-08 anchor)
tests/test_policy_verdict.py::test_verdict_signing_directory_presence_alone_yields_allowed  PASSED  (Pitfall 3 anchor)
tests/test_policy_verdict.py::test_verdict_partial_downgrades_allowed_to_restricted  PASSED  (D-18 strict-philosophy anchor)
```

## POLICY-08 Grep Verification

```
$ grep -vE "^\s*#" python/src/wbauth/policy/inspector.py | grep -v "^\s*\"\"\"" | grep -cE "wbauth\.dev|agentpassport"
0
```

Inspector source contains zero non-comment / non-docstring references to wbauth-controlled hostnames. Combined with the runtime `test_only_user_supplied_host_is_fetched` assertion (every captured request hostname equals the input URL hostname), POLICY-08 is enforced both statically and dynamically.

## Phase-1 + Plan-02-01 Regression Confirmation

```
$ uv run pytest
============================= 148 passed in 0.92s ==============================
```

Breakdown: 78 prior (Phase 1 + Plan 02-01) + 70 new (Plan 02-02) = 148 total. All previous adapter, identity, signer, vector, and CLI tests continue to pass — no regressions.

## Open-Question Resolutions in Inspector Docstring

The inspector module docstring documents the four open-question resolutions inline so users don't have to chase the planning docs:

1. **Redirects** — `follow_redirects=True, max_redirects=3` on every well-known fetch (bounds latency without missing common 301-to-canonical-path patterns).
2. **Robots evaluation** — `protego.can_fetch(target_url, "wbauth/0.1")` invoked with the input URL's full path; answers "can I crawl THIS URL?" matching user intent.
3. **Cache key** — `(host, endpoint_name)` for the parsed result; verdict (path-dependent for robots) computed per-call from the cached parse. Compact + RFC 9309-correct.
4. **POLICY-08** — explicitly documented as an invariant + verified by both grep gate and `test_only_user_supplied_host_is_fetched`.

## Decisions Made

- **`partial` excludes 404s.** As noted in deviations below, treating 404 on optional endpoints as "errored" would downgrade every minimal-policy site to `restricted`, defeating the verdict's usefulness. The verdict rule table treats 404 as "absent" (neutral) for ai.txt/llms.txt/signing-directory and as allow-leaning for robots.txt; partial is reserved for real failures (timeouts, 5xx, parse errors, network errors).
- **`asyncio.TimeoutError` normalized to `httpx.TimeoutException`.** The verdict engine's robots-timeout branch matches `isinstance(httpx.TimeoutException)` only; normalizing at the boundary keeps the engine free of asyncio dependency and lets us reuse one branch for httpx-internal timeouts AND `wait_for` cancellations.
- **Reasons-list UA assumption pinned at index 0.** Whenever robots was evaluated cleanly, the inspector inserts `"evaluated against User-Agent='wbauth/0.1'"` as the first reason — directly addressing Pitfall 2 (UA-mismatch confusion).
- **Inspector grep gate referenced in docstring without literal hostnames.** The original docstring referenced the grep pattern verbatim, which itself triggered the POLICY-08 grep gate (the docstring contained `wbauth.dev|agentpassport`). Reworded to "must return zero non-comment matches for any wbauth-owned hostname literal" — preserves intent without tripping its own check.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] `partial=True` was triggered by 404 responses on optional endpoints**

- **Found during:** Task 3 GREEN run (`test_happy_path_no_restrictions_yields_allowed` failed)
- **Issue:** Initial implementation set `partial = bool(errors)`. With ai.txt / llms.txt / signing-directory all 404'ing (the common case for minimal sites), `errors` was non-empty and `partial=True` triggered the D-18 tie-break, downgrading otherwise-allowed sites to `restricted`. The verdict rule table treats 404 on those endpoints as neutral and 404 on robots.txt as allow-leaning per RFC 9309.
- **Fix:** Added `_is_partial_failure(exc)` helper that returns False for `httpx.HTTPStatusError(404)` and True otherwise. `partial` now reflects only real failures (timeouts, 5xx, parse errors, network errors).
- **Files modified:** `python/src/wbauth/policy/inspector.py`
- **Verification:** `test_happy_path_no_restrictions_yields_allowed` now passes; `test_ai_txt_timeout_yields_partial` continues to pass (timeout still counts).
- **Committed in:** `69ee50c` (Task 3 GREEN)

**2. [Rule 1 — Bug] Inspector module docstring tripped its own POLICY-08 grep gate**

- **Found during:** Task 3 GREEN verify-gate run (POLICY-08 grep returned `1` instead of `0`)
- **Issue:** The docstring documented the POLICY-08 enforcement mechanism by quoting the grep pattern verbatim — which contained the literal substring `wbauth\.dev|agentpassport`. The grep gate is line-based and filters out only comment lines (`^\s*#`) and triple-quote sentinel lines (`^\s*"""`); content INSIDE a multi-line docstring still matches.
- **Fix:** Reworded the docstring to describe the grep gate's intent ("must return zero non-comment matches for any wbauth-owned hostname literal") without including the literal hostname substrings.
- **Files modified:** `python/src/wbauth/policy/inspector.py`
- **Verification:** Grep gate now returns `0`. Documentation intent preserved.
- **Committed in:** `69ee50c` (Task 3 GREEN)

---

**Total deviations:** 2 auto-fixed (both Rule 1 bugs caught during the GREEN verify step). Both are correctness fixes — the first preserves the verdict engine's intended semantics; the second preserves the POLICY-08 enforcement mechanism. No scope creep; all critical functionality from the plan is implemented as specified.

## Issues Encountered

- **macOS UF_HIDDEN flag** (L-05): re-ran `bash scripts/post-sync.sh` four times during this plan after `uv` operations re-hid site-packages. Phase-1 known issue, no new mitigation needed beyond the existing `scripts/post-sync.sh`.

## TDD Gate Compliance

All 3 tasks followed RED → GREEN gate sequence:

| Task | RED commit (test) | GREEN commit (feat) |
| ---- | ----------------- | ------------------- |
| 1    | `bcebade`         | `69e6c75`           |
| 2    | `c32c826`         | `31f4647`           |
| 3    | `6024e0e`         | `69ee50c`           |

No REFACTOR commits — implementations were already minimal at GREEN.

## Threat Flags

None — all threat-register entries (T-02-02-01 through T-02-02-08) from the plan's `<threat_model>` are mitigated as designed:

- T-02-02-01 (DoS via large robots body): 3s timeout + connection-pool close
- T-02-02-02 (DoS via deep ai.txt nesting): line-based parser + 1 MB body cap in ai_txt.py + llms_txt.py
- T-02-02-03 (SSRF via inspect URL): documented in inspector docstring as "do not pass untrusted URLs"
- T-02-02-04 (in-process cache info disclosure): no PII, per-process, no persistence
- T-02-02-05/06 (cache poisoning): bucket TTL caps + max-age=0 skips
- T-02-02-07 (URL leakage in errors): documented in docstring
- T-02-02-08 (POLICY-08 violation via future refactor): grep gate enforced in plan + this summary

No new security surface introduced beyond what the threat model anticipated. Plan 02-02 is a pure orchestration + parsing + glue layer; no new cryptographic code (Phase-1 signer is unchanged).

## Next Phase Readiness

- Plan 02-03 (CLI) can rely on `wbauth.inspect` and `wbauth.SitePolicy` being stable at the package root. The `--json` output path will need a `_serialize_policy(SitePolicy) -> dict` helper (CLI-side concern; SitePolicy is a frozen dataclass so `dataclasses.asdict()` works for the basic case, but `errors: dict[str, Exception]` and `fetched_at: datetime` need custom handling — Plan 02-03's responsibility).
- Phase 4 (TypeScript SDK) has the inspector as a reference: same fan-out pattern, same verdict rule table, same per-(host, endpoint) cache shape. The 16-row table in RESEARCH §"Verdict Engine Rule Table" is canonical across languages.
- Phase 5 (docs/launch) can reference the sample `inspect()` output above for the README quickstart "lighthouse for agents" demo.

## Self-Check: PASSED

Verification commands (all succeed):

- `[ -f python/src/wbauth/policy/__init__.py ]` → FOUND
- `[ -f python/src/wbauth/policy/policy.py ]` → FOUND
- `[ -f python/src/wbauth/policy/errors.py ]` → FOUND
- `[ -f python/src/wbauth/policy/inspector.py ]` → FOUND
- `[ -f python/src/wbauth/policy/verdict.py ]` → FOUND
- `[ -f python/src/wbauth/policy/cache.py ]` → FOUND
- `[ -f python/src/wbauth/policy/parsers/robots.py ]` → FOUND
- `[ -f python/src/wbauth/policy/parsers/ai_txt.py ]` → FOUND
- `[ -f python/src/wbauth/policy/parsers/llms_txt.py ]` → FOUND
- `[ -f python/src/wbauth/policy/parsers/signing_directory.py ]` → FOUND
- All 12 fixtures + 6 test files exist (verified by `ls`)
- `git log --oneline | grep bcebade` → FOUND (Task 1 RED)
- `git log --oneline | grep 69e6c75` → FOUND (Task 1 GREEN)
- `git log --oneline | grep c32c826` → FOUND (Task 2 RED)
- `git log --oneline | grep 31f4647` → FOUND (Task 2 GREEN)
- `git log --oneline | grep 6024e0e` → FOUND (Task 3 RED)
- `git log --oneline | grep 69ee50c` → FOUND (Task 3 GREEN)

---
*Phase: 02-python-adapters-policy-inspector*
*Completed: 2026-05-03*
