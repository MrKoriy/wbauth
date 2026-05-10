---
phase: 03-hosted-directory-cloudflare-submission
plan: 01
subsystem: directory-backend
tags: [cloudflare-workers, d1, hono, web-bot-auth, rfc-9421, ed25519, deploy]
requires:
  - phase-1-signer (web-bot-auth verify path reused for proof-of-key-ownership)
  - cloudflare-account silov801@gmail.com (account_id 2a1e5d83dbc5d553a3537d7a79009899)
provides:
  - "Live Worker: https://wbauth.silov801.workers.dev"
  - "D1 database: wbauth-directory (e9bd675b-da95-4ee5-aecf-58c326cfe766)"
  - "Two-step proof-of-key-ownership registration (POST /register/challenge + /register/submit)"
  - "Signed JWKS read endpoints per draft-meunier-http-message-signatures-directory-05"
  - "Per-IP rate limit (10/IP/day) on /register/* via D1 ratelimit table"
  - "Reserved-name blocklist (12 tokens × 3 suffixes) at /register/submit"
  - "Directory's own signed JWKS at /.well-known/http-message-signatures-directory (root)"
  - "Snapshot endpoint /static/all.json for Plan 03-02 nightly mirror job"
affects:
  - "Plan 03-02 register CLI (default --directory=https://wbauth.silov801.workers.dev)"
  - "Plan 03-02 snapshot job (consumes GET /static/all.json)"
  - "Plan 03-03 E2E manual script (full register→sign→Cloudflare-verify loop)"
tech-stack:
  added: [hono@4.12.16, "web-bot-auth@0.1.3 (npm)", "@hono/standard-validator@0.2.2", "zod@4.4.3", "@cloudflare/workers-types@4.20260504.1", "@cloudflare/vitest-pool-workers@0.15.2", "vitest@4"]
  patterns:
    - "D1 .batch() for atomic UPSERT-then-SELECT rate-limit increment + cleanup-on-write"
    - "Lazy module-level cached signer keyed by JWK secret string (warm-isolate optimization)"
    - "Nonce burn BEFORE 201 response (regression-guarded)"
    - "Hono onError global handler returning generic {error:'internal'} (V7 ASVS)"
    - "wrangler-managed D1 migrations under directory/migrations/ (no schema.sql)"
key-files:
  created:
    - directory/src/env.ts
    - directory/src/blocklist.ts
    - directory/src/ratelimit.ts
    - directory/src/signing.ts
    - directory/src/schemas.ts
    - directory/src/routes/register.ts
    - directory/src/routes/read.ts
    - directory/src/index.ts (replaced Phase-1 hello-world)
    - directory/tests/blocklist.test.ts
    - directory/tests/ratelimit.test.ts
    - directory/tests/handlers.test.ts
    - directory/tests/verify.test.ts
    - directory/migrations/0001_create_agents.sql
    - directory/migrations/0002_create_registration_challenges.sql
    - directory/migrations/0003_create_ratelimit.sql
    - directory/tsconfig.json
    - directory/vitest.config.ts
    - directory/README.md
    - python/scripts/generate_directory_jwk.py
  modified:
    - directory/package.json (added hono, web-bot-auth, zod, @hono/standard-validator + dev deps)
    - directory/wrangler.jsonc (D-33 worker name, D-34 D1 binding, observability enabled)
    - package-lock.json (root, npm workspaces)
  deleted:
    - directory/schema.sql (replaced by managed migrations per D-55)
decisions:
  - "Framework: Hono 4.12.16 (D-54) — minimal Workers-native router with sValidator for zod"
  - "Migrations: wrangler-managed (D-55) — directory/migrations/0001-0003.sql; schema.sql deleted"
  - "Rotation procedure: documented in directory/README.md (D-56)"
  - "Module organization: src/{routes/,blocklist.ts,ratelimit.ts,signing.ts,schemas.ts,env.ts,index.ts} (D-57) — flat under src/ with routes/ subdir, single concern per file"
  - "Open Question #2 resolved: secret stored as JSON-stringified JWK with d field (NOT PKCS8 PEM) — web-bot-auth/crypto.signerFromJWK accepts JWK natively; sidesteps Workers WebCrypto Ed25519 PKCS8 import ambiguity"
  - "Open Question #1 resolved: directory's own JWKS published at root /.well-known/http-message-signatures-directory (no kid suffix); per-agent JWKS at /.well-known/http-message-signatures-directory/{kid}"
  - "Open Question #5 resolved: blocklist substring check is case-insensitive (lowercase candidate then includes())"
  - "Blocklist enforcement location: /register/submit only (NOT /register/challenge) — see Design Notes below"
metrics:
  duration: "~120 min total (Tasks 1+2 implementation ~90 min, Task 3 deploy + smoke ~30 min including human-action gate)"
  completed-date: "2026-05-04"
  tasks: 3
  files-created: 18
  files-modified: 3
  files-deleted: 1
  test-count: "20/20 vitest pass (local @cloudflare/vitest-pool-workers)"
  src-loc: 516 (8 src/ files)
  test-loc: 450 (4 tests/ files)
---

# Phase 3 Plan 01: Directory Backend Summary

Production Cloudflare Worker `wbauth` deployed to `https://wbauth.silov801.workers.dev` with D1-backed two-step registration, Ed25519-signed JWKS read endpoints per draft-meunier-http-message-signatures-directory-05, per-IP rate limiting, and reserved-name blocklist — the cryptographic root that Plans 03-02 and 03-03 depend on.

## Live Deployment

| Field | Value |
| --- | --- |
| Worker URL | `https://wbauth.silov801.workers.dev` |
| Worker name (D-33) | `wbauth` |
| Cloudflare account | silov801@gmail.com (`2a1e5d83dbc5d553a3537d7a79009899`) |
| Version ID | `4fce28b9-cf13-4713-98f1-5efef6f41d43` |
| D1 database name (D-34) | `wbauth-directory` |
| D1 database ID | `e9bd675b-da95-4ee5-aecf-58c326cfe766` |
| D1 region | WEUR |
| Migrations applied to --remote | `0001_create_agents.sql`, `0002_create_registration_challenges.sql`, `0003_create_ratelimit.sql` |
| Secret name (D-42) | `DIRECTORY_PRIVATE_JWK` (provisioned via piped stdin — never touched filesystem) |
| Directory's published kid | `UeCLA_Q47BCqq9eB6T7gPaLnVJ1gpNyDI4Vi4bUanZw` |
| Directory's published x | `jY4krL4NJGGxm4T3HI1zHG53WwBQkViTN73BCjfKisI` |

## Smoke Test Results (live Worker)

All 4 endpoints from the success-criteria block pass on the deployed Worker:

```
GET /.well-known/http-message-signatures-directory
→ 200 OK
{"keys":[{"kty":"OKP","crv":"Ed25519","kid":"UeCLA_Q47BCqq9eB6T7gPaLnVJ1gpNyDI4Vi4bUanZw","x":"jY4krL4NJGGxm4T3HI1zHG53WwBQkViTN73BCjfKisI"}]}

GET /agents
→ 200 OK
{"page":1,"count":0,"agents":[]}

POST /register/challenge {"kid":"<≥20-char>","client_name":"any"}
→ 200 OK
{"challenge":"<32-hex>","expires_at":<ts+300>}

POST /register/challenge {"kid":"<short>"}
→ 400 (zod structured error — schema rejection)
```

Live Worker confirms zod validation, D1 binding (`env.DB`), challenge nonce generation, and signed JWKS serving all functional end-to-end.

## Test Suite

`cd directory && npx vitest run` → **20/20 pass** across 4 test files using `@cloudflare/vitest-pool-workers` with isolated D1 per test:

| Test file | Coverage |
| --- | --- |
| `tests/blocklist.test.ts` | Exact-match (`google` → "google"), case-insensitive (`Google` → "google"), substring+suffix (`openai-bot` → "openai"), V4 ASVS false-positive guard (`googlestyle-app` → null), legitimate-bot guard (`legitimate-bot` → null) |
| `tests/ratelimit.test.ts` | 10 calls allowed, 11th rejected, distinct IP starts fresh, cleanup-on-write of stale day_buckets |
| `tests/handlers.test.ts` | `/healthz`, challenge happy/sad path, agents 404/empty-list, JWKS root + per-kid 404, T-03-02 nonce-burn-before-response regression |
| `tests/verify.test.ts` | web-bot-auth verify happy path, signature_invalid rejection on tampered byte |

## Commits Landed

| Commit | Scope | Files |
| --- | --- | --- |
| `c02c38a` | feat(03-01): scaffold Phase 3 directory worker (deps + wrangler config + D1 migrations + JWK gen script) | wrangler.jsonc, package.json, tsconfig.json, vitest.config.ts, migrations/0001-0003, generate_directory_jwk.py, schema.sql DELETED |
| `9b22f33` | feat(03-01): implement directory worker handlers + tests (DIR-01..04, DIR-07) | 8 src/ files, 4 tests/ files, README |
| `bcb0ebb` | chore(03-01): wire wbauth-directory D1 database_id into wrangler.jsonc | wrangler.jsonc (placeholder → real id) |
| _this commit_ | docs(03-01): complete directory backend plan (deployed + smoke-tested) | SUMMARY.md, STATE.md, ROADMAP.md, REQUIREMENTS.md, checkpoint deletion |

## Design Notes — Blocklist Enforcement Location (Soft Gap Surfaced During Smoke)

**Observation during deploy smoke-test:** `POST /register/challenge` with `client_name: "google-bot"` returned a valid `{challenge, expires_at}` (200 OK) instead of being rejected as a reserved name.

**Code review of `directory/src/routes/register.ts` confirms:**

- The `/challenge` handler validates the kid via zod, gates on rate-limit, and issues a 16-byte hex nonce. It does **NOT** check the blocklist.
- The `/submit` handler enforces the blocklist (line 74-85) BEFORE any expensive crypto work but after the rate-limit gate.

**Design rationale (intentional):**

1. The challenge endpoint accepts only `{kid}` per `ChallengeBody` zod schema — no `client_name` is collected or validated at this step. The `client_name` only appears in `SubmitBody`. So the blocklist physically cannot be checked until /submit. (The orchestrator's smoke-test was sending `client_name` in the challenge body — zod silently strips unknown fields, which is why no error fired.)
2. Blocklist enforcement at the commitment point (where the agents row would be created) avoids leaking blocklist policy at a cheap probe step. An attacker enumerating reserved tokens would need to burn a full registration cycle (kid + challenge + signed submit) per probe.
3. Per-IP rate limit (10/IP/day) gates BOTH /challenge and /submit, so the cheap-probe attack is structurally bounded regardless.

**Conclusion:** This matches D-43/D-44 intent — the blocklist must reject reserved registrations, not reserved nonce requests. **No code change needed.** Documented here so Plan 03 verifier knows to expect this behavior. The full register→submit flow with `client_name: "google"` returning HTTP 422 is exercised by `tests/handlers.test.ts` and is the authoritative gate.

**Soft gap for Plan 03 verifier to reassess:** if a future requirement says "do not even let an agent enumerate reserved names via challenge", we'd need to either (a) move `client_name` into ChallengeBody and gate there too, or (b) tighten the rate limit. Neither is required by the current plan's must_haves.

## Deviations from Plan

### Auto-fixed Issues

None. The plan executed as written. Only non-trivial implementation choice was Open Question #2 resolution (JWK secret format vs PKCS8 PEM) which was already locked in the plan's constraints — deciding to JSON-stringify the JWK directly proved clean: `web-bot-auth/crypto.signerFromJWK` accepts the parsed object natively, no PEM/PKCS8 parsing needed in the Worker.

### Authentication Gates

One — Task 3 (Deploy + smoke). The executor cannot run `npx wrangler secret put` interactively from inside the agent loop, so the plan was structured with a `checkpoint:human-verify` gate (downgraded to human-action for the secret put step). The orchestrator drove the three live-Cloudflare commands on the user's behalf:

1. JWK generation + secret upload via stdin pipe (no key material on disk)
2. `npx wrangler deploy`
3. 4-curl smoke-test against the published URL

All three completed successfully; results recorded in the Smoke Test Results section above.

## Hand-off Notes for Plan 03-02

**Live URL contract** (Plan 03-02 register CLI should use this as default `--directory`):

```
https://wbauth.silov801.workers.dev
```

**Endpoint contracts** Plan 03-02 will consume:

| Endpoint | Request | Response |
| --- | --- | --- |
| `POST /register/challenge` | `{"kid": "<base64url 20-80 chars>"}` JSON body | `{"challenge": "<32-hex>", "expires_at": <unix-ts+300>}` |
| `POST /register/submit` | Full SubmitBody zod schema (kid, challenge, client_name, client_uri?, signature_agent_url, expected_user_agent?, contacts?, purpose?, targeted_content?, rate_control?, keys{keys[]}); request MUST be RFC 9421-signed by the kid's private key | `201 {"kid": ..., "directory_url": "https://wbauth.silov801.workers.dev/.well-known/http-message-signatures-directory/<kid>"}` |
| `GET /.well-known/http-message-signatures-directory/{kid}` | None | `200` JWKS + `Signature` + `Signature-Input` headers, `cache-control: public, max-age=300` (NO immutable per Pitfall 1) |
| `GET /static/all.json` | None | `{"generated_at": <unix-ts>, "agents": [...]}` — full snapshot for nightly mirror job |
| `GET /agents` | optional `?page=N&all=true` | Paginated 50/page or up to 10000 with all=true |
| `GET /agents/{kid}` | None | Full Signature Agent Card JSON, unsigned, `cache-control: public, max-age=60` |

**Rate-limit budget** for Plan 03-02 register CLI tests: 10 register attempts per IP per day. Smoke-tests should reuse the same kid (UPSERT idempotent) to avoid burning the budget against unique IPs.

**Per-IP rate-limit shares budget across `/register/challenge` AND `/register/submit`** — a register CLI attempt costs 2 against the 10/day cap. Plan 03-02 should account for this (5 full register attempts per IP per day max).

**Directory's own published kid** (Plan 03-03 may verify the directory response signature against this):

```
UeCLA_Q47BCqq9eB6T7gPaLnVJ1gpNyDI4Vi4bUanZw
```

Available for fetch at `GET /.well-known/http-message-signatures-directory` (root, no kid suffix).

**D1 schema** for any Plan 03-02 / 03-03 utility that needs to introspect (read-only via `npx wrangler d1 execute wbauth-directory --remote --command "..."`):

- `agents` — kid PK + 11 columns per D-36
- `registration_challenges` — kid PK + nonce + expires_at
- `ratelimit` — (ip, day_bucket) compound PK + count

## Threat Model Coverage

All 15 threats from the plan's `<threat_model>` STRIDE register are mitigated or accepted as documented. Quick audit:

- **T-03-01..T-03-06 (Spoofing/Tampering):** Mitigated via web-bot-auth verify, nonce burn, blocklist (with caveat above), Worker-secret signing, parameterized D1 binds, and signed JWKS responses.
- **T-03-07 (Repudiation):** Accepted per Web Bot Auth threat model.
- **T-03-08 (Verbose error leakage):** `app.onError` returns generic 500 — verified in src/index.ts grep.
- **T-03-09 (Secret exposure):** Generation script prints JWK to stdout once with explicit private-terminal warning; orchestrator deployed via piped stdin so secret never landed on disk.
- **T-03-10..T-03-13 (DoS):** Rate-limit + cleanup-on-write + Free-tier cap acceptance.
- **T-03-14, T-03-15 (Elevation of privilege):** Cryptographic kid-thumbprint pinning + atomic D1 batch.

No new threats discovered during execution. No threat flags raised.

## Self-Check: PASSED

Files created:

```
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/directory/src/env.ts
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/directory/src/blocklist.ts
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/directory/src/ratelimit.ts
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/directory/src/signing.ts
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/directory/src/schemas.ts
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/directory/src/routes/register.ts
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/directory/src/routes/read.ts
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/directory/src/index.ts
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/directory/tests/blocklist.test.ts
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/directory/tests/ratelimit.test.ts
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/directory/tests/handlers.test.ts
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/directory/tests/verify.test.ts
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/directory/migrations/0001_create_agents.sql
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/directory/migrations/0002_create_registration_challenges.sql
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/directory/migrations/0003_create_ratelimit.sql
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/directory/README.md
[FOUND] /Users/leonid/Documents/coding/Vibecoded/YC/python/scripts/generate_directory_jwk.py
[ABSENT-AS-EXPECTED] /Users/leonid/Documents/coding/Vibecoded/YC/directory/schema.sql (deleted per D-55)
```

Commits:

```
[FOUND] c02c38a feat(03-01): scaffold Phase 3 directory worker
[FOUND] 9b22f33 feat(03-01): implement directory worker handlers + tests
[FOUND] bcb0ebb chore(03-01): wire wbauth-directory D1 database_id into wrangler.jsonc
```

Live URL:

```
[REACHABLE] https://wbauth.silov801.workers.dev/.well-known/http-message-signatures-directory → 200 + JWKS w/ kid UeCLA_Q47BCqq9eB6T7gPaLnVJ1gpNyDI4Vi4bUanZw
```
