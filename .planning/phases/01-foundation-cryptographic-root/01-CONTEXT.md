# Phase 1: Foundation & Cryptographic Root - Context

**Gathered:** 2026-05-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 delivers the cryptographic root and project skeleton: a Day-1 confirmed hosting baseline (Cloudflare Workers + D1 free tier verified working before any code), a monorepo scaffold, the `spec/test-vectors/` cross-language oracle, and a Python signer that produces RFC 9421 + Web Bot Auth headers Cloudflare's debug verifier accepts. Wrong here = every downstream feature is broken.

Covers v1 requirements: IDENT-01, IDENT-02, IDENT-03, IDENT-04, IDENT-05, IDENT-06, IDENT-07, IDENT-08, DIR-06.

</domain>

<decisions>
## Implementation Decisions

### Hosting & Billing Strategy
- **D-01: Zero-billing architecture chosen.** All hosted infrastructure runs on free tiers — no recurring credit-card charges. This optimizes for the 6+ months unmaintained period during army leave: nothing can break in billing because there is no billing.
- **D-02: Directory backend stack changed from original plan.** Architectural shift: directory backend is **TypeScript on Cloudflare Workers + D1** (NOT Python on FastAPI/Fly.io as originally written in PROJECT.md, REQUIREMENTS.md DIR-01, and SUMMARY.md). All references to FastAPI for the directory backend in research outputs are now superseded. Reason: zero-billing surface + Cloudflare D1 is managed SQLite with auto-backup. Implication: Python developer must delegate directory implementation to TypeScript-capable sub-agents with careful verification against test vectors.
- **D-03: No custom domain in v1.** Use `wbauth.workers.dev` (or similar Cloudflare-assigned subdomain) for the directory backend, and `<github-org>.github.io/wbauth` for docs. Custom domain registration deferred to post-army return — domain renewal is the one billing surface that survives best, but adds zero functional value to v1 and adds one more thing that could lapse.
- **D-04: Day-1 hosting protocol = Cloudflare-only.** Before any code is written: (1) sign up Cloudflare account, (2) deploy hello-world Worker, (3) provision and read/write to a D1 database instance. ~30 minutes total. If Cloudflare rejects the signup or the available payment card for any reason, escalate to user before proceeding (no automatic fallback to Fly.io/Railway — those were eliminated by the zero-billing decision).

### Project Naming
- **D-05: Package name is `wbauth`.** Verified available on PyPI and npm as of 2026-05-03. Chosen for: short (6 letters), pronounceable, ties directly to the IETF Web Bot Auth spec name (SEO benefit — "Web Bot Auth Python" → finds us), no conflict with existing `agentpassport.com` JWT-based system.
- **D-06: Public import surface = `wbauth`.** Python: `from wbauth import sign, inspect, Identity`. TypeScript: `import { sign, inspect, Identity } from "wbauth"`.
- **D-07: PROJECT.md naming references are aliases, not blockers.** All earlier mentions of `agentpassport.dev` / `agentpassport` in PROJECT.md, REQUIREMENTS.md, ROADMAP.md, and research/* are working names that planner should treat as `wbauth` going forward. Update files in Phase 1 as part of repo scaffold.

### Repository Hosting
- **D-08: GitHub account/org choice deferred.** User will decide between personal account and new `wbauth` org at the moment of `git remote add` (planner: leave this as an open knob in scaffolding tasks; do not hardcode an org name in workflows or pyproject.toml).

### Claude's Discretion (areas user delegated)

User explicitly delegated these decisions to Claude (will review the proposal before commit, but does not want to discuss interactively):

- **D-09: Public API shape (Identity construction, signer surface, key file conventions).** Planner should propose a standard pattern based on research/STACK.md and ARCHITECTURE.md (Identity is a long-lived object constructed once at process start; key file default at `~/.config/wbauth/key.pem` with `0o600`; `Identity.load_or_generate(path, signature_agent_url=...)` as the primary entry point). Surface the proposal in the plan for explicit user sign-off before adapter work in Phase 2 begins.
- **D-10: Monorepo layout.** Apply industry-standard layout: `python/` (uv workspace member with `pyproject.toml`), `typescript/` (pnpm workspace member with `package.json`), `directory/` (TypeScript Cloudflare Worker), `spec/test-vectors/` (shared JSON test fixtures), `docs/` (Astro Starlight, deferred details to Phase 5), `.github/workflows/` (CI for python, typescript, cross-language conformance). Single repo, dual workspace roots (uv + pnpm).
- **D-11: Test vector format and initial coverage.** Apply the format described in research/ARCHITECTURE.md (paired `input.json` + `expected.json` files in `spec/test-vectors/`). Minimum 5 vectors covering: (a) basic GET with `@authority` + `signature-agent`, (b) POST with body + `content-digest`, (c) custom non-default expiry, (d) key with multiple URIs in JWKS, (e) edge case TBD (chosen during implementation — likely a Cloudflare-specific quirk). Add Cloudflare debug-endpoint round-trip as the 6th canonical "live" check.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project & Requirements
- `.planning/PROJECT.md` — Core value, constraints, anti-features, tech-stack constraints
- `.planning/REQUIREMENTS.md` — All 52 v1 requirements, especially IDENT-01..08 and DIR-06 for this phase
- `.planning/ROADMAP.md` — Phase boundaries, success criteria, parallelism notes

### Research
- `.planning/research/SUMMARY.md` — Decision-ready synthesis with locked Convergent Decisions section (Cloudflare-safe profile, expires=created+60s, 0o600 perms, REDACTED repr, etc.)
- `.planning/research/STACK.md` — Specific library versions: `pyauth/http-message-signatures` 2.0.1, `cryptography` 46.x, `httpx` 0.28.x, FastAPI 0.118+ (Note: FastAPI is now superseded for directory backend per D-02; still relevant if any local self-hosted directory CLI ships)
- `.planning/research/FEATURES.md` — Web Bot Auth profile spec details (Signature-Agent header rules, derived components, JWKS format)
- `.planning/research/ARCHITECTURE.md` — Pure-function signer pattern, identity-as-long-lived-object, test-vector contract design
- `.planning/research/PITFALLS.md` — Cloudflare rejection conditions, Ed25519 key handling pitfalls, `__repr__` REDACTED requirement, content-type validation for `/robots.txt`

### External Specs (read directly when implementing signer)
- IETF: `draft-meunier-web-bot-auth-architecture-05` (March 2026) — Web Bot Auth profile
- IETF: `draft-meunier-http-message-signatures-directory-05` — JWKS directory format
- IETF: `draft-meunier-webbotauth-registry-01` — Signature Agent Card schema
- IETF: `RFC 9421` — HTTP Message Signatures (canonical signing spec)
- IETF: `RFC 7638` — JSON Web Key Thumbprint (kid format)
- Cloudflare: `https://developers.cloudflare.com/bots/reference/bot-verification/web-bot-auth/`
- Cloudflare debug verifier: `https://http-message-signatures-example.research.cloudflare.com/debug`
- GitHub: `cloudflare/web-bot-auth` (TypeScript + Rust reference implementation)

### Library Docs (verify versions current at implementation time via Context7)
- `pyauth/http-message-signatures` — Python RFC 9421 implementation
- PyCA `cryptography` — Ed25519 keygen, JWK export
- `httpx` — `Auth` subclass pattern (relevant for Phase 2 but useful here for testing)
- Cloudflare Workers + D1 docs — for Day-1 hosting test

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None. Greenfield project. Repo currently contains only `strategic_memo_ru.md` and `.planning/`.

### Established Patterns
- None to inherit. Phase 1 establishes the patterns the rest of the project follows.

### Integration Points
- None yet — this phase produces the `wbauth` Python package as the first integration target for downstream phases.

</code_context>

<specifics>
## Specific Ideas

- **Domain name `agentpassport.dev` was the working name** but is rejected in favor of `wbauth` — explicit user decision after seeing PyPI/npm availability check confirmed `agentpassport` is taken on both registries and shares confusion risk with the existing `agentpassport.com` JWT identity service.
- **Cloudflare debug endpoint MUST be hit by Day 3 of implementation** per SUMMARY.md (cryptographic root validated against external oracle). Planner should treat this as a hard milestone gate inside Phase 1, not a Phase 1 exit criterion only.

</specifics>

<deferred>
## Deferred Ideas

- **Custom domain registration** — defer to post-army. Working name candidates if user wants to register later: `wbauth.dev`, `wbauth.io`, `wbauth.org`. Not registered now to keep zero-billing surface intact.
- **GitHub org `wbauth` vs personal account** — user defers decision to `git remote add` moment in Phase 1 implementation. Planner should leave this as a fill-in-when-applied decision, not hardcode any specific GitHub URL.
- **TypeScript-on-Workers vs Python-on-Fly.io for directory backend** — user chose TypeScript+Workers; Python+Fly.io path is rejected and should not be re-proposed without explicit re-discussion. The `directory/` workspace in monorepo is TypeScript exclusively.

</deferred>

---

*Phase: 1-Foundation & Cryptographic Root*
*Context gathered: 2026-05-03*
