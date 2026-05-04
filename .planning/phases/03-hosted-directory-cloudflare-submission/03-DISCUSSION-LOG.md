# Phase 3: Hosted Directory & Cloudflare Submission - Discussion Log

> **Audit trail only.** Decisions are captured in CONTEXT.md.

**Date:** 2026-05-04
**Phase:** 3-Hosted Directory & Cloudflare Submission
**Areas discussed:** CLI-05 scope, Cloudflare submission timing, Worker URL naming
**Mode:** Carrying forward Phase 1+2 decisions; deciding Phase 3 implementation choices

---

## CLI-05: `wbauth serve` Implementation

| Option | Description | Selected |
|--------|-------------|----------|
| Static JWKS server (Recommended) | 30 LOC Python http.server serving one JWKS file | ✓ |
| Drop CLI-05 from v1 | workers.dev free tier good enough; defer self-hosting | |
| wrangler dev wrapper | Requires Node + wrangler locally | |

**Rationale captured in CONTEXT.md D-50/D-51:** Original plan was Python FastAPI directory. With architectural shift to TS Workers, dropping FastAPI dup. Static JWKS-only server is the simplest viable surface for self-hosters who don't want the hosted directory dependency. Doesn't replicate registration/list endpoints — those are what the hosted directory is for.

---

## Cloudflare Verified-Bot Submission Timing

| Option | Description | Selected |
|--------|-------------|----------|
| Defer until after GitHub push | Cloudflare wants public repo URL | ✓ |
| Submit now without GitHub | workers.dev URL only; risk rejection | |
| Push to GitHub first, then submit in this phase | Resolve D-08 before Phase 3 | |

**Rationale captured in CONTEXT.md D-53:** Moves DIST-08 from Phase 3 to Phase 5 (Pre-Army Hardening). Phase 5 already owns "go-public" actions (docs + Loom + distribution PRs). Bundling GitHub push + Cloudflare submission + reference bot registration there keeps related actions together.

---

## Worker URL Naming

| Option | Description | Selected |
|--------|-------------|----------|
| wbauth-directory.silov801.workers.dev | Descriptive | |
| wbauth.silov801.workers.dev (Recommended) | Short, brand-aligned | ✓ |
| Reuse wbauth-day1-test | "test" in name is bad branding | |

**Rationale captured in CONTEXT.md D-33:** Cleaner brand. Day1-test stays as historical artifact (no deletion in this phase).

---

## Claude's Discretion

The user delegated implementation-level decisions to me — documented in CONTEXT.md D-54..D-57:

- Exact TypeScript framework choice (Hono vs raw fetch vs itty-router) — leaning Hono
- D1 migrations strategy (wrangler-managed vs raw SQL files)
- Worker secret rotation procedure documentation
- Internal TS module organization beyond named files

## Deferred Ideas

- Custom domain (post-army)
- Full directory backend self-hosting in CLI-05 (v1.x)
- Web UI for directory (post-army DIR-UI-01)
- Real-time multi-region mirroring (post-army)
- Site-side verification SDK (v2)
- DIST-08 → Phase 5 (not deferred, scheduled)
