---
phase: 04-typescript-sdk-framework-integrations
plan: 02
subsystem: typescript-sdk-conformance
tags: [typescript, cross-language, identity, round-trip, multi-key-rotation, vitest, conformance, regression-protection]

# Dependency graph
requires:
  - phase: 04-typescript-sdk-framework-integrations
    plan: 01
    provides: Identity.loadOrGenerate (PEM file path), Identity.fromTestKey, Identity.rotate, exportJwks, sign() byte-equal vs vector 01 expected.json
  - phase: 01-foundation-cryptographic-root
    provides: spec/test-vectors/01-basic-get + 04-multi-uri-jwks pinned by python-vectors workflow; vitest helpers.loadAllVectors with VectorExpected.jwks_full typing
  - phase: 02-python-adapters-policy-inspector
    provides: python/src/wbauth/identity.py (PEM write code at lines 282-293 — the on-disk format we test compatibility with)
provides:
  - typescript/tests/identity-roundtrip.test.ts — D-66 cross-language Identity round-trip oracle (Python writes PKCS8 PEM → TS reads via createPrivateKey → kid + Signature byte-equal vs vector 01)
  - typescript/tests/identity-multikey.test.ts — Multi-key Identity rotation TS coverage (closes Phase 1 vectors.test.ts hand-off; rotate() + exportJwks() ordering verified)
  - vectors.test.ts skip comment now points at identity-multikey.test.ts as the canonical multi-key oracle
affects:
  - 04-03-framework-demos (no API change — round-trip proof confirms demos can pass a Python-keygen'd identity to TS code)
  - 05-publishing-distribution (round-trip test is a prime daily-canary candidate alongside cloudflare-debug.yml — catches Python↔TS PEM drift within 24h between releases)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cross-runtime fixture materialization via execSync('cd ../python && uv run python3 -c \"...\"') — keeps the Python-side cryptography import inside the python workspace venv without polluting TS deps"
    - "pythonAvailable() guard wraps describeIfPython = pythonOK ? describe : describe.skip — auto-skip if python venv not synced (contributor-friendly)"
    - "RED-as-already-GREEN TDD pattern: when adding regression-protection layer for code shipped in a prior plan, the new test passes on first run; commit as single test(...) commit (no GREEN impl), document as expected per 01-04 SUMMARY precedent"

key-files:
  created:
    - typescript/tests/identity-roundtrip.test.ts (118L) — 2 tests: kid match + vector 01 byte-equal sign, beforeAll spawns python3 to write PEM, afterAll unlinks
    - typescript/tests/identity-multikey.test.ts (108L) — 4 tests: rotate placement + no `d` leak + RFC 7638 fields + vector 04 fixture ordering sanity
    - .planning/phases/04-typescript-sdk-framework-integrations/04-02-SUMMARY.md (this file)
  modified:
    - typescript/tests/vectors.test.ts — updated docstring + skip comment to point at identity-multikey.test.ts as the canonical multi-key oracle (the structural skip remains because web-bot-auth's raw Signer API is single-key by design)

key-decisions:
  - "execSync command uses `cd ../python && uv run python3` not `uv run python3` from typescript/ directly — the cryptography lib lives in the python workspace venv (uv.workspace member), root invocation has no cryptography. Findings to feed Phase 5 docs: Linux CI conformance.yml already runs `uv sync --workspace` so cwd-shim works there too."
  - "pythonAvailable() guard auto-skips when uv/cryptography unavailable — keeps the suite green on contributor machines without `uv sync` already run. Trade-off: silent skip vs hard fail. Chose silent because Phase 5 daily-canary will still catch drift in CI where deps ARE installed."
  - "Did NOT delete the vectors.test.ts skip — it's structural (raw web-bot-auth Signer API only handles one key at a time). Updated the skip's comment to point at the new file so future readers find the multi-key oracle in identity-multikey.test.ts instead of treating the skip as a TODO."
  - "Did NOT add an Identity.fromJwks([active, retiring]) constructor for vector 04 byte-equal reconstitution — D-58 minimalism. The 4th multi-key test asserts the FIXTURE shape (kty/crv/kid/x ordering) rather than reconstructing an Identity from arbitrary JWKs. v1.x can add fromJwks if a TS user needs it."

patterns-established:
  - "Cross-language oracle test naming: `tests/identity-roundtrip.test.ts` for cross-language SDK contract tests; `tests/identity-multikey.test.ts` for multi-key Identity API tests"
  - "Vector-driven multi-key fixture sanity (test 4 in identity-multikey.test.ts) — verifies expected.json schema invariants Python pinned, without requiring a TS-side reconstitution constructor"

requirements-completed: []
requirements-strengthened: [ADAPT-04, ADAPT-05, IDENT-04, IDENT-07]

# Metrics
duration: 4min
completed: 2026-05-10
---

# Phase 4 Plan 02: Cross-language Identity Round-trip + Multi-key TS Coverage Summary

**Cross-language SDK contract is now machine-verified on every PR: a key written by Python's cryptography library can be loaded by the TS Identity class and used to sign vector 01 with byte-equal output — D-60 / D-66 closed end-to-end with 6 new tests (2 round-trip + 4 multi-key rotation).**

## Performance

- **Duration:** ~4 minutes
- **Started:** 2026-05-10T20:02:56Z
- **Completed:** 2026-05-10T20:07:26Z
- **Tasks:** 2 of 2 complete (both `tdd="true"`)
- **Files created:** 2 (both vitest test files; no source code — purely conformance/regression layer)
- **Files modified:** 1 (typescript/tests/vectors.test.ts — docstring + skip comment update)
- **Tests added:** 6 (2 round-trip + 4 multi-key)
- **Tests passing (TS suite):** 33 of 34 (was 27/28 after Plan 04-01; +6 new tests, +0 new skips). The 1 carry-forward skip in vectors.test.ts is structural — web-bot-auth's raw Signer API is single-key by design.

## Accomplishments

- **D-66 satisfied (D-60 proven runtime):** The "single key file works in both SDKs" guarantee is now machine-verifiable. Python's `Ed25519PrivateKey.private_bytes(PEM, PKCS8, NoEncryption)` PEM output → `createPrivateKey(pem).export({format:'jwk'})` in Node → identical RFC 7638 thumbprint kid `poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U` AND identical Signature/Signature-Input/Signature-Agent for vector 01.
- **Phase 1 vectors.test.ts hand-off closed:** 01-04-SUMMARY shipped vector 04 with `it.skip(...) (multi-key — Phase 4 will cover)`. Plan 04-02 adds 4 new multi-key Identity tests in `identity-multikey.test.ts` that exercise `Identity.rotate()` end-to-end. The vectors.test.ts skip now correctly points at the new file as the canonical multi-key oracle.
- **T-04-02-04 mitigation in test:** Both active AND retiring keys verified to NOT contain the `d` private component in `exportJwks()` output — private bytes provably do not leak via the public JWKS export path.
- **A8 cross-language ordering verified:** Test 4 of identity-multikey.test.ts proves the vector 04 fixture's `jwks_full.keys` array is `[active, retiring]` ordering (active kid matches `expected.kid`), matching Python's `export_jwks` output that produced the fixture. If TS ever rearranges to `[retiring, active]`, this test fails.
- **Auto-skip on contributor machines:** `pythonAvailable()` guard means the suite stays green for TS-only contributors who haven't run `uv sync` in the python workspace; CI (Linux) has both runtimes pre-synced, so the cross-language gate runs in CI and is mandatory there.
- **/tmp cleanup verified:** No stray `/tmp/wbauth-roundtrip.pem` after the test run (afterAll fires; beforeAll defensively unlinks any prior leftover before re-creating, handling failed-prior-run edge case T-04-02-01).

## Task Commits

Per `tdd="true"` semantics + 01-04-SUMMARY documented "RED-as-already-GREEN" precedent (the Identity + sign + rotate implementations already exist from Plan 04-01; Plan 04-02 adds the regression-protection oracle layer):

1. **Task 1:** `794d8ef` test(04-02): add cross-language Identity round-trip test (D-66)
2. **Task 2:** `2a46eb0` test(04-02): add multi-key rotation TS coverage (closes Phase 1 hand-off)

Both commits are `test(...)` — no `feat(...)` GREEN counterpart needed because the implementation under test was already shipped + verified in Plan 04-01 commits `6bbd906`/`c4462f6`/`1dfa9e0`. This is the same situation 01-04-SUMMARY documented for its conformance test ("If a test passes unexpectedly during the RED phase, investigate. Investigated; expected behavior given the chicken-and-egg vector authoring strategy.")

Note on parallel execution: commits `f8f07f5` and `6e05674` from Plan 04-03 (framework demos) interleave between my Task 1 and Task 2 commits. Per `<executor_context>`, Plan 04-02 is "parallel-safe with Plan 04-03 (different files: TS+Python tests vs `examples/`)" — confirmed: Plan 04-03 only touched `examples/`, no overlap with `typescript/tests/`. No merge conflicts, no regressions in either plan's test suite.

## Cross-language Verification Evidence

### Round-trip path (D-66)

```
Python                                            TypeScript
─────────                                         ──────────
Ed25519PrivateKey.from_private_bytes(b64decode(   →  /tmp/wbauth-roundtrip.pem
  "n4Ni-HpISpVObnQMW0wOhCKROaIKqKtW_2ZYb2p9KcU"))    (PKCS8 NoEncryption PEM, mode 0o600)
    .private_bytes(PEM, PKCS8, NoEncryption())
                                                  Identity.loadOrGenerate(KEY_PATH, ...)
                                                    → createPrivateKey(pem).export({format:'jwk'})
                                                    → signerFromJWK(jwk) → kid via signer.keyid

Assertion 1: kid === "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U" (RFC 7638 thumbprint of pub key)  ✅
Assertion 2: sign(vector01_request, identity, vector01_params) returns
             { signature, signatureInput, signatureAgent } byte-equal to
             spec/test-vectors/01-basic-get/expected.json                                              ✅
```

### Multi-key path (closes Phase 1 skip)

```
Plan 04-01 shipped:    Identity.fromTestKey(...).rotate(newPath)
Plan 04-02 verifies:   exportJwks().keys = [
                         { kty:OKP, crv:Ed25519, kid:<NEW>, x:<NEW>, /* no `d` */ },  // active
                         { kty:OKP, crv:Ed25519, kid:<ORIG>, x:<ORIG>, /* no `d` */ }, // retiring
                       ]
                       — ordering [active, retiring] matches Python export_jwks (A8 ✅)
                       — neither active nor retiring leaks `d` (T-04-02-04 ✅)
                       — active.x is base64url 43-char (Ed25519 32-byte raw) ✅
```

### Test execution

```
$ cd typescript && npm test -- identity-roundtrip.test.ts
 Test Files  1 passed (1)
      Tests  2 passed (2)

$ cd typescript && npm test -- identity-multikey.test.ts
 Test Files  1 passed (1)
      Tests  4 passed (4)

$ cd typescript && npm test                     # full suite, no regressions
 Test Files  8 passed (8)
      Tests  33 passed | 1 skipped (34)         # was 27|1 after Plan 04-01

$ [ ! -f /tmp/wbauth-roundtrip.pem ] && echo "OK: cleaned"
OK: cleaned
```

## Decisions Made

- **`cd ../python && uv run python3` (not `uv run python3` from cwd):** The execSync command runs from vitest's cwd which is `typescript/`. The repo root pyproject.toml declares `[tool.uv.workspace] members = ["python"]`; root-level `uv run` has no `cryptography` dep. Switching cwd into `python/` for the spawn picks up the workspace member's venv where cryptography is installed. macOS dev verified; Linux CI runs `uv sync --workspace` per Phase 1 conformance.yml so the same path works there. Phase 5 docs should mention this for contributors who try to run the test stand-alone.
- **Auto-skip via `pythonAvailable()` guard:** Trade-off vs hard-fail. Chose silent skip so TS-only contributors who haven't run `uv sync` aren't blocked from running `npm test`. Risk: regression slips through locally. Mitigation: CI (Linux conformance.yml) has both runtimes pre-synced, so the gate runs there and is mandatory before merge.
- **Did not retire the `vectors.test.ts` skip:** It's a *structural* skip — the raw `web-bot-auth` Signer API is single-key by design, so the signer-level vector loop literally cannot construct a 2-key fixture. Updated the skip's docstring to make this clear (was misleading "Phase 4 will cover" → now "see identity-multikey.test.ts"). The Identity-API-level multi-key oracle lives in the new file.
- **Did NOT add `Identity.fromJwks([active, retiring])` constructor:** D-58 minimalism. The 4th multi-key test (vector 04 fixture sanity) asserts the schema invariants Python pinned (kty/crv/kid/x present, ordering [active,retiring], distinct kids, no `d` leak) without needing a TS-side reconstitution constructor. v1.x can add `fromJwks` if a TS user needs to load a Python-rotated Identity directly from a JSON-serialized JWKS pair.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan sketch had unbalanced braces in `afterEach`**
- **Found during:** Task 2 file write.
- **Issue:** Plan's Task 2 sketch had `afterEach(() => rmSync(tmp, { recursive: true, force: true }); });` — extra trailing `;` and unbalanced braces would not parse.
- **Fix:** Wrote the correct form `afterEach(() => { rmSync(tmp, { recursive: true, force: true }); });` (block body to match the plan's intent).
- **Files modified:** `typescript/tests/identity-multikey.test.ts` (only — never made it into the codebase in the broken form).
- **Verification:** All 4 multi-key tests pass.
- **Committed in:** `2a46eb0`.

**2. [Rule 1 - Clarity bug] vectors.test.ts skip comment was misleading after Plan 04-02**
- **Found during:** Final verification (full TS suite output showed `04-multi-uri-jwks (multi-key — Phase 4 will cover)`).
- **Issue:** The Phase 1 skip message says "Phase 4 will cover" — but Phase 4 *is* now done, and the multi-key oracle lives in a different file. Reader following that comment would not find the new oracle.
- **Fix:** Updated docstring + skip message to point at `identity-multikey.test.ts` as the canonical multi-key oracle, and explained why the structural skip in vectors.test.ts remains (single-key Signer API).
- **Files modified:** `typescript/tests/vectors.test.ts`.
- **Verification:** Full suite still 33|1 passing|skipped — no test behavior change, comment-only update.
- **Committed in:** `2a46eb0`.

### Confirmation: No new dependencies, no new source code

- 0 new files in `typescript/src/`.
- 0 new entries in `typescript/package.json` deps.
- Only `node:child_process`, `node:fs`, `node:os`, `node:path` — all stdlib — added to test imports.
- Pure regression/conformance layer per the plan's "no new public API" boundary.

## TDD Gate Compliance

Both tasks shipped as single `test(...)` commits per the documented "RED-as-already-GREEN" pattern that 01-04-SUMMARY established for analogous regression-layer additions.

Per the plan-level TDD enforcement rule "If a test passes unexpectedly during the RED phase, STOP. Investigate":

- **Task 1 investigation:** Test passes because Plan 04-01 already shipped `Identity.loadOrGenerate` reading PKCS8 PEM via Node stdlib `createPrivateKey`. The signing path (`sign() → web-bot-auth signatureHeaders`) was vector 01 byte-equal verified at the JWK level in Plan 04-01 commit `c4462f6`. Plan 04-02 closes the loop by proving the PEM-file path produces the same Signature as the JWK-loaded path (the actual missing oracle layer per D-66). Pass-on-first-run is the correct outcome — the test EXISTS to lock in that contract for future regression detection.
- **Task 2 investigation:** Test passes because Plan 04-01 shipped `Identity.fromTestKey`, `rotate`, `exportJwks` with documented [active, retiring] ordering. Plan 04-02 adds the Identity-API-level coverage of vector 04 (which Plan 04-01 explicitly skipped at the raw-Signer level per its own SUMMARY hand-off). Pass-on-first-run is the correct outcome — same regression-protection role.

Conclusion: gate compliance verified by inspection. The test commits are GREEN-on-arrival because the implementation they cover was correctly shipped earlier; this is the documented pattern for regression-layer additions, not a TDD anti-pattern.

## Hand-off Notes

### To Plan 04-03 (framework demos — running in parallel)

No coordination needed — Plan 04-03 only touches `examples/`. The round-trip test means a Python-keygen'd identity (e.g., from a `wbauth keygen` invocation in a demo's "first-run setup" step) can be passed straight to TS demo code via `Identity.loadOrGenerate("./key.pem", { signatureAgentUrl: "..." })`. Plan 04-03's `examples/stagehand_demo.ts` should document this in its README/preamble.

### To Phase 5 (publishing & hardening)

The cross-language round-trip test is a prime candidate for the daily canary alongside Phase 1's `cloudflare-debug.yml`. Reasoning:
- If a future Node release changes `createPrivateKey().export({format:'jwk'})` byte-output, this test fails within 24h.
- If a future Python `cryptography` release changes PKCS8 PEM byte-output, same.
- If `web-bot-auth` 0.1.x changes `signerFromJWK().keyid` derivation, same.
- Cost: ~1s of CI time per run.
- Action item for Phase 5: add `cd typescript && npm test -- identity-roundtrip.test.ts` to the daily cron workflow Phase 1 set up. The existing `cd ../python && uv run python3 ...` invocation works in the GitHub Actions Linux runners (already used by `python-vectors`).

### To v1.x (post-army deferred)

If TS users start asking for full multi-key Identity reconstitution from JWKS (e.g., loading a saved 2-key JWKS file written by Python), add `Identity.fromJwks([active, retiring])` as a v1.x API. Test 4 of identity-multikey.test.ts already documents the expected shape (matches Python `export_jwks` output verbatim) — implementing the constructor is ~20 LOC and the test would extend to byte-equal reconstitution oracle.

## Threat Flags

None — Plan 04-02 adds tests only; introduces no new network endpoints, auth paths, file access patterns at trust boundaries, or schema changes. The execSync call to python3 has been audited (T-04-02-02): hard-coded literal command body, no user input interpolation.

## Self-Check: PASSED

All claimed files exist:

```
typescript/tests/identity-roundtrip.test.ts                              FOUND
typescript/tests/identity-multikey.test.ts                               FOUND
.planning/phases/04-typescript-sdk-framework-integrations/04-02-SUMMARY.md  FOUND (this file)
```

All claimed commits exist in `git log`:

```
794d8ef  test(04-02): add cross-language Identity round-trip test (D-66)        FOUND
2a46eb0  test(04-02): add multi-key rotation TS coverage (closes Phase 1 hand-off)  FOUND
```

Verification gates (from PLAN `<verification>` section):

```
1. Files exist                          PASS (both)
2. Round-trip test                      PASS (2/2 tests)
3. Multi-key test                       PASS (4/4 tests)
4. Full TS suite                        PASS (33 passed | 1 skipped — was 27|1)
5. /tmp cleanup verified                PASS (no stray PEM after run)
```

`npm test` → 33 passing / 1 skipped (4 vector-loop + 7 identity + 4 signer + 6 fetch + 5 playwright + 1 conformance + 2 round-trip + 4 multi-key = 33).
