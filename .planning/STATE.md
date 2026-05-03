---
gsd_state_version: 1.0
milestone: v1.1.1
milestone_name: milestone
status: executing
stopped_at: Plan 01-04 complete (test vectors + Cloudflare conformance — Phase 1 DONE)
last_updated: "2026-05-03T20:25:26Z"
last_activity: 2026-05-03
progress:
  total_phases: 5
  completed_phases: 1
  total_plans: 4
  completed_plans: 4
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-03)

**Core value:** AI-агенты получают идентичность и знают свои права на сайте — до того, как сделают первый запрос. Если ничего другое не работает, эти две вещи (signed identity + pre-flight policy) должны работать в одну строку импорта.
**Current focus:** Phase 01 — foundation-cryptographic-root

## Current Position

Phase: 01 (foundation-cryptographic-root) — COMPLETE
Next phase: 02 (Python Adapters & Policy Inspector)
Plan: 4 of 4 (all Phase 1 plans complete)
Status: Ready to advance to Phase 2
Last activity: 2026-05-03

Progress: [██████████] 100% (4/4 plans complete in Phase 1)

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

Last session: 2026-05-03T20:25:26Z
Stopped at: Plan 01-04 complete — Phase 1 fully delivered (cryptographic root locked + cross-language oracle + live Cloudflare conformance)
Resume file: None
Next plan: Phase 2 plans not yet drafted; orchestrator should run `/gsd-plan-phase 02-python-adapters-and-policy-inspector` next.
