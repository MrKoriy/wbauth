# Phase 1: Foundation & Cryptographic Root - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-03
**Phase:** 1-Foundation & Cryptographic Root
**Areas discussed:** Day-1 Hosting Protocol, Project Naming & Domain
**Areas deferred to Claude's discretion:** Public API shape, Monorepo structure

---

## Day-1 Hosting Protocol

### Q1: What payment cards are available for foreign services?

| Option | Description | Selected |
|--------|-------------|----------|
| RU card (Sber/Tinkoff/Mir) | Stripe blocks since 2022; Fly.io/Railway/Vercel reject | |
| Virtual card (Pyypl/PayPal/Wise) | Issued in UAE/EU; passes most providers but needs balance topup | |
| Other-country card (Armenia/Kazakhstan/etc.) | Non-RF bank, no sanctions, passes everywhere | ✓ |
| None of the above | Plan full zero-billing architecture | ✓ |

**User's choice:** Multi-select with both contradictory options selected; clarified in follow-up.
**Notes:** User has a non-RF card available but explicitly chose zero-billing as the architectural strategy.

### Q2: Clarification on payment situation

| Option | Description | Selected |
|--------|-------------|----------|
| Card available, use it | Paid hosting OK (~$5/mo Fly.io) | |
| Card available, but want zero-billing architecture | Free tier only (CF Workers + D1 + GH Pages); safer for army leave; directory rewrites to TS | ✓ |
| No card at all, zero-billing mandatory | Fully on free tier; domain via crypto/RU registrar | |

**User's choice:** Card available, but want zero-billing architecture
**Notes:** Optimizing for the 6+ months unmaintained period. Significant architectural implication: directory backend moves from Python+FastAPI to TypeScript on Cloudflare Workers + D1.

### Q3: Where to register domain?

| Option | Description | Selected |
|--------|-------------|----------|
| Cloudflare Registrar (Recommended) | Wholesale pricing, integrated with DNS+Workers, robust auto-renewal | |
| Namecheap | $12-15/year .dev, accepts crypto | |
| RU registrar (Reg.ru/Beget) | Rubles, simple from Russia | |
| Defer registration | Use *.workers.dev + *.github.io URLs in v1 | ✓ |

**User's choice:** Defer registration
**Notes:** Eliminates the only remaining recurring billing surface. Custom domain becomes a post-army task.

### Q4: Day-1 protocol shape

| Option | Description | Selected |
|--------|-------------|----------|
| Cloudflare-only test (Recommended) | Sign up, deploy hello-world Worker + D1 (~30 min) | ✓ |
| Cloudflare + domain registration | Everything in one Day-1 session | |
| Code first, hosting later | Defer hosting to Phase 3 | |

**User's choice:** Cloudflare-only test
**Notes:** Lowest friction confirmation that the chosen architecture actually works before committing code.

---

## Project Naming & Domain

### Q1: What naming direction?

| Option | Description | Selected |
|--------|-------------|----------|
| "Identity"-focus (Recommended) | agentid, botid, agentauth, agentpass | ✓ |
| "Policy"-focus | agentpolicy, webpolicy | |
| Neutral "kit" | agentkit (taken), botkit (taken) | |
| Brand/metaphor | havenkit, passport, wayfinder, signpost | |

**User's choice:** "Identity"-focus
**Notes:** Identity is the primary differentiator; policy inspector is the second half.

### Q2: Specific name from curated availability-checked shortlist

| Option | Description | Selected |
|--------|-------------|----------|
| `wbauth` (Recommended) | 6 letters, ties to IETF Web Bot Auth spec name, SEO benefit, free both registries | ✓ |
| `signbot` | Most viral, twitter-friendly, but "bot" connotation conflicts with honest-identity thesis | |
| `webbotauth` | Maximally spec-aligned, but long and clunky to type | |
| `agentcert` | TLS/PKI metaphor, professional, but npm taken (would need scoped name) | |

**User's choice:** `wbauth`
**Notes:** Verified available on PyPI and npm via direct registry checks before locking. SEO alignment with the IETF spec name was the deciding factor.

### Q3: GitHub account/org for the repo?

| Option | Description | Selected |
|--------|-------------|----------|
| Personal account | github.com/<user>/wbauth — clear attribution, calling-card story | |
| New GitHub Org | github.com/wbauth/wbauth — more professional, easier external integrations later | |
| Decide later | Plan-phase leaves it open | ✓ |

**User's choice:** Decide later
**Notes:** Will resolve at the moment of `git remote add`. Plan should leave this as a fill-in-when-applied decision and not hardcode any URL.

---

## Claude's Discretion

The user explicitly delegated these decisions to Claude (will review the proposal before commit, but does not want to discuss interactively):

- **Public API shape** — Identity construction conventions, signer surface, default key file path. Planner will propose a standard pattern (`Identity.load_or_generate(path, signature_agent_url=...)`, default `~/.config/wbauth/key.pem`) for explicit user sign-off in the plan, before adapter work in Phase 2 begins.
- **Monorepo layout** — Apply industry-standard structure: `python/` (uv workspace), `typescript/` (pnpm workspace), `directory/` (TS Cloudflare Worker), `spec/test-vectors/` (shared JSON), `docs/` (Astro Starlight, deferred to Phase 5), `.github/workflows/` (CI). Single repo, dual workspace roots.
- **Test vector format and initial coverage** — Apply paired `input.json` + `expected.json` pattern from research/ARCHITECTURE.md. Minimum 5 vectors covering basic GET, POST with content-digest, custom expiry, multi-URI JWKS, and one Cloudflare-quirk edge case identified during implementation.

## Deferred Ideas

- **Custom domain registration** — defer to post-army return. Working candidates if registered later: `wbauth.dev`, `wbauth.io`, `wbauth.org`.
- **GitHub org `wbauth`** — defer to `git remote add` moment in implementation.
- **Python+FastAPI directory backend** — explicitly rejected in favor of TypeScript+Cloudflare Workers; do not re-propose without re-discussion.
