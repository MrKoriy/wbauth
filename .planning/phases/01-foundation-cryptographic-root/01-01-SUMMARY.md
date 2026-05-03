---
phase: 01-foundation-cryptographic-root
plan: 01
subsystem: infra
tags: [cloudflare-workers, d1, wrangler, typescript, hosting]

# Dependency graph
requires: []
provides:
  - Day-1 hosting baseline confirmed (DIR-06): Cloudflare Workers + D1 free tier verified end-to-end on developer's account
  - Live `*.workers.dev` URL serving a hello-world handler reading from D1
  - `directory/` workspace skeleton (TypeScript, wrangler 4.87.0) — Phase 3 will replace `src/index.ts` with the real JWKS backend
  - Provisioned remote D1 database `wbauth-day1-test` (id 13e5aebd-4999-4333-9a23-7fd7fb75549a, region EEUR)
  - Recorded `01-01-HOSTING-RESULT.md` artifact validating D-01..D-04
affects:
  - 01-02 (monorepo scaffold) — must include `directory/` as workspace member; should reconcile npm-vs-pnpm lockfile
  - 01-03 / 01-04 (downstream Phase 1 plans) — unblocked
  - Phase 3 (hosted directory) — will reuse this `directory/` workspace and replace `src/index.ts`

# Tech tracking
tech-stack:
  added:
    - "wrangler 4.87.0 (Cloudflare CLI, devDependency in directory/)"
    - "Cloudflare Workers (free tier) — TypeScript fetch handler runtime"
    - "Cloudflare D1 (free tier) — managed SQLite with auto-backup"
  patterns:
    - "Worker fetch handler reads from D1 via `env.DB.prepare(...).all<T>()` typed binding"
    - "wrangler.jsonc binding name in code is `DB` (short, idiomatic) — NOT the auto-suggested verbose `wbauth_day1_test`"
    - "Phase 1 throwaway code in `directory/src/index.ts` to be replaced wholesale by Phase 3 (boundary documented in directory/README.md)"

key-files:
  created:
    - "directory/wrangler.jsonc — Worker config + D1 binding"
    - "directory/schema.sql — D1 schema for `hello` smoke-test table"
    - "directory/src/index.ts — Worker fetch handler with `/` and `/ping` routes"
    - "directory/package.json — wrangler devDependency"
    - "directory/README.md — Phase 1 vs Phase 3 boundary"
    - "directory/.gitignore — node_modules/, .wrangler/, dist/"
    - "directory/package-lock.json — npm lockfile (Plan 02 may swap for pnpm-lock.yaml)"
    - ".planning/phases/01-foundation-cryptographic-root/01-01-HOSTING-RESULT.md — STATUS: PASS record"
  modified: []

key-decisions:
  - "Used npm instead of pnpm (Rule 3 — pnpm not installed on dev machine; deferred to Plan 02 for monorepo lockfile reconciliation)"
  - "D1 binding name in code is `DB`, not the auto-suggested `wbauth_day1_test` (matches plan template; idiomatic short name)"
  - "Added directory/.gitignore (Rule 2 — without it, node_modules/ would be committable; root .gitignore deferred to Plan 02)"

patterns-established:
  - "Worker code uses typed D1 generics: `env.DB.prepare(...).all<{ count: number }>()`"
  - "wrangler config uses `.jsonc` (commented JSON) format per Cloudflare's current default"
  - "Throwaway-Phase-1 code is colocated with permanent workspace path (no `directory-day1/` rename) so Phase 3 can replace files in place"

requirements-completed: [DIR-06]

# Metrics
duration: ~5min
completed: 2026-05-03
---

# Phase 1 Plan 01: Day-1 Hosting Confirmation Summary

**Cloudflare Workers + D1 free-tier hosting validated end-to-end on developer's account: live `wbauth-day1-test.silov801.workers.dev` Worker reads a seeded row from D1 via `env.DB.prepare(...)`, unblocking the entire zero-billing architecture (D-01..D-04) for Phase 1.**

## Performance

- **Duration:** ~5 min (executor wall time after human-action checkpoint completed)
- **Started:** 2026-05-03T15:27:Z (executor invocation)
- **Completed:** 2026-05-03T15:31:41Z
- **Tasks:** 3 (Task 1 = human-action gate, completed by user before executor spawned; Tasks 2-3 autonomous)
- **Files modified:** 8 (7 created in directory/, 1 created in .planning/)

## Accomplishments

- **DIR-06 satisfied.** Hosting platform proven working end-to-end (account → CLI auth → Worker deploy → D1 read).
- **Zero-billing locked decisions validated.** D-01 (no card), D-02 (TS-on-Workers + D1), D-03 (no custom domain — using `silov801.workers.dev`), D-04 (Cloudflare-only protocol satisfied without VPN or fallback).
- **`directory/` workspace member created** with throwaway code at the canonical path Phase 3 will reuse (no `directory-day1/` throwaway-rename).
- **Live D1 round-trip confirmed:** `GET /ping` on the deployed Worker returns `{"ok":true,"row_count":1}` reading the seeded `hello` table.
- **Phase 1 unblocked.** Plans 01-02, 01-03, 01-04 may proceed in Wave 2+.

## Task Commits

1. **Task 1: Cloudflare account signup + wrangler login** — completed by user before executor was spawned (no executor commit; verified via `npx wrangler whoami` returning `silov801@gmail.com` / Account ID `2a1e5d83dbc5d553a3537d7a79009899`).
2. **Task 2: Scaffold directory/ workspace and provision D1 database** — `a57a1f3` (feat)
3. **Task 3: Deploy Worker and verify end-to-end (record result file)** — `320e165` (feat)

**Plan metadata commit:** to be added by `<final_commit>` step (this SUMMARY + STATE.md + ROADMAP.md + REQUIREMENTS.md).

## Files Created/Modified

- `directory/wrangler.jsonc` — Worker config; binds D1 database `wbauth-day1-test` (id `13e5aebd-4999-4333-9a23-7fd7fb75549a`) as `env.DB`; compatibility_date `2026-05-01`
- `directory/schema.sql` — Creates `hello (id, message, created_at)` table; seeds one row `'Day 1 works'`
- `directory/src/index.ts` — Fetch handler: `GET /` returns `"Day 1 hello-world"`; `GET /ping` queries D1 and returns row count
- `directory/package.json` — Name `wbauth-directory`, private, ESM, wrangler ^4.87.0 devDep
- `directory/package-lock.json` — npm lockfile (Plan 02 should reconcile vs pnpm-workspace expectations)
- `directory/README.md` — Documents Phase 1 throwaway / Phase 3 replacement boundary per D-02
- `directory/.gitignore` — Excludes node_modules/, .wrangler/, dist/, .dev.vars
- `.planning/phases/01-foundation-cryptographic-root/01-01-HOSTING-RESULT.md` — `STATUS: PASS` record with deployed URL, database_id, account email, and validation of D-01..D-04

## Decisions Made

- **npm instead of pnpm.** The dev machine has no `pnpm` binary on PATH (only `npm` 10.9.7 with Node 22.22.2). The plan reads `pnpm install` / `pnpm add -D wrangler`; substituted `npm install`. Result: `directory/package-lock.json` exists where the plan implied `directory/pnpm-lock.yaml`. Plan 02 must decide whether to install pnpm system-wide and convert, or accept npm and update D-10 / Plan 02 monorepo notes accordingly. Either path works; the wrangler install itself is identical.
- **Bound D1 namespace name `DB`** in `wrangler.jsonc`, matching the plan's `<interfaces>` template, NOT the auto-emitted `wbauth_day1_test` from `wrangler d1 create`. The plan template was authoritative.
- **Added `directory/.gitignore`** so `node_modules/` doesn't slip into commits. Repo root has no `.gitignore` yet (deferred to Plan 02 monorepo setup).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Substituted `npm install` for `pnpm install`**
- **Found during:** Task 2 (scaffold directory/)
- **Issue:** `pnpm` not present on dev machine; `cd directory && pnpm install` returned `command not found: pnpm`. Without a working install, wrangler couldn't be invoked.
- **Fix:** Used `npm install` (npm 10.9.7 already on PATH). wrangler 4.87.0 installed identically. Lockfile is `package-lock.json` instead of `pnpm-lock.yaml`. Documented in HOSTING-RESULT.md "Environment Notes" and flagged for Plan 02 reconciliation.
- **Files modified:** `directory/package-lock.json` (created by npm)
- **Verification:** `npx wrangler --version` resolves to 4.87.0 from `directory/node_modules/.bin/wrangler`; all wrangler commands in the plan executed successfully.
- **Committed in:** `a57a1f3` (Task 2 commit)

**2. [Rule 2 — Missing critical] Added `directory/.gitignore`**
- **Found during:** Task 2 (after `npm install` produced `node_modules/`)
- **Issue:** Plan didn't specify a gitignore. Without it, `node_modules/` (~35 packages, several MB) would be committable, and `.wrangler/` cache + `.dev.vars` (potentially containing secrets in future) had no exclusion.
- **Fix:** Added `directory/.gitignore` covering `node_modules/`, `.wrangler/`, `.dev.vars`, `dist/`. (Root-level `.gitignore` is Plan 02's responsibility per monorepo decision D-10.)
- **Files modified:** `directory/.gitignore`
- **Verification:** `git status --short` post-commit shows no `node_modules/` entries.
- **Committed in:** `a57a1f3` (Task 2 commit)

**3. [Rule 1 — Bug] Fixed `STATUS: PASS` literal in HOSTING-RESULT.md**
- **Found during:** Task 3 verification step
- **Issue:** Initial result file had `**STATUS:** PASS` (markdown bold around `STATUS:`). The plan's automated `<verify>` block runs `grep -q "STATUS: PASS"` which requires the literal substring `STATUS: PASS` (no `**` in between). The grep failed, breaking the verification gate.
- **Fix:** Changed to `**STATUS: PASS**` (bolding wraps the entire literal phrase). Both renders identically in Markdown and now satisfies the literal grep.
- **Files modified:** `.planning/phases/01-foundation-cryptographic-root/01-01-HOSTING-RESULT.md` (line 4)
- **Verification:** Re-ran the full Task 3 verify block — `ALL VERIFICATION CHECKS PASS`.
- **Committed in:** `320e165` (Task 3 commit)

---

**Total deviations:** 3 auto-fixed (1 blocking, 1 missing critical, 1 bug)
**Impact on plan:** All three were small, mechanical, and necessary to complete the plan as designed. The npm/pnpm divergence is the only one with downstream impact — Plan 02 inherits it as a monorepo-tooling decision.

## Issues Encountered

- **None blocking.** Cloudflare signup, OAuth, and D1 provisioning all worked first try from the developer's IP — no VPN required, no card requested at any step. The RU-IP-block failure mode flagged in 01-RESEARCH.md §1 did not materialize.
- The first deploy printed a one-time telemetry notice from wrangler; benign, no action needed.

## Threat Surface Scan

No new trust boundaries introduced beyond those already in the plan's `<threat_model>`. The `database_id` in `wrangler.jsonc` is intentionally committed (T-01-01-02 disposition: accept — it's a routing identifier, not a secret).

## User Setup Required

None additional. The single user-setup step (Cloudflare account + `wrangler login`) was completed by the user before this executor was spawned (Task 1 human-action checkpoint).

## Next Phase Readiness

- **Plan 01-02 (monorepo scaffold)** is the natural next step. Inputs it should consume from this plan:
  - Treat `directory/` as an existing workspace member; do not recreate.
  - Resolve npm-vs-pnpm: either `npm install -g pnpm && rm directory/package-lock.json && pnpm install` from repo root, or update D-10 to accept npm and add a root `package.json` with `workspaces` field instead of `pnpm-workspace.yaml`.
  - Add a root-level `.gitignore` consolidating `node_modules/`, `.wrangler/`, `dist/`, `*.log`, `.env*`.
- **Plans 01-03 / 01-04** can run in parallel with 01-02 once 01-02's monorepo contract is in place.
- **Phase 3** is unblocked for the architecture decision — the `directory/` Worker scaffold is the canonical landing pad for the real JWKS backend.

## Self-Check: PASSED

Verified post-write:
- `directory/wrangler.jsonc` — FOUND (contains real `database_id`, no placeholder)
- `directory/schema.sql` — FOUND
- `directory/src/index.ts` — FOUND (contains `env.DB.prepare`)
- `directory/package.json` — FOUND
- `directory/README.md` — FOUND
- `directory/.gitignore` — FOUND
- `.planning/phases/01-foundation-cryptographic-root/01-01-HOSTING-RESULT.md` — FOUND (contains literal `STATUS: PASS`)
- Commit `a57a1f3` (Task 2) — FOUND in `git log`
- Commit `320e165` (Task 3) — FOUND in `git log`
- Live URL `https://wbauth-day1-test.silov801.workers.dev/ping` — returns `{"ok":true,"row_count":1}` (re-curled at write time)

---
*Phase: 01-foundation-cryptographic-root*
*Plan: 01*
*Completed: 2026-05-03*
