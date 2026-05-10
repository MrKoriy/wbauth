# Roadmap: Agent Identity & Policy Toolkit

## Overview

Five phases ship a Python+TypeScript OSS toolkit that gives AI agents two superpowers in one import: signed identity (IETF Web Bot Auth via RFC 9421) and pre-flight site policy (robots.txt + ai.txt + llms.txt + .well-known/* fan-out). The build sequence is dictated by a single non-negotiable critical path — the Python signer must pass Cloudflare's debug verifier before any adapter, framework demo, or directory work begins, because cryptographic correctness gates everything downstream. The journey starts with a Day-1 hosting card test (highest-uncertainty external blocker), proceeds through the cryptographic root, then expands into the policy inspector and HTTP-client adapters, then ships the public directory backend and initiates Cloudflare's verified-bot submission (the longest external dependency), runs the TypeScript SDK and framework demos in parallel with directory work via shared test-vector contracts, and ends with a hardening phase whose entire purpose is making the project survive 6+ months unmaintained while the maintainer is on army leave.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation & Cryptographic Root** - Day-1 hosting test, monorepo scaffold, test vectors, Python signer passing Cloudflare debug verifier
- [ ] **Phase 2: Python Adapters & Policy Inspector** - httpx/requests/Playwright adapters, full inspect(url) with verdict engine, wbauth CLI core
- [x] **Phase 3: Hosted Directory & Cloudflare Submission** - Cloudflare Workers + D1 directory at `wbauth.silov801.workers.dev`, end-to-end registration→sign→verify (DIST-08 moved to Phase 5 — Cloudflare submission requires public GitHub repo which depends on D-08 GitHub-org choice). E2E exit criterion D-52 SATISFIED (PARTIAL — internal chain proved; external Cloudflare verifier validation deferred to Phase 5 DIST-08).
- [ ] **Phase 4: TypeScript SDK & Framework Integrations** - TS fetch+Playwright adapters with byte-equality to Python, Browser Use/Stagehand/OpenAI Agents demos (DIST-07 upstream PRs moved to Phase 5 per 04-CONTEXT.md D-71)
- [ ] **Phase 5: Pre-Army Hardening, Docs & Launch** - Astro Starlight docs site, Loom demo, README polish, Dependabot, daily canary, frozen branch, MAINTAINER_AWAY runbook, 2FA backups, public launch + Cloudflare verified-bot submission (DIST-08) + upstream framework PRs (DIST-07)

## Phase Details

### Phase 1: Foundation & Cryptographic Root
**Goal**: Establish the project skeleton on confirmed hosting and prove that the Python signer produces signatures Cloudflare accepts — the cryptographic root that gates every downstream feature.
**Depends on**: Nothing (first phase)
**Requirements**: IDENT-01, IDENT-02, IDENT-03, IDENT-04, IDENT-05, IDENT-06, IDENT-07, IDENT-08, DIR-06
**Success Criteria** (what must be TRUE):
  1. Russian payment card is confirmed working on the chosen hosting provider (Fly.io primary; Railway or Cloudflare Workers+D1 fallback if rejected) and the project domain is registered with auto-renewal enabled for >18 months — this is a Day-1 blocker before any code is written
  2. A developer can run `wbauth keygen` and get an Ed25519 keypair written with `0o600` permissions, with the loader refusing wider-permission files; `__repr__` and `__str__` of `Identity` return REDACTED instead of leaking key material
  3. The pure function `sign(NormalizedRequest, Identity) -> SignatureHeaders` produces RFC 9421 `Signature`, `Signature-Input`, and `Signature-Agent` headers with Web Bot Auth defaults (Ed25519, `tag="web-bot-auth"`, `expires = created + 60s`) and JWKS export uses `kid = base64url(sha256(JWK))` per RFC 7638
  4. Generated signatures pass byte-equal verification against `spec/test-vectors/` (≥5 golden vectors) AND Cloudflare's debug verifier endpoint accepts a request signed by our SDK in <2 seconds end-to-end (CI smoke test plus weekly scheduled run)
  5. Multi-key Identity supports rotation lifecycle (active + retiring key with overlap window); old key remains usable until explicit retirement
**Plans**: 4 plans
- [x] 01-01-PLAN.md — Day-1 Cloudflare Workers + D1 hosting confirmation (DIR-06; strict serial blocker, autonomous=false)
- [x] 01-02-PLAN.md — Monorepo scaffold (uv + npm workspaces, package metadata, CI workflows, LICENSE; supporting plan) [npm not pnpm per user override]
- [x] 01-03-PLAN.md — Identity, signer, JWKS thumbprint, multi-key rotation, REDACTED repr, `wbauth keygen` CLI (IDENT-01, 02, 03, 06, 07, 08)
- [x] 01-04-PLAN.md — Test vectors (5 byte-equal + 1 live), pytest+vitest cross-language oracle, Cloudflare research verifier as hard CI exit criterion (IDENT-04, IDENT-05)
**Parallelism note**: Day-1 hosting test (Plan 01) is a strict serial blocker. Plans 02→03→04 are sequential because each consumes the previous plan's outputs (workspace skeleton → signer → vectors generated by signer).

### Phase 2: Python Adapters & Policy Inspector
**Goal**: Make the signer drop-in usable from real Python HTTP clients AND deliver the policy half (`inspect(url) -> SitePolicy` with verdict engine) so the project's core value claim ("identity + policy in one import") is demonstrable end-to-end in Python.
**Depends on**: Phase 1 (signer + test vectors locked)
**Requirements**: ADAPT-01, ADAPT-02, ADAPT-03, ADAPT-06, ADAPT-07, POLICY-01, POLICY-02, POLICY-03, POLICY-04, POLICY-05, POLICY-06, POLICY-07, POLICY-08, CLI-01, CLI-02, CLI-03, CLI-06
**Success Criteria** (what must be TRUE):
  1. A user can write `httpx.Client(auth=WebBotAuth(identity)).get(url)` (or use the `requests` transport adapter or `attach_signing(page, identity)` for Playwright) and the outgoing request carries valid Web Bot Auth signatures verified by Phase 1 test vectors; each adapter file is ≤50 LOC of glue with complexity living in the pure signer
  2. `await inspect(url)` returns a frozen `SitePolicy` dataclass with parallel-fetched robots.txt (via `protego`, RFC 9309-compliant), ai.txt v1.1.1, llms.txt (labeled `enforcement: "voluntary"`), and `.well-known/http-message-signatures-directory`; partial failures are isolated (`return_exceptions=True`, `partial: bool`, `errors: dict`) with 3s per-endpoint timeout
  3. `policy.verdict` returns `"allowed" | "restricted" | "forbidden"` with `reasons: list[str]` from a deterministic rule engine (robots authoritative, ai.txt restriction → restricted, signing-required → restricted with mitigation hint); HTML 200 on `/robots.txt` raises explicit parse error rather than silently returning "allowed"
  4. Per-host LRU cache honors `Cache-Control`/`ETag` (defaults: robots.txt 24h, ai.txt 1h, llms.txt 24h) and operates entirely in-process with zero hard cloud dependency — `inspect(url)` works without agentpassport.dev
  5. `wbauth keygen`, `wbauth inspect <url>` (with `--json`), and `wbauth verify --domain <domain>` (runs Cloudflare debug verifier and prints pass/fail per criterion) all work from the command line, returning non-zero exit codes on failure with machine-readable errors on stderr
**Plans**: 3 plans
- [x] 02-01-PLAN.md — Three Python HTTP-client adapters (httpx, requests, Playwright) with byte-equal conformance vs Phase-1 test vectors; ADAPT-01,02,03,06,07
- [x] 02-02-PLAN.md — Async policy inspector (4-endpoint fan-out, four parsers, strict verdict engine, per-host LRU cache); POLICY-01..08
- [x] 02-03-PLAN.md — wbauth CLI extension (inspect + verify subcommands; keygen exit-code/stderr audit); CLI-01,02,03,06
**Parallelism note**: Plans 02-01 and 02-02 share zero code dependencies (adapters wrap signer; inspector fetches HTTP without signer involvement) but both touch `python/src/wbauth/__init__.py` and `python/pyproject.toml` — wave-purity rule forces 02-02 to wave 2 (sequential after 02-01). 02-03 is wave 3 (depends on both prior plans). Browser Use Playwright spike was DROPPED per CONTEXT.md D-13 — async page.route confidence HIGH; Phase 4 demo is the live verification.

### Phase 3: Hosted Directory & Cloudflare Submission
**Goal**: Stand up the public agent identity directory at `https://wbauth.silov801.workers.dev` (Cloudflare Worker + D1) so verifiers can fetch JWKS for any registered agent, prove the full register→sign→verify flow end-to-end against Cloudflare's research verifier, and ship the local `wbauth serve` JWKS host for self-hosters.
**Depends on**: Phase 1 (verifier code path reused for proof-of-key-ownership)
**Requirements**: DIR-01, DIR-02, DIR-03, DIR-04, DIR-05, DIR-07, DIR-08, CLI-04, CLI-05
**Scope change**: DIST-08 (Cloudflare verified-bot submission) MOVED from Phase 3 to Phase 5 per 03-CONTEXT.md D-53. Cloudflare's submission review requires a public GitHub repo URL; D-08 (GitHub org/account choice) was deferred to be resolved at `git remote add` time. Phase 5 bundles all "go-public" actions (resolve D-08, push to GitHub, file Cloudflare submission, register reference bot via the directory we built in Phase 3).
**Success Criteria** (what must be TRUE):
  1. A user can register an agent via `wbauth register --directory https://wbauth.silov801.workers.dev --identity <path>` using two-step proof-of-key-ownership (server issues nonce, caller signs with claimed private key, server verifies via the same `web-bot-auth` 0.1.3 verify path the SDK exports — no email, no OAuth, no third-party identity provider)
  2. `GET /.well-known/http-message-signatures-directory/{kid}` returns JWKS with `Content-Type: application/http-message-signatures-directory+json`; the directory response itself is signed (Worker holds its own Ed25519 keypair as `DIRECTORY_PRIVATE_JWK` secret); responses are CDN-cached with `Cache-Control: public, max-age=300`; per-IP registration rate limit (10/day) and reserved-name blocklist (google, openai, anthropic, cloudflare, microsoft, meta, apple, amazon, aws, github, stripe, shopify) prevent abuse
  3. End-to-end flow validated live: register an identity → sign an HTTP request via the SDK with that identity's directory URL → Cloudflare research verifier confirms verification passes (manual run via `python/scripts/e2e_phase3.py`, NOT in CI to avoid spamming our own directory)
  4. A nightly snapshot job mirrors the full directory to `/static/all.json` and to a GitHub Pages mirror as disaster recovery (workflow file ships with cron commented out + `workflow_dispatch` for ad-hoc runs; cron enabled in Phase 5 when D-08 GitHub remote resolves); zero billing possible — Workers Free tier hard-capped at 100k req/day, D1 Free tier 5M reads/day
  5. `wbauth serve [--port N] --jwks <path>` runs a local self-hostable static JWKS server (~30 LOC stdlib `http.server`) for users who don't want to depend on the hosted directory; `wbauth keygen --jwks-output <path>` extension lets self-hosters export the JWKS file
**Plans**: 3 plans
- [x] 03-01-PLAN.md — Hono+D1 Worker (challenge/submit/JWKS read/agents list/snapshot endpoint), blocklist, rate limit, response signing, vitest tests, secret provisioning, live deploy to wbauth.silov801.workers.dev (DIR-01, DIR-02, DIR-03, DIR-04, DIR-07)
- [x] 03-02-PLAN.md — GitHub Action snapshot workflow (cron disabled), Python `wbauth register` CLI, `wbauth serve` ≤30 LOC static JWKS server, `wbauth keygen --jwks-output` extension (DIR-05, CLI-04, CLI-05)
- [x] 03-03-PLAN.md — End-to-end manual test script (register → fetch JWKS → sign → Cloudflare research verifier 200 OK), E2E-RESULT.md write, exit-criterion checkpoint (DIR-08); STATUS: PARTIAL accepted per 03-RESEARCH.md §8 NOTE
**Parallelism note**: Plans 03-01 and 03-02 are sequential because 03-02's E2E `wbauth register` smoke and 03-03's exit script both require the live Worker URL and live D1. Phase 4 (TypeScript SDK) can begin in parallel with this phase as soon as Phase 1's test vectors are locked — TS implementation by sub-agents is safe because conformance is gated by the shared `spec/test-vectors/` JSON files.

### Phase 4: TypeScript SDK & Framework Integrations
**Goal**: Ship feature-parity TypeScript SDK guaranteed byte-equal to Python via shared test vectors, plus tested integration recipes for the three target frameworks (Browser Use, Stagehand, Playwright+OpenAI Agents SDK). Upstream PRs (DIST-07) are explicitly NOT in Phase 4 — see scope change below.
**Depends on**: Phase 1 (test vectors locked) — runs largely in parallel with Phase 3
**Requirements**: ADAPT-04, ADAPT-05, DIST-04, DIST-05, DIST-06
**Scope change**: DIST-07 (upstream PRs to Browser Use, Stagehand, mcp-agent `examples/` directories) MOVED from Phase 4 to Phase 5 per 04-CONTEXT.md D-71. Three reasons: (1) PRs need a public GitHub repo URL — D-08 (GitHub org/account choice) still deferred until `git remote add` time. (2) PRs need an author identity for review correspondence — also gated on D-08. (3) PRs need capacity to respond to review feedback — Phase 5 hardening territory. Phase 4 produces the runnable `examples/*_demo.{py,ts}` scripts; Phase 5 forks the upstream repos and opens the PRs based on those scripts.
**Success Criteria** (what must be TRUE):
  1. A TypeScript user can write `const signedFetch = createSignedFetch(identity); await signedFetch(url)` and the produced `Signature`/`Signature-Input`/`Signature-Agent` headers are byte-identical to Python's output for the same inputs (Vitest tests consume the same `spec/test-vectors/` JSON files as pytest)
  2. A TypeScript user can call `applyTo(page, identity)` against a Playwright page and outgoing requests are signed via `page.route("**/*", handler)` (NOT static `set_extra_http_headers`) — mirroring Python adapter behavior
  3. `examples/browser_use_demo.py` shows a verified end-to-end flow runnable both with and without an LLM key: mock-mode opens our live Worker (`https://wbauth.silov801.workers.dev/agents`) and prints the signed Signature-Input header to stdout; real-mode runs a Browser Use Agent navigating to a benign target. Same dual-mode pattern applies to `examples/stagehand_demo.ts` and `examples/openai_agents_demo.py`.
  4. A user can generate an Ed25519 key in Python (`wbauth keygen`), then load it in TypeScript via `Identity.loadOrGenerate`, and produce a Signature byte-equal to Python's output for the same vector — proving the canonical "single key file, two SDKs" guarantee (D-60 / D-66 cross-language round-trip test)
  5. Public TypeScript API uses idiomatic camelCase (`Identity.loadOrGenerate()`, `signatureInput`) and exports flat from `wbauth` root (`import { sign, Identity, createSignedFetch, applyTo } from "wbauth"`); JSON wire format stays snake_case to follow the IETF draft; on-disk PKCS8 NoEncryption PEM file format works in both SDKs
**Plans**: 3 plans
- [x] 04-01-PLAN.md — TS SDK core: Identity (loadOrGenerate/fromTestKey/rotate/exportJwks), signer (wraps web-bot-auth 0.1.3), createSignedFetch (≤50 LOC), applyTo Playwright (≤50 LOC), vitest unit + adapter conformance vs vector 01 (ADAPT-04, ADAPT-05)
- [x] 04-02-PLAN.md — Cross-language Identity round-trip (D-66): Python keygen → TS load → sign vector 01 → byte-equal vs Python; multi-key rotation TS coverage closing Phase 1 vector 04 skip (supporting plan, no new requirements)
- [x] 04-03-PLAN.md — Three runnable framework demos in `examples/`: browser_use_demo.py + stagehand_demo.ts + openai_agents_demo.py, all with optional-LLM bifurcation, mock-mode targets the live Worker (DIST-04, DIST-05, DIST-06)
**Parallelism note**: This is the project's primary time-leverage point. The test-vector contract from Phase 1 makes safe agent delegation possible — sub-agent(s) build the TS SDK while the human focuses on directory backend (Phase 3). Plans 04-02 and 04-03 are wave 2 (depend on 04-01) and run in parallel with each other (different files: cross-language test in `python/tests/` + `typescript/tests/`; demos in `examples/`). DIST-07 (upstream PRs) is explicitly Phase 5 work per D-71.

### Phase 5: Pre-Army Hardening, Docs & Launch
**Goal**: Make the project actually survive 6+ months unmaintained — documentation that answers "is this abandoned?" with content not activity, automated systems that catch dependency rot and Cloudflare-spec drift, frozen-branch guarantees, and the public launch (Loom demo, README polish, distribution). Also resolves D-08 (GitHub org choice), files the Cloudflare verified-bot submission (DIST-08, moved from Phase 3 per 03-CONTEXT.md D-53), and submits upstream framework PRs (DIST-07, moved from Phase 4 per 04-CONTEXT.md D-71).
**Depends on**: Phase 4 (all SDK + adapter + directory + demos shipping)
**Requirements**: DIST-01, DIST-02, DIST-03, DIST-07, DIST-08, HARDEN-01, HARDEN-02, HARDEN-03, HARDEN-04, HARDEN-05, HARDEN-06, HARDEN-07
**Success Criteria** (what must be TRUE):
  1. A developer landing on the GitHub README understands the project in ≤30 seconds — GIF demo at top, code-before-prose, native-English review completed; the 60-second Loom demo (agent fails on Cloudflare → installs SDK → 3 lines added → request passes) is embedded on landing and README
  2. Astro Starlight docs on GitHub Pages contain quickstart, API reference, "why this exists", and FAQ — builds reproducibly years later with `package-lock.json` committed; PyPI publishing uses OIDC trusted publishers (no token to rotate); npm publishing uses provenance from GitHub Actions
  3. A monthly scheduled CI canary verifies "still installs cleanly"; a daily conformance canary (GitHub Action → Cloudflare debug) opens a GitHub issue and posts a Discord alert on failure — both run without manual intervention; Dependabot is configured (not Renovate — fewer PRs during absence)
  4. A `v1.x-frozen` git branch exists with a 12-month compatibility promise documented in `MAINTAINER_AWAY.md` at the repo root (expected return date, contact for moderators); a pinned status issue at the top of the repo explains the maintainer absence and routes urgent security reports; CONTRIBUTING.md documents the triage path
  5. 2FA backup codes for GitHub, PyPI, npm, and the domain registrar are printed and stored offline with a trusted party; designated repo moderator(s) added with triage permissions; domain auto-renewal verified to cover >18 months; DNS, TLS cert (Let's Encrypt auto-renew), CDN config all set to auto-mode with no manual touch points
  6. **DIST-07**: Pull requests submitted to `examples/` directories of Browser Use, Stagehand, and mcp-agent adding our SDK as a first-class integration option (based on the Phase 4 `examples/*_demo.{py,ts}` scripts); PR links recorded in the project README
  7. **DIST-08**: Reference demo bot registered in `wbauth.silov801.workers.dev` directory (using Phase 3's `wbauth register` CLI) AND submission filed to Cloudflare's verified-bot directory (filed on Day 1 of Phase 5 due to opaque review timeline; approval by army leave is best-effort). Phase 3 snapshot workflow's `cron` is enabled in this phase once GitHub remote exists.
**Plans**: TBD (estimate 2-3 plans)
**UI hint**: yes
**Parallelism note**: Docs writing (DIST-01/02/03) and hardening tasks (HARDEN-01-07) are independent — sub-agents can draft the Astro Starlight site, README polish, and Loom storyboard in parallel with the human configuring OIDC publishers, Dependabot, frozen branch, and 2FA backup printing. DIST-07 (upstream PRs) and DIST-08 (Cloudflare submission) both unblock once D-08 (GitHub org choice) resolves at `git remote add` time.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 (with Phase 4 starting in parallel as soon as Phase 1's test vectors are locked) → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Cryptographic Root | 4/4 | Complete | 2026-05-03 |
| 2. Python Adapters & Policy Inspector | 1/3 | In Progress|  |
| 3. Hosted Directory & Cloudflare Submission | 3/3 | Complete | 2026-05-10 |
| 4. TypeScript SDK & Framework Integrations | 0/3 | Planned | - |
| 5. Pre-Army Hardening, Docs & Launch | 0/TBD | Not started | - |
