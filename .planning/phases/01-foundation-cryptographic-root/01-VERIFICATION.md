---
phase: 01-foundation-cryptographic-root
verified: 2026-05-03T23:38:00Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
overrides:
  - must_have: "Russian payment card confirmed working on chosen hosting, domain registered with auto-renewal >18 months"
    reason: "User overrode during discuss-phase to zero-billing CF Workers + D1 + no domain in v1. CONTEXT.md D-01..D-04 supersede the original ROADMAP text. DIR-06 verified against corrected scope: Cloudflare account confirmed working, D1 read/write confirmed, no card required."
    accepted_by: "user (captured in CONTEXT.md D-01..D-04)"
    accepted_at: "2026-05-03T00:00:00Z"
  - must_have: "Signatures pass Cloudflare debug verifier (crawltest.com/cdn-cgi/web-bot-auth)"
    reason: "Executor discovered crawltest.com is the closed verified-bots gate requiring dashboard bot registration (out of Phase 1 scope). Switched to https://http-message-signatures-example.research.cloudflare.com/ — Cloudflare Research's open-spec verifier. IDENT-05 substance (live external Cloudflare conformance) fully preserved. Verified live: banner 'You successfully authenticated as owning the test public key' with exit 0."
    accepted_by: "user (per verification_context instructions)"
    accepted_at: "2026-05-03T20:25:00Z"
---

# Phase 1: Foundation & Cryptographic Root — Verification Report

**Phase Goal:** Establish the project skeleton on confirmed hosting and prove that the Python signer produces signatures Cloudflare accepts — the cryptographic root that gates every downstream feature.
**Verified:** 2026-05-03T23:38:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | DIR-06: Hosting confirmed working (zero-billing CF Workers + D1, no domain per CONTEXT.md D-01..D-04) | VERIFIED | HOSTING-RESULT.md STATUS: PASS; Worker deployed at wbauth-day1-test.silov801.workers.dev; D1 DB id 13e5aebd-...; GET /ping returns {"ok":true,"row_count":1}; D-01..D-04 all validated |
| 2 | IDENT-01: `wbauth keygen` produces Ed25519 keypair at 0o600; loader refuses wider perms | VERIFIED | keygen verified live: mode 100600 confirmed via stat; `_load_keypair` raises PermissionError on 0o644; `os.open(O_WRONLY|O_CREAT|O_EXCL, 0o600)` in identity.py:288; test_keygen_creates_key_at_path PASSED |
| 3 | IDENT-02: Long-lived Identity object with keypair + agent metadata | VERIFIED | `Identity.load_or_generate()` primary entrypoint at identity.py:149; round-trip generate→load→reload preserves kid (test_load_existing_returns_same_kid PASSED); https:// enforced at init |
| 4 | IDENT-03: `sign()` produces RFC 9421 + Web Bot Auth headers (Ed25519, tag="web-bot-auth", expires=created+60s) | VERIFIED | signer.py:100; WEB_BOT_AUTH_TAG="web-bot-auth" at signer.py:36; DEFAULT_EXPIRES_SECONDS=60; test vector 01 confirms `expires=created+60s`; all 13 signer tests PASSED |
| 5 | IDENT-04: Byte-equal vs spec/test-vectors/ golden files (≥5 vectors, cross-language) | VERIFIED | 5 vectors present; pytest: 25/25 byte-equality assertions PASSED (Signature, Signature-Input, Signature-Agent, kid, JWKS for each vector); vitest: 4/4 non-multi-key vectors PASSED with identical bytes vs Cloudflare web-bot-auth 0.1.3 |
| 6 | IDENT-05: Signatures pass Cloudflare debug verifier (corrected endpoint per override) | VERIFIED | Live smoke test run confirmed: `OK: Cloudflare research verifier accepted (status=200, kid=poqkLGiymh..., banner='You successfully authenticated as owning the test public key')`; wired into cloudflare-debug.yml with daily cron + per-PR |
| 7 | IDENT-06: JWKS export with kid = base64url(sha256(JWK)) per RFC 7638 | VERIFIED | `_compute_kid` in identity.py:207; RFC 7638 canonical JSON with sort_keys=True, no whitespace; SHA-256 then base64url-no-pad; canonical kid `poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U` reproduced; test_kid_matches_rfc9421_test_key PASSED |
| 8 | IDENT-07: Multi-key Identity with active + retiring overlap; old key signing blocked | VERIFIED | `Identity.rotate()` returns new Identity (immutable update) with active→retiring demotion; `_IdentityResolver` ONLY returns `_active.private_key`; double rotation drops oldest; verified live: 2-key JWKS after rotation, retiring kid not in Signature-Input |
| 9 | IDENT-08: `__repr__` and `__str__` return REDACTED | VERIFIED | `redacted_repr()` in _redaction.py:10; `__repr__ = __str__` in identity.py:195; `pickle.dumps` raises TypeError; live test: `<Identity REDACTED kid='...' sig_agent='...'>` pattern confirmed; test_repr_returns_REDACTED, test_str_returns_REDACTED, test_pickle_raises all PASSED |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `python/src/wbauth/identity.py` | Identity, KeyPair, _compute_kid, 0o600 creation | VERIFIED | 293 lines; O_EXCL at line 288; _compute_kid RFC 7638 at line 207 |
| `python/src/wbauth/signer.py` | Pure sign() with Web Bot Auth defaults | VERIFIED | 178 lines; WEB_BOT_AUTH_TAG="web-bot-auth"; DEFAULT_EXPIRES_SECONDS=60 |
| `python/src/wbauth/normalized_request.py` | NormalizedRequest dataclass | VERIFIED | 32 lines; mutable headers dict |
| `python/src/wbauth/_redaction.py` | REDACTED repr helper | VERIFIED | 19 lines; `redacted_repr()` function |
| `python/src/wbauth/cli.py` | `wbauth keygen` CLI | VERIFIED | 73 lines; subprocess-tested; entry-point in pyproject.toml |
| `python/src/wbauth/__init__.py` | Public re-exports | VERIFIED | Exports Identity, KeyPair, NormalizedRequest, sign, SignatureHeaders |
| `python/src/wbauth/_smoke/cloudflare_debug.py` | Live Cloudflare smoke test | VERIFIED | 135 lines; targets CF research verifier; banner-check logic |
| `spec/test-vectors/01-basic-get/{input,expected}.json` | GET vector | VERIFIED | kid=poqkLGiymh..., tag=web-bot-auth, expires=created+60s |
| `spec/test-vectors/02-post-with-content-digest/{input,expected}.json` | POST+content-digest vector | VERIFIED | content-digest in covered_components |
| `spec/test-vectors/03-custom-expiry/{input,expected}.json` | Custom expiry vector | VERIFIED | expires_after_seconds=300, delta=300s in expected |
| `spec/test-vectors/04-multi-uri-jwks/{input,expected}.json` | Multi-key JWKS vector | VERIFIED | jwks_full has 2 keys |
| `spec/test-vectors/05-cloudflare-quirk/{input,expected}.json` | Cloudflare quirk vector | VERIFIED | @authority lowercased from uppercase input host |
| `typescript/tests/vectors.test.ts` | Cross-language vitest oracle | VERIFIED | 4/4 vectors PASSED (multi-key skipped per design); imports from web-bot-auth/crypto |
| `.github/workflows/conformance.yml` | Cross-language CI gate | VERIFIED | 3 jobs: python-vectors, typescript-vectors, cloudflare-debug; real content (no Plan 02 stubs) |
| `.github/workflows/cloudflare-debug.yml` | Daily conformance canary | VERIFIED | push/PR/daily cron 0 12 * * * / workflow_dispatch |
| `directory/src/index.ts` | Cloudflare Worker with D1 | VERIFIED | /ping route reads from env.DB; deployed live |
| `directory/wrangler.jsonc` | Worker config with D1 binding | VERIFIED | database_id 13e5aebd-..., binding name DB |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `identity.py._generate_keypair_to` | OS file system | `os.open(O_EXCL, 0o600)` | WIRED | identity.py:288; race-free creation at mode 0o600 |
| `signer.sign()` | `http_message_signatures.HTTPMessageSigner` | `_IdentityResolver` adapter | WIRED | signer.py:157-171; key resolver bridges Identity to library |
| `signer.sign()` | `request.headers` | mutation + return | WIRED | signer.py:174-178; SignatureHeaders returned AND headers mutated |
| `_smoke.cloudflare_debug.run()` | CF research verifier | `httpx.get()` + banner parse | WIRED | cloudflare_debug.py:73-130; live verified exit 0 |
| `conformance.yml:cloudflare-debug job` | `cloudflare_debug.py` | `uv run python -m wbauth._smoke.cloudflare_debug` | WIRED | conformance.yml:33 |
| `cloudflare-debug.yml` | `cloudflare_debug.py` | `uv run python -m wbauth._smoke.cloudflare_debug` | WIRED | cloudflare-debug.yml:37; daily cron present |
| `vectors.test.ts` | `spec/test-vectors/` | `loadAllVectors()` filesystem walk | WIRED | helpers.ts + vectors.test.ts; both pytest and vitest consume same JSON files |
| `test_vectors.py` | `spec/test-vectors/` | `conftest.py:all_vector_dirs()` | WIRED | 25 byte-equality assertions PASSED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `_smoke/cloudflare_debug.py` | `response.text` | `httpx.get(CF_RESEARCH_VERIFIER_URL, headers={...})` | Yes — live HTTP to Cloudflare | FLOWING |
| `directory/src/index.ts (/ping)` | `results` | `env.DB.prepare("SELECT COUNT(*) as count FROM hello").all()` | Yes — real D1 SQLite query | FLOWING |
| `test_vectors.py` | vector dicts | `json.load(open(input.json/expected.json))` | Yes — real files from spec/test-vectors/ | FLOWING |
| `vectors.test.ts` | `v.input`, `v.expected` | `loadAllVectors()` filesystem walk + JSON.parse | Yes — real files from spec/test-vectors/ | FLOWING |

### Behavioral Spot-Checks

| Behavior | Result | Status |
|----------|--------|--------|
| `wbauth keygen --output /tmp/wbauth-verifier-test.pem` produces 0o600 file | mode 100600 (= 0o600), kid printed (43 chars) | PASS |
| `uv run pytest python/tests/ -v` — all 55 tests | 55 passed in 1.47s | PASS |
| `npm run test --workspace=wbauth` — cross-language vectors | 4 passed, 1 skipped (multi-key per design) | PASS |
| `uv run python -m wbauth._smoke.cloudflare_debug` — live CF verifier | OK: status=200, banner='You successfully authenticated...' | PASS |
| `Identity.from_test_key().kid == "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U"` | Match confirmed | PASS |
| REDACTED repr: `repr(identity)` matches regex pattern | Pattern match: True, REDACTED: True | PASS |
| Multi-key rotation: retiring key NOT used to sign | Signing uses active kid only | PASS |
| pickle.dumps(identity) raises TypeError | TypeError confirmed | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| IDENT-01 | 01-03 | Ed25519 keygen via Python API + CLI; 0o600 perms; loader refuses wider perms | SATISFIED | identity.py:_generate_keypair_to(O_EXCL,0o600); _load_keypair refuses >0o600; CLI tested via subprocess |
| IDENT-02 | 01-03 | Long-lived Identity object with keypair + agent metadata | SATISFIED | Identity class with load_or_generate, from_test_key; round-trip kid preservation |
| IDENT-03 | 01-03 | Pure sign() with RFC 9421 + Web Bot Auth headers (Ed25519, tag="web-bot-auth", expires=created+60s) | SATISFIED | signer.py:100; WEB_BOT_AUTH_TAG; DEFAULT_EXPIRES_SECONDS=60; 13 signer tests green |
| IDENT-04 | 01-04 | Byte-equal vs spec/test-vectors/ (≥5 vectors) | SATISFIED | 5 vectors; 25 Python byte-equality assertions; 4 TypeScript byte-equality assertions |
| IDENT-05 | 01-04 | Signatures pass Cloudflare debug verifier (corrected endpoint per override) | SATISFIED | Live smoke test exit 0; banner confirmed; daily cron wired |
| IDENT-06 | 01-03 | JWKS export with kid = base64url(sha256(JWK)) per RFC 7638 | SATISFIED | _compute_kid with sort_keys=True; canonical kid matches Cloudflare's published value |
| IDENT-07 | 01-03 | Multi-key Identity with rotation lifecycle (active + retiring overlap) | SATISFIED | Identity.rotate() immutable update; JWKS exports both; retiring key never signs |
| IDENT-08 | 01-03 | REDACTED __repr__ and __str__ | SATISFIED | redacted_repr() helper; pickle.dumps raises TypeError; repr pattern matched |
| DIR-06 | 01-01 | Hosting confirmed working (zero-billing variant per CONTEXT.md D-01..D-04) | SATISFIED | HOSTING-RESULT.md STATUS: PASS; live Worker + D1 confirmed |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `python/src/wbauth/cli.py` | 47 | `default="https://example.invalid/placeholder"` in `--signature-agent-url` arg | Info only | Not a stub — this is a legitimate default URL for the keygen CLI which only needs to generate the key. The `.invalid` TLD prevents accidental network use. The help text correctly explains this. |

No blockers or warnings found.

### Environment Note (Not a Gap)

The project .venv had become corrupted locally (macOS UF_HIDDEN flags on dist-info RECORD files caused uv to be unable to uninstall packages, resulting in broken RECORD-less dist-info entries and missing package directories). This was resolved during verification by deleting and rebuilding the venv. After fresh `uv sync` from `python/` and `bash scripts/post-sync.sh`, all 55 tests passed.

**This is a local dev environment issue, not a code quality issue.** CI runs on ubuntu-latest where UF_HIDDEN does not occur (macOS-only quirk). The post-sync.sh script is a no-op on Linux. The conformance.yml workflows do not need post-sync.sh.

### Human Verification Required

None. All phase behaviors are verifiable programmatically and were verified.

### Gaps Summary

No gaps. All 9 must-have truths verified, all artifacts substantive and wired, all tests pass, live Cloudflare conformance confirmed.

---

_Verified: 2026-05-03T23:38:00Z_
_Verifier: Claude (gsd-verifier)_
