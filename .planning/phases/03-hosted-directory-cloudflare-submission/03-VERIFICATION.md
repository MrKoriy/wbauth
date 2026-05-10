---
phase: 03-hosted-directory-cloudflare-submission
verified: 2026-05-10T14:30:00Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 3: Hosted Directory & Cloudflare Submission — Verification Report

**Phase Goal:** Stand up the public agent identity directory at `https://wbauth.silov801.workers.dev` (Cloudflare Worker + D1) so verifiers can fetch JWKS for any registered agent, prove the full register→sign→verify flow end-to-end, and ship the local `wbauth serve` JWKS host for self-hosters.

**Verified:** 2026-05-10T14:30:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | User can register an agent via two-step proof-of-key-ownership (SC 1, DIR-01, DIR-02) | VERIFIED | `/register/challenge` + `/register/submit` routes substantive in `directory/src/routes/register.ts`; live E2E confirmed kid `kkklAFaE0n5cUZ_s9VjgWMtLWPf9GZgM7daY0WL95-I` registered in production D1; 11 Python tests green |
| 2  | `GET /.well-known/…/{kid}` returns JWKS with correct content-type, directory signature, and `public, max-age=300` Cache-Control — no `immutable` (SC 2, DIR-03, DIR-04) | VERIFIED | Live curl confirmed: `content-type: application/http-message-signatures-directory+json`, `cache-control: public, max-age=300`, `Signature` + `Signature-Input` headers present signed by directory kid `UeCLA_Q47BCqq9eB6T7gPaLnVJ1gpNyDI4Vi4bUanZw` |
| 3  | End-to-end flow validated: register → fetch JWKS → sign probe → external verifier (SC 3, DIR-08) | VERIFIED (PARTIAL) | `E2E-RESULT.md` documents STATUS: PARTIAL — internal chain register→fetch→sign succeeded; Cloudflare research verifier returned FAILURE banner because it validates only the RFC 9421 test key. Accepted per 03-RESEARCH.md §8 NOTE and verification context instructions. `python/scripts/e2e_phase3.py` exits 0. |
| 4  | Nightly snapshot job ships with cron commented out; `workflow_dispatch` triggers the `scripts/snapshot.sh` against `/static/all.json` (SC 4, DIR-05) | VERIFIED | `.github/workflows/snapshot.yml` cron commented out (grep confirmed); `/static/all.json` live endpoint responds HTTP 200 with 3-agent payload |
| 5  | `wbauth serve --jwks <path>` runs a self-hostable JWKS server at ≤30 executable LOC (SC 5, CLI-05) | VERIFIED | `jwks_server.py` executable LOC = 26 (D-50 cap is 30); serves correct content-type + 200/404 per kid; 6 server tests green |
| 6  | Per-IP rate limit (10/day) on `/register/*` enforced via D1 (DIR-04, DIR-07) | VERIFIED | `ratelimit.ts` uses D1 `.batch()` atomic UPSERT + cleanup-on-write; live Worker returned `rate_limited` 429 on excess request during verification; `ratelimit.test.ts` 10-allowed/11th-rejected tests pass |
| 7  | Reserved-name blocklist (12 tokens × 3 suffixes) enforced at `/register/submit` (DIR-04) | VERIFIED | `blocklist.ts` substantive; enforced in `register.ts` lines 74–85 before any crypto work; 7 blocklist test cases (exact, substring+suffix, false-positive guard) all green |
| 8  | `wbauth register --directory <url> --identity <path>` CLI implements proof-of-key-ownership flow (CLI-04) | VERIFIED | `cli.py` `_do_register` async helper: two-load Identity pattern, `ensure_content_digest` pre-computation, `sign()` reuse (Pitfall 5 guard); 11 tests green; default `--directory` is production Worker URL |
| 9  | `wbauth keygen --jwks-output <path>` emits public JWKS without private scalar (D-51) | VERIFIED | `cli.py` `_dispatch_keygen` writes via `identity.export_jwks()`; `test_keygen_jwks_output_writes_valid_jwks` asserts `"d" not in k0`; 3 keygen-JWKS tests green |

**Score:** 9/9 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `directory/src/routes/register.ts` | Two-step registration handlers | VERIFIED | 168 LOC; challenge + submit routes with rate-limit, blocklist, zod validation, crypto verify, D1 UPSERT |
| `directory/src/routes/read.ts` | JWKS + agents list + snapshot endpoints | VERIFIED | 159 LOC; `/.well-known/…` (root + kid), `/agents/{kid}`, `/agents`, `/static/all.json` all implemented |
| `directory/src/blocklist.ts` | 12-token reserved-name blocklist | VERIFIED | Exact and substring+suffix matching; false-positive guard present |
| `directory/src/ratelimit.ts` | D1-backed per-IP rate limiter | VERIFIED | `.batch()` atomic UPSERT + cleanup-on-write pattern per D-48 |
| `directory/src/signing.ts` | Directory keypair signer (D-42) | VERIFIED | Lazy-cached signer from `DIRECTORY_PRIVATE_JWK` secret; `getDirectoryPublicJwks` strips `d` field |
| `directory/src/index.ts` | Hono app wiring routes + onError | VERIFIED | All routes mounted; generic 500 handler (no stack traces leaked) |
| `directory/tests/` (4 files, 20 tests) | Unit tests for Worker | VERIFIED | `npx vitest run` → 20/20 pass |
| `python/src/wbauth/_http_server/jwks_server.py` | stdlib JWKS server ≤30 exec LOC | VERIFIED | 26 executable LOC; `ThreadingHTTPServer`; correct content-type + cache-control |
| `python/src/wbauth/cli.py` (register + serve + keygen --jwks-output) | CLI-04, CLI-05, D-51 | VERIFIED | All three handlers present and wired in `_dispatch`; `_do_register` module-importable |
| `python/scripts/e2e_phase3.py` | D-52 manual exit-criterion gate | VERIFIED | Exists; NOT referenced in any CI workflow; handles PARTIAL/PASS/FAIL outcomes |
| `scripts/snapshot.sh` + `.github/workflows/snapshot.yml` | Nightly snapshot (DIR-05) | VERIFIED | Script fetches `/static/all.json`; workflow `workflow_dispatch` only; cron commented |
| `E2E-RESULT.md` | Captured D-52 outcome | VERIFIED | `STATUS: PARTIAL`; registered kid confirmed in D1; no private key material |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `directory/src/index.ts` | `routes/register.ts` + `routes/read.ts` | `app.route()` | WIRED | All endpoints mounted; confirmed by live Worker responses |
| `routes/register.ts` | `blocklist.ts` | `isReservedName()` import + call at submit L74 | WIRED | Checked at submit before crypto work |
| `routes/register.ts` | `ratelimit.ts` | `checkAndIncrementRateLimit()` at challenge L33 + submit L69 | WIRED | Both challenge and submit consume rate-limit budget |
| `routes/register.ts` | `web-bot-auth` verify | `verify()` + `verifierFromJWK()` from `web-bot-auth/crypto` | WIRED | Proof-of-key-ownership at submit L109–117 |
| `routes/read.ts` | `signing.ts` | `getDirectorySigner()` + `getDirectoryPublicJwks()` | WIRED | Called on every JWKS read; lazy-cached per isolate |
| `routes/read.ts` | D1 `DB` binding | `.bind(kid).first()` + `.bind().all()` | WIRED | D1 database_id `e9bd675b-da95-4ee5-aecf-58c326cfe766` wired in `wrangler.jsonc` |
| `wbauth register` CLI | `wbauth.signer.sign` | `from .signer import sign` in `_do_register` (L524) | WIRED | Pitfall 5 regression guard: `test_do_register_happy_path_calls_sign_once` asserts `mock_sign.call_count == 1` |
| `wbauth serve` CLI | `jwks_server.serve()` | `from ._http_server.jwks_server import serve` in `_dispatch_serve` | WIRED | Lazy import; `serve()` starts `ThreadingHTTPServer` |
| `e2e_phase3.py` | `wbauth.cli._do_register` | `from wbauth.cli import _do_register` | WIRED | Module-importable contract honored |
| `snapshot.yml` | `scripts/snapshot.sh` | `run: bash scripts/snapshot.sh` | WIRED | ENV vars `DIRECTORY_URL` + `OUT_DIR` set in workflow |
| `snapshot.sh` | `/static/all.json` Worker endpoint | `curl "${DIRECTORY_URL}/static/all.json"` | WIRED | Live endpoint returns 200 + full agent payload |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `routes/read.ts` `/.well-known/…/{kid}` | `row.keys` (JWKS JSON) | `DB.prepare("SELECT keys FROM agents WHERE kid = ?").first()` | Yes — D1 real query | FLOWING |
| `routes/read.ts` `/agents` | `results` (agent list) | `DB.prepare("SELECT kid, client_name, … FROM agents ORDER BY …").all()` | Yes — D1 real query | FLOWING |
| `routes/read.ts` `/static/all.json` | `agents` (full dump) | `DB.prepare("SELECT … FROM agents … LIMIT 10000").all()` | Yes — D1 real query | FLOWING |
| `routes/read.ts` signing | `sigHeaders` | `directoryResponseHeaders(…, [signer], …)` using live `DIRECTORY_PRIVATE_JWK` secret | Yes — Ed25519 sign per request | FLOWING |
| `jwks_server.py` | `jwks_bytes` | `jwks_path.read_bytes()` at make_handler time (module-level) | Yes — real file read | FLOWING |
| `cli.py _do_register` | `result` | `httpx.AsyncClient.post(…/register/submit)` against live Worker | Yes — live HTTP | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Worker responds to `/agents` | `curl -sw "\nHTTP %{http_code}\n" https://wbauth.silov801.workers.dev/agents` | `HTTP 200` + `{"page":1,"count":3,"agents":[…]}` | PASS |
| Directory root JWKS endpoint | `curl -sw "\nHTTP %{http_code}\n" https://…/.well-known/http-message-signatures-directory` | `HTTP 200` + `{"keys":[{kty,crv,kid,x}]}` | PASS |
| E2E-registered kid resolvable | `curl -si https://…/.well-known/…/kkklAFaE0n5cUZ_s9VjgWMtLWPf9GZgM7daY0WL95-I` | `HTTP 200` + correct content-type + Signature + no `immutable` | PASS |
| Worker unit tests | `npx vitest run` in `directory/` | `20/20 pass` (4 test files) | PASS |
| Python suite | `uv run pytest -v` in `python/` | `195 passed in 3.23s` | PASS |
| jwks_server.py LOC budget | `grep -vcE '…' jwks_server.py` | `26` (cap: 30) | PASS |
| Snapshot cron disabled | `grep -E "^\s*-\s*cron:" snapshot.yml` | no output (cron commented) | PASS |
| E2E script NOT in CI | `grep -rqE 'e2e_phase3' .github/workflows/*.yml` | NOT_IN_CI | PASS |
| Rate-limit live | `curl POST /register/challenge` on rate-limited IP | `429 {"error":"rate_limited","retry_after_seconds":3600}` | PASS |
| `/static/all.json` endpoint | `curl https://…/static/all.json` | `HTTP 200` + agents array with real D1 data | PASS |

---

## Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| DIR-01 | Worker exposes `POST /register` accepting Signature Agent Card (Hono+D1) | SATISFIED | `registerRouter` in `routes/register.ts`; `SubmitBody` zod schema matches all card fields |
| DIR-02 | Two-step proof-of-key-ownership; no email/OAuth/CAPTCHA | SATISFIED | `/challenge` → nonce; `/submit` → `verify()` from `web-bot-auth`; challenge burned before 201 (T-03-02 guard) |
| DIR-03 | `GET /.well-known/…/{kid}` returns JWKS with `application/http-message-signatures-directory+json`; response signed | SATISFIED | Live confirmed: correct content-type + `Signature` + `Signature-Input` headers |
| DIR-04 | `Cache-Control: public, max-age=300` (NO `immutable`); per-IP rate limit 10/day; reserved-name blocklist | SATISFIED | Live headers confirmed no `immutable`; rate-limit live; blocklist 7-test-case suite green |
| DIR-05 | Snapshot job mirrors to `/static/all.json`; cron commented out (workflow_dispatch only) | SATISFIED | `.github/workflows/snapshot.yml` ships; cron commented; `/static/all.json` live |
| DIR-07 | Zero-billing: Workers Free tier; no paid features; abuse mitigated via blocklist + rate-limit | SATISFIED | `wrangler.jsonc` has no paid bindings; D1 only; rate-limit + blocklist documented |
| DIR-08 | End-to-end flow: register → sign → Cloudflare verifier (PARTIAL accepted) | SATISFIED (PARTIAL) | `E2E-RESULT.md` STATUS: PARTIAL; internal chain proved; external Cloudflare test-key-only limitation documented per 03-RESEARCH.md §8 NOTE; verification context explicitly instructs VERIFIED for this |
| CLI-04 | `wbauth register --directory <url> --identity <path>` proof-of-ownership CLI | SATISFIED | `_do_register` + `_dispatch_register` in `cli.py`; 11 tests; Pitfall 5 sign-reuse guard active |
| CLI-05 | `wbauth serve --jwks <path>` stdlib JWKS server ≤30 exec LOC | SATISFIED | `jwks_server.py` 26 exec LOC; `wbauth keygen --jwks-output` complement (D-51) |

**Out-of-scope confirmed:** DIST-08 (Cloudflare verified-bot submission) correctly moved to Phase 5 per D-53. Not evaluated here.

---

## Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `directory/src/routes/read.ts` | WebSocket deprecation noise from workerd in vitest run | Info | Test noise only; `exception = workerd/api/web-socket.c++:821: disconnected` appears 3 times but all 20 tests pass. No behavioral impact. |

No STUB, MISSING, PLACEHOLDER, or TODO-gated implementations found in the Phase 3 delivery files. The `_http_server/__init__.py` is a proper package init (empty is intentional). No hardcoded empty returns in data paths.

---

## Human Verification Required

None. All must-haves verified programmatically against live endpoints and passing test suites.

---

## Gaps Summary

No gaps. All 9 must-haves verified. DIR-08 PARTIAL is documented, pre-approved per the verification context and 03-RESEARCH.md §8 NOTE, and deferred closure is scheduled in Phase 5 DIST-08.

---

## Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Full external Cloudflare verifier validation (arbitrary kid resolution via `Signature-Agent`) | Phase 5 | Phase 5 success criteria 6: "DIST-08: Reference demo bot registered … AND submission filed to Cloudflare's verified-bot directory" |

---

_Verified: 2026-05-10T14:30:00Z_
_Verifier: Claude (gsd-verifier)_
