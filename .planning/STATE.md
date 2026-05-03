# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-03)

**Core value:** AI-агенты получают идентичность и знают свои права на сайте — до того, как сделают первый запрос. Если ничего другое не работает, эти две вещи (signed identity + pre-flight policy) должны работать в одну строку импорта.
**Current focus:** Phase 1 — Foundation & Cryptographic Root

## Current Position

Phase: 1 of 5 (Foundation & Cryptographic Root)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-05-03 — ROADMAP.md and STATE.md created from REQUIREMENTS.md + research synthesis

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundation & Cryptographic Root | 0 | — | — |
| 2. Python Adapters & Policy Inspector | 0 | — | — |
| 3. Hosted Directory & Cloudflare Submission | 0 | — | — |
| 4. TypeScript SDK & Framework Integrations | 0 | — | — |
| 5. Pre-Army Hardening, Docs & Launch | 0 | — | — |

**Recent Trend:**
- Last 5 plans: —
- Trend: — (no execution data yet)

*Updated after each plan completion*

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

Last session: 2026-05-03 (roadmap creation)
Stopped at: ROADMAP.md and STATE.md written; REQUIREMENTS.md traceability section pending update
Resume file: None — next step is `/gsd-plan-phase 1`
