---
gsd_state_version: 1.0
milestone: v1.1.1
milestone_name: milestone
status: executing
stopped_at: Phase 3 Plan 02 complete (register CLI + serve + snapshot workflow)
last_updated: "2026-05-10T13:35:00.000Z"
last_activity: 2026-05-10 -- Phase 03 Plan 02 complete (wbauth register/serve + GH Actions snapshot)
progress:
  total_phases: 5
  completed_phases: 2
  total_plans: 10
  completed_plans: 9
  percent: 90
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-03)

**Core value:** AI-агенты получают идентичность и знают свои права на сайте — до того, как сделают первый запрос. Если ничего другое не работает, эти две вещи (signed identity + pre-flight policy) должны работать в одну строку импорта.
**Current focus:** Phase 03 — hosted-directory-cloudflare-submission

## Current Position

Phase: 03 (hosted-directory-cloudflare-submission) — EXECUTING
Next phase: 03 (Hosted Directory & Cloudflare Submission)
Plan: 3 of 3 (next: 03-03 E2E exit gate)
Status: Executing Phase 03 (Plans 03-01 + 03-02 complete; CLI surface shipped, snapshot workflow ready)
Last activity: 2026-05-10 -- Phase 03 Plan 02 complete (wbauth register + serve + snapshot workflow)

Progress: [██████▋···] 67% (2/3 plans complete in Phase 3)

## Performance Metrics

**Velocity:**

- Total plans completed: 4
- Average duration: ~10min
- Total execution time: ~40min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundation & Cryptographic Root | 4 | ~40min | ~10min |
| 2. Python Adapters & Policy Inspector | 0 | — | — |
| 3. Hosted Directory & Cloudflare Submission | 0 | — | — |
| 4. TypeScript SDK & Framework Integrations | 0 | — | — |
| 5. Pre-Army Hardening, Docs & Launch | 0 | — | — |

**Recent Trend:**

- Last 5 plans: 01-01 (~5min), 01-02 (~10min), 01-03 (~7m 39s), 01-04 (~17m 8s)
- Trend: 01-04 was longest in the phase; deviation #1 (Cloudflare verifier endpoint discovery) added ~5 min of empirical investigation. Rest of phase steady ~7-10 min/plan.

*Updated after each plan completion*
| Phase 01 P01 | 5min | 3 tasks | 8 files |
| Phase 01 P02 | 10min | 3 tasks + 1 fix | 24 files created, 4 modified, 1 deleted |
| Phase 01-foundation-cryptographic-root P03 | 7m 39s | 3 tasks | 8 files |
| Phase 01-foundation-cryptographic-root P04 | 17m 8s | 3 tasks + 4 deviations | 16 files created, 2 modified |
| Phase 02-python-adapters-policy-inspector P01 | 30min | 3 tasks | 10 files |
| Phase 02-python-adapters-policy-inspector P02 | 30min | 3 tasks + 2 deviations | 24 created, 1 modified |
| Phase 02-python-adapters-policy-inspector P03 | 25min | 3 tasks + 1 deviation | 4 created, 3 modified, 1 renamed |
| Phase 03-hosted-directory-cloudflare-submission P01 | ~120min | 3 tasks (incl. human-action deploy gate) + 0 deviations | 18 created, 3 modified, 1 deleted |
| Phase 03-hosted-directory-cloudflare-submission P02 | ~50min | 3 tasks + 3 auto-fixed deviations | 9 created, 1 modified |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Key decisions affecting current work (from PROJECT.md):

- Identity + Policy hybrid (not pure identity) — combined value claim is the wedge
- Python first, TypeScript parallel via agents — TS via shared test vectors
- Hosted directory simple (FastAPI + Postgres/SQLite) — must run unattended through army leave
- Drop-in API: client-construction helper + one function — `WebBotAuth(identity)` and `inspect(url)`
- OSS-first under Apache 2.0, no paywall in v1 — maximize star velocity
- Coarse granularity, 5 phases (not 7 from research) — collapsed Phase-0 hosting test into Phase 1, merged hardening + distribution into Phase 5
- [Phase ?]: Day-1 hosting validated on Cloudflare: Worker live at wbauth-day1-test.silov801.workers.dev, D1 read confirmed, no card required (D-01..D-04 locked)
- [Phase ?]: directory/ uses npm (pnpm absent on dev machine); Plan 02 must reconcile npm vs pnpm lockfile
- [Phase 1 Plan 02]: D-10 amended — npm workspaces (root package.json) over pnpm workspaces (no pnpm-workspace.yaml). Lockfile is package-lock.json at root; per-workspace lockfiles deleted.
- [Phase 1 Plan 02]: CLI command renamed from original-draft to `wbauth` across REQUIREMENTS.md and ROADMAP.md (sub-decision per orchestrator brief). Package + import + CLI all share the name `wbauth`.
- [Phase 1 Plan 02]: Pinned Python 3.13 via .python-version for reproducibility; macOS dev machines need scripts/post-sync.sh after every `uv sync` (clears UF_HIDDEN flag set by uv on editable .pth; Python 3.13+ skips hidden .pth per CPython security policy GH-99458).
- [Phase ?]: RFC 7638 thumbprint computation centralized in _compute_kid (canonical JWK ordering, base64url-no-pad SHA-256)
- [Phase ?]: Pure-function signer with belt-and-suspenders https:// re-check (Identity.__init__ enforces, sign() re-checks defensively)
- [Phase ?]: Subprocess tests for CLI entry point — exercises pyproject.toml [project.scripts] registration, not just main(argv=...) in-process
- [Phase ?]: scripts/post-sync.sh now recursively un-hides every UF_HIDDEN entry in site-packages (uv hides every file it writes, not just .pth)
- [Phase ?]: Implementation-time A3/A4/A6 verified live: alg="ed25519" lowercase, Ed25519PrivateKey accepted directly, tag="web-bot-auth" auto-quoted by http_sfv
- [Phase 1 Plan 04]: Live verifier endpoint corrected from crawltest.com (closed verified-bots gate, requires manual CF bot registration) to https://http-message-signatures-example.research.cloudflare.com/ (open-spec verifier, returns 200 + success banner). RESEARCH §6 and CONTEXT critical_constraints #5 superseded by empirical finding; IDENT-05 substance preserved.
- [Phase 1 Plan 04]: Cross-language byte-equality oracle locked: Python http-message-signatures 2.0.1 and TS web-bot-auth 0.1.3 produce IDENTICAL Signature-Input + Signature for all 4 active-key vectors; no A8 conformance direction needed.
- [Phase 1 Plan 04]: Vector nonces are 64-byte base64 strings (TS web-bot-auth validates length via NONCE_LENGTH_IN_BYTES=64). Vector 04 retiring key uses fixed 32-byte ASCII seed for byte-stable JWKS regeneration.
- [Phase 1 Plan 04]: signerFromJWK lives at "web-bot-auth/crypto" subpath — NOT at the main "web-bot-auth" entry. Caught at first vitest run; documented in vectors.test.ts.
- [Phase 1 Plan 04]: Daily canary cron added (.github/workflows/cloudflare-debug.yml) — Pitfall 12 mitigation for army-leave window. Phase 5 HARDEN-04 layers Discord+GitHub-issue alerts on top.
- [Phase ?]: Adapters use direct submodule imports (wbauth.signer, wbauth.normalized_request) to avoid circular import via wbauth/__init__.py re-exports
- [Phase ?]: Content-Digest auto-computation lives in wbauth.adapters._utils.ensure_content_digest (not in signer); fulfills Phase-1 signer's TODO for POST/PUT/PATCH body requests
- [Phase ?]: Plan 02-01 frontloaded all Phase-2 runtime + dev deps (cachetools, playwright, protego, requests; pytest-httpx, responses) so 02-02 stays append-only on pyproject.toml
- [Phase 3 Plan 01]: Worker `wbauth` deployed live at https://wbauth.silov801.workers.dev (version 4fce28b9-cf13-4713-98f1-5efef6f41d43); D1 `wbauth-directory` (e9bd675b-da95-4ee5-aecf-58c326cfe766) seeded with 3 migrations; DIRECTORY_PRIVATE_JWK provisioned via piped stdin (no key on disk). Directory's published kid: UeCLA_Q47BCqq9eB6T7gPaLnVJ1gpNyDI4Vi4bUanZw.
- [Phase 3 Plan 01]: Hono 4.12.16 chosen as Worker framework (D-54); managed wrangler migrations under directory/migrations/ replace Phase-1 schema.sql (D-55); rotation procedure documented in directory/README.md (D-56); module organization src/{routes/,blocklist,ratelimit,signing,schemas,env,index} flat-with-routes-subdir (D-57).
- [Phase 3 Plan 01]: DIRECTORY_PRIVATE_JWK stored as JSON-stringified JWK (kty,crv,kid,d,x) — NOT PKCS8 PEM (Open Question #2 resolution); web-bot-auth/crypto.signerFromJWK accepts JWK natively, sidesteps Workers WebCrypto Ed25519 PKCS8 import ambiguity.
- [Phase 3 Plan 01]: Blocklist enforcement at /register/submit only (NOT /register/challenge) — challenge body schema doesn't carry client_name; per-IP rate limit (10/IP/day shared across challenge+submit) bounds enumeration. Documented in 03-01-SUMMARY.md as design choice; soft-gap noted for verifier reassessment.
- [Phase 3 Plan 02]: `_do_register` two-load pattern for canonical Signature-Agent URL (T-03-17 mitigation): first load_or_generate with placeholder URL to read deterministic kid, second load_or_generate with canonical kid-aware URL so produced signature commits to it.
- [Phase 3 Plan 02]: `_do_register` Content-Digest pre-compute via existing `wbauth.adapters._utils.ensure_content_digest` — signer auto-includes `content-digest` covered component for POST+body but requires header pre-set; deviation Rule 1 caught by failing test, fixed by reusing Phase 2 helper (no new code).
- [Phase 3 Plan 02]: `wbauth serve` final executable LOC = 26 (D-50 cap is ≤30); achieved by single-line docstring + `#` comment block (LOC counter excludes `#`-prefixed lines but counts docstring CONTENT lines).
- [Phase 3 Plan 02]: snapshot.yml ships with workflow_dispatch only; schedule.cron commented out until Phase 5 D-08 resolves (Open Question #3 / Pitfall 7 mitigation — prevents daily "scheduled workflow failed" emails during army leave).
- [Phase 3 Plan 02]: Pre-existing macOS subprocess flake in tests/test_cli_keygen.py logged in deferred-items.md DEF-03-01; affects 3 of 195 tests on macOS only (CI on Ubuntu unaffected; in-process tests all green).

### Pending Todos

None yet.

### Blockers/Concerns

- **Day-1 hosting card test (Phase 1, Plan 1)**: Russian payment card acceptance on Fly.io is unconfirmed. If rejected, fallback decision tree is Railway → Cloudflare Workers+D1 (forces TypeScript directory rewrite). Resolve before any signer code is written.
- **Cloudflare verified-bot submission timeline**: Opaque external dependency, must be filed on Day 1 of Phase 3 (week 4-ish), not at phase end. Approval by army leave is best-effort; document live demo bot status honestly if not approved in time.
- **Browser Use Playwright `Page` accessibility**: MEDIUM confidence per research. Run 1-hour spike on Day 1 of Phase 2 before committing to adapter design.
- **Requirement count discrepancy**: REQUIREMENTS.md states 47 v1 requirements but actual count across categories is 52. Update REQUIREMENTS.md coverage line at next opportunity.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-05-10T13:35:00.000Z
Stopped at: Phase 3 Plan 02 complete (CLI surface + snapshot workflow shipped)
Resume file: .planning/phases/03-hosted-directory-cloudflare-submission/03-03-PLAN.md (or wherever the E2E exit-gate plan lives)
Next plan: 03-03 (E2E exit gate D-52). Imports `_do_register` from `wbauth.cli`. Hand-off notes in 03-02-SUMMARY.md.
