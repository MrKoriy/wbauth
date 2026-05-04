# Phase 3: Hosted Directory & Cloudflare Submission - Research

**Researched:** 2026-05-03
**Domain:** TypeScript Cloudflare Worker + D1 directory backend serving signed JWKS per `draft-meunier-http-message-signatures-directory-05`, with proof-of-key-ownership registration, per-IP rate limiting, nightly snapshot mirror, plus Python `wbauth register` / `wbauth serve` CLI extensions.
**Confidence:** HIGH for stack/library APIs (Hono, web-bot-auth 0.1.3, D1, wrangler — all verified via Context7 + npm registry); MEDIUM for one Workers Free-tier edge case (Ed25519 PKCS8 import via WebCrypto — see Open Question #2); HIGH for Python CLI work (reuses Phase 1/2 primitives 1:1).

---

## Summary

Phase 3 replaces the Phase-1 throwaway `directory/src/index.ts` with a production-grade Hono + Cloudflare Workers + D1 backend at `wbauth.silov801.workers.dev`, implementing the IETF directory format, a two-step proof-of-key-ownership registration flow that re-uses the same `cloudflare/web-bot-auth` 0.1.3 verifier the SDK consumes, and a per-IP D1-backed rate limit (Workers Rate Limit binding's free-tier status is unconfirmed and CONTEXT.md D-48 already locks D1). The Worker holds its own Ed25519 keypair as a Cloudflare secret and signs JWKS responses via the package's `directoryResponseHeaders` helper. Snapshots run nightly via a GitHub Action that fetches `/static/all.json` and pushes to a `gh-pages`-style branch (the exact target depends on D-08 GitHub-org resolution, deferred to Phase 5 — Phase 3 ships the workflow file but disabled-by-default until the snapshot repo URL exists).

The Python side is small: `wbauth register --identity <key.pem> [--directory <url>]` reuses `wbauth.sign()` + httpx (already deps) to drive the two-step challenge/submit flow against the live Worker; `wbauth serve --jwks <path>` is a ~30-LOC stdlib `http.server` static JWKS host for users who want zero dependency on the hosted directory. The E2E exit gate (D-52) is a manual script under `python/scripts/` that registers a fresh identity, verifies the JWKS comes back signed and parseable, signs a request via `wbauth.sign()`, hits the Cloudflare research verifier, and asserts the success banner — kept out of CI to avoid spamming our own directory on every push.

**Primary recommendation:** Use Hono 4.12.x as the TypeScript router (smallest/fastest framework that ships first-class Cloudflare Workers + D1 support and a built-in Cloudflare-Workers `getConnInfo` helper for IP extraction). Use wrangler 4.87.0 with managed D1 migrations under `directory/migrations/`. Use `web-bot-auth/crypto` for `verifierFromJWK` (registration verify) and `signerFromJWK` for the directory's own Ed25519 key, plus `directoryResponseHeaders` from the same package for the signed JWKS response — the helper is purpose-built for this exact endpoint and matches the spec's tag/component requirements. Store the directory's Ed25519 private key as a JSON-stringified JWK in a Worker secret (`DIRECTORY_PRIVATE_JWK`) — JWK is the format `signerFromJWK` expects natively, sidestepping the Workers WebCrypto Ed25519-PKCS8 ambiguity entirely.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Carrying forward (Phase 1 + Phase 2):**
- Package name `wbauth` (Phase 1 D-05); zero-billing architecture, Cloudflare Workers + D1 (D-01, D-02); no custom domain in v1 — `*.workers.dev` URL (D-03); Identity API `Identity.load_or_generate(path, signature_agent_url=...)` (D-09); signer is `wbauth.sign()` pure function; Cloudflare research verifier is the open-spec conformance oracle.

**Phase 3 Production Worker:**
- **D-33:** Production Worker URL = `https://wbauth.silov801.workers.dev`. New Worker, NOT a rename of `wbauth-day1-test`.
- **D-34:** D1 database = `wbauth-directory` (new). Single-table schema.
- **D-35:** Worker codebase replaces existing `directory/` workspace contents. The throwaway `src/index.ts` is overwritten.

**Phase 3 Schema:**
- **D-36:** Single `agents` table. Columns: `kid TEXT PRIMARY KEY`, `client_name TEXT NOT NULL`, `client_uri TEXT`, `signature_agent_url TEXT NOT NULL`, `expected_user_agent TEXT`, `contacts TEXT` (JSON array), `purpose TEXT`, `targeted_content TEXT`, `rate_control TEXT`, `keys TEXT NOT NULL` (JWKS JSON blob), `created_at INTEGER NOT NULL`, `last_updated INTEGER NOT NULL`. Multi-key support inside the JWKS blob — no separate keys table.
- **D-37:** No user accounts table. Identity == kid.

**Phase 3 Registration (DIR-02):**
- **D-38:** Two-step proof-of-key-ownership. (1) `POST /register/challenge {kid}` → `{challenge, expires_at}`. (2) Client signs `{action:"register", kid, challenge}` with the kid's private key via Web Bot Auth signer; POSTs to `/register/submit`. Server verifies via the same RFC 9421 path the SDK exports, then INSERT/UPDATE atomically.
- **D-39:** No email, no OAuth, no CAPTCHA.
- **D-40:** Per-IP rate limit on `/register/*`. 10 attempts per IP per day. Doesn't apply to read endpoints.

**Phase 3 Read API (DIR-03):**
- **D-41:** Read endpoints:
  - `GET /.well-known/http-message-signatures-directory/{kid}` — JWKS for a single kid; content-type `application/http-message-signatures-directory+json`; signed; `Cache-Control: public, max-age=300, immutable`.
  - `GET /agents/{kid}` — full Signature Agent Card; JSON; `max-age=60`.
  - `GET /agents` — paginated list (50 per page), `?page=N`; `max-age=300`.
  - `GET /static/all.json` — full snapshot.
- **D-42:** Directory response signing. Worker holds its own Ed25519 keypair stored as a Cloudflare Worker secret via `wrangler secret put DIRECTORY_PRIVATE_KEY`. The directory's own kid is published at the root of `/.well-known/http-message-signatures-directory/`.

**Phase 3 Reserved-Name Blocklist (DIR-04):**
- **D-43:** Block `client_name` matching exact (case-insensitive) any of: `google`, `openai`, `anthropic`, `cloudflare`, `microsoft`, `meta`, `apple`, `amazon`, `aws`, `github`, `stripe`, `shopify`. Also block any `client_name` containing those tokens IF combined with `bot`/`agent`/`crawler` (e.g., `google-bot` blocked, `googlestyle-app` allowed). Implementation: small TS regex array in `directory/src/blocklist.ts`.
- **D-44:** Reject with HTTP 422 + `{"error": "reserved_name", "blocked_token": "google", "guidance": "If you represent this organization and want this name on agentpassport, contact <maintainer email TBD in Phase 5>"}`.

**Phase 3 Snapshot & DR (DIR-05):**
- **D-45:** Nightly GitHub Action job at 02:00 UTC queries `GET /agents?all=true` against the live Worker; writes single `directory-snapshot.json` to `snapshots/` directory in repo's `gh-pages` branch (or dedicated `wbauth-snapshots` repo). Script: `.github/workflows/snapshot.yml` + `scripts/snapshot.sh`. Snapshot URL documented in README.
- **D-46:** Last 30 days as separate dated files (`directory-snapshot-2026-05-04.json`); plus a `latest` copy.

**Phase 3 Spend Caps & Abuse (DIR-07):**
- **D-47:** Cloudflare Workers Free tier limits. 100k requests/day, 10ms CPU per invocation. D1: 5M reads/day, 100k writes/day, 5GB storage. Free tier hard-capped — no spend possible. Do NOT enable Workers Paid in v1.
- **D-48:** Per-IP rate limit on registration enforced via D1 small-row strategy. 10 attempts per IP per day. Cloudflare's built-in IP rate limiting is paid-only; D1 is free.

**Phase 3 CLI (CLI-04, CLI-05):**
- **D-49:** `wbauth register --identity <key.pem> [--directory <url>]` — defaults `--directory https://wbauth.silov801.workers.dev`. Prompts for `client_name` and `purpose` (or accepts `--client-name`/`--purpose` args). Two-step flow. Exit 0 on success, 1 on rejection.
- **D-50:** `wbauth serve [--port 8080] --jwks <path>` — minimal Python http.server-based static JWKS server. ~30 LOC. Serves single JWKS file at `/.well-known/http-message-signatures-directory/{kid}` with correct content-type. NO registration, NO list endpoints.
- **D-51:** Self-hosters generate JWKS via `wbauth keygen --jwks-output <path>` (extend existing `keygen` subcommand with a `--jwks-output` flag).

**Phase 3 E2E (DIR-08):**
- **D-52:** Phase 3 exit criterion is a live E2E flow. Generate identity locally → `wbauth register` to live Worker → confirm `GET /.well-known/http-message-signatures-directory/{kid}` returns JWKS with valid signature → sign a probe via `wbauth.sign()` with the registered directory URL → POST to Cloudflare research verifier → verifier responds 200 OK + success banner. Captured in CI test (manual run, not auto).

**Phase 3 Scope Boundary:**
- **D-53:** DIST-08 (Cloudflare verified-bot submission) MOVED from Phase 3 to Phase 5. Phase 3 builds the directory; Phase 5 makes it discoverable.

### Claude's Discretion

- **D-54:** Exact TypeScript framework choice (Hono vs raw fetch handler vs itty-router). Planner picks based on size + maintenance — leaning Hono.
- **D-55:** D1 migrations strategy (wrangler-managed vs raw SQL files). Pick simpler.
- **D-56:** Worker secret rotation procedure documentation (in directory README — explain how to rotate `DIRECTORY_PRIVATE_KEY` if compromised).
- **D-57:** Internal TypeScript module organization beyond what's named in D-36 schema and D-41 endpoints.

### Deferred Ideas (OUT OF SCOPE)

- Custom domain `wbauth.dev` / `wbauth.io` — post-army.
- `wbauth serve` as full directory backend (registration, list endpoints) — v1.x.
- Web UI / browse experience for the directory — REQUIREMENTS.md `DIR-UI-01`, post-army.
- Real-time directory mirroring / multi-region replication — `DIR-MIRROR-01`, post-army.
- Site-side verification SDK — `SITE-VERIFY-01`, v2.
- DIST-08 (Cloudflare verified-bot submission) — moved to Phase 5 per D-53.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DIR-01 | Backend exposes `POST /register` accepting Signature Agent Card per draft-meunier-webbotauth-registry-01 | §2 (Wrangler/D1 schema) + §3 (route handlers) — `POST /register/submit` is the canonical endpoint per D-38 two-step flow; the bare `POST /register` from REQUIREMENTS.md is replaced by `/register/challenge` + `/register/submit` per locked D-38 |
| DIR-02 | Registration via proof-of-key-ownership (no email/OAuth) | §3 (`/register/challenge` + `/register/submit` handlers) + §4 (web-bot-auth 0.1.3 `verify` integration) |
| DIR-03 | `GET /.well-known/http-message-signatures-directory/{kid}` returns signed JWKS | §3 (read handlers) + §4 (`directoryResponseHeaders` helper from web-bot-auth/http-message-sig) |
| DIR-04 | CDN-cached reads, per-IP rate limit (10/day), reserved-name blocklist | §3 (Cache-Control headers, blocklist module, D1 rate-limit table + cleanup-on-write) |
| DIR-05 | Nightly snapshot to `/static/all.json` + GitHub Pages mirror | §5 (GitHub Actions YAML) — exact workflow blocked on D-08 (GitHub-org resolution); ship workflow file disabled until Phase 5 |
| DIR-07 | Spend caps configured; abuse vectors handled | §1 (free-tier hard caps — no spend possible) + §3 (blocklist + rate limit) |
| DIR-08 | E2E flow validated: register → sign → Cloudflare verifier 200 OK | §8 (E2E manual-test script; reuses Phase 1 `_smoke/cloudflare_debug.py` pattern) |
| CLI-04 | `wbauth register --directory <url> --identity <path>` | §6 (Python CLI implementation reference using existing `wbauth.sign()` + httpx) |
| CLI-05 | `wbauth serve [--port N]` minimal local JWKS server | §7 (~30 LOC stdlib http.server reference) |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

CLAUDE.md is auto-generated GSD scaffolding (no project-specific directives beyond the GSD workflow enforcement). Key items distilled:

- **GSD workflow enforcement:** All file edits go through a GSD command. Phase 3 work proceeds via `/gsd-execute-phase` after planning.
- **Tech stack — TypeScript:** Delegated to agents with tight verification. The `directory/` workspace is TypeScript-exclusive per Phase 1 D-02 (and `deferred` block in Phase 1 explicitly forbids re-proposing Python+Fly.io for the directory).
- **No billing in v1.** Confirms zero-billing architecture (Phase 1 D-01).
- **macOS dev workaround:** `bash scripts/post-sync.sh` after `uv sync` + `chflags nohidden` on `.pth` files (carry-forward from Phase 2 verification). Affects `wbauth register` / `wbauth serve` smoke testing on the dev machine but not CI.
- **Maintenance after publication:** Must survive 6+ months unmaintained. Pin upper bounds aggressively in `directory/package.json` (already done for Phase 1's `wrangler ^4.87.0`); add explicit pins for `hono` and `web-bot-auth` in this phase.

## Architectural Responsibility Map

Phase 3 spans three deployment surfaces and one human-action gate. Each Phase 3 capability slots into exactly one tier:

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| HTTP routing (Hono) | Cloudflare Worker | — | Worker is the only network surface for the hosted directory |
| Persistent storage (agents, ratelimit) | D1 (Cloudflare-managed SQLite) | — | D1 is Worker's only durable storage in zero-billing mode |
| Registration signature verification | Cloudflare Worker | — | Worker calls `web-bot-auth/crypto.verifierFromJWK` against the kid's published JWKS in the submit body — server-side validation only |
| Directory response signing | Cloudflare Worker | — | Worker holds the directory's own Ed25519 secret; signing happens at response time |
| Reserved-name blocklist | Cloudflare Worker | — | Cheap regex match in handler; no DB hit needed |
| Per-IP rate limit | Cloudflare Worker + D1 | — | Worker reads + writes a small `ratelimit` D1 row per registration attempt; cleanup-on-write of expired rows |
| Snapshot job | GitHub Actions runner | Cloudflare Worker (read source) + GitHub Pages (sink) | External cron — Worker is just an HTTP source; sink is a separate gh-pages branch |
| `wbauth register` CLI | Python user process | Cloudflare Worker (HTTPS POST target) | Local Python tool drives the registration flow against the live Worker |
| `wbauth serve` CLI | Python user process | — | Self-host alternative — runs locally; never talks to our hosted directory |
| `wbauth keygen --jwks-output` extension | Python user process | — | Pure file write; reuses Phase 1 `Identity.export_jwks()` |
| E2E manual test | Python script invoked by maintainer | Cloudflare Worker + Cloudflare research verifier | Exit-criterion gate; runs once per release, not in CI |

## Standard Stack

### Core (verified versions as of 2026-05-03)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `hono` | `^4.12.16` | TypeScript Workers router | [VERIFIED: npm view hono → 4.12.16, published 2026-04-30]. Web-Standards-based, ~14kb gzipped, first-class Cloudflare Workers + D1 + getConnInfo support. Ranked top in ctx7 search ("works on any JavaScript runtime including Cloudflare Workers"). [CITED: hono.dev/docs/getting-started/cloudflare-workers] |
| `web-bot-auth` | `^0.1.3` | RFC 9421 + Web Bot Auth verify/sign + directory response signing | [VERIFIED: npm view web-bot-auth → 0.1.3, published 2026-03-09]. Already a Phase 1 dep in `typescript/`; reuse in `directory/` for cross-language conformance. Exports verified via Context7 `/cloudflare/web-bot-auth`: `signatureHeaders`, `verify` from main; `signerFromJWK`, `verifierFromJWK` from `/crypto`; `directoryResponseHeaders` from the bundled `http-message-sig` (re-exported by main per the README). |
| `wrangler` | `^4.87.0` | Cloudflare deploy/dev/migrations CLI | [VERIFIED: existing devDep in `directory/package.json`, latest npm tag is 4.87.0]. Already validated working in Phase 1 Plan 01-01. |
| `@cloudflare/workers-types` | `^4.20260504.1` | Type definitions for Worker bindings | [VERIFIED: npm view → 4.20260504.1]. Provides `D1Database`, `ExecutionContext`, `Env` types used in handlers. |

### Supporting (verified)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@cloudflare/vitest-pool-workers` | `^0.15.2` | Worker-aware vitest runner with D1 isolation | Use for handler unit/integration tests that need a real D1 binding (without deploying). [CITED: developers.cloudflare.com/workers/testing/vitest-integration]. Provides `applyD1Migrations` test helper. |
| `vitest` | `^4` | Test framework | [VERIFIED: existing devDep in `typescript/package.json`]. Same as Phase 1 TypeScript SDK. |
| `zod` | `^4.4.3` | Runtime schema validation for request bodies | [VERIFIED: npm view zod → 4.4.3]. Use with `@hono/standard-validator` for JSON body validation on `/register/submit`. |
| `@hono/standard-validator` | `^0.2.2` | Hono ⇄ zod adapter | [VERIFIED: npm view → 0.2.2]. Standard pattern per Hono docs (`sValidator('json', schema)`). |

### Python (no new deps required)

The `wbauth register` CLI uses already-installed deps:

| Library | Already installed via | Purpose in Phase 3 |
|---------|----------------------|--------------------|
| `httpx>=0.28,<0.30` | `python/pyproject.toml` (Phase 2) | POST to `/register/challenge` + `/register/submit` |
| `cryptography>=47,<48` | `python/pyproject.toml` (Phase 1) | Already loaded by `Identity` for the user's signing key |
| stdlib `http.server` | Python ≥3.11 | `wbauth serve` static JWKS host |
| stdlib `argparse` | Python ≥3.11 | `wbauth register` / `wbauth serve` subcommand wiring |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hono | Raw `export default { fetch }` handler with hand-written URL routing | -1 dep but +200 LOC of routing/middleware glue. For 5 routes + IP extraction + JSON validation + rate-limit middleware, Hono pays for itself. CONTEXT.md D-54 already leans Hono. |
| Hono | itty-router (~1kb) | Smaller, but no built-in `getConnInfo` for Cloudflare Workers, no validator middleware, no per-environment-context generic types. Ergonomics loss outweighs the 12kb saving — neither cuts into Workers Free 1MB script-size limit. |
| Cloudflare native Rate Limit binding (`env.RATE_LIMITER.limit()`) | D1 small-row strategy (CONTEXT.md D-48) | The native binding's free-tier availability could not be confirmed from official docs (search verified: docs page has no pricing/tier statement). D1-table approach is portable, debuggable, and already in our schema budget. Decision locked by D-48. |
| `wrangler d1 migrations` (managed) | Raw `directory/schema.sql` + `wrangler d1 execute --file=` | Managed migrations are versioned and atomic per CLI [CITED: developers.cloudflare.com/workers/wrangler/commands/d1]: `wrangler d1 migrations create <db> <message>` then `wrangler d1 migrations apply <db>`. **Recommend wrangler-managed** — it auto-rollback on failure, captures backup, and tracks state in a `d1_migrations` table. Phase 1 used raw `schema.sql` for the throwaway hello-table; Phase 3 should adopt the managed flow now that schema will evolve. Resolves D-55. |
| Storing directory key as PKCS8 PEM in secret | Storing as JSON-stringified JWK in secret (private key included as `d`) | Workers WebCrypto's Ed25519 PKCS8 import support is genuinely ambiguous in the docs (see Open Question #2). `web-bot-auth/crypto.signerFromJWK` accepts a JWK directly and handles import internally — sidesteps the question entirely. **Recommended.** |
| GitHub `actions/deploy-pages@v4` | `peaceiris/actions-gh-pages@v4` | `actions-gh-pages` writes to a separate branch (gh-pages) which matches D-45's "snapshots/ in gh-pages branch". `actions/deploy-pages` is for full Pages-deploy uploads. **Use peaceiris** for snapshot-as-file, matches D-45 verbatim. |

**Installation** (run from `directory/`):

```bash
cd directory
npm install hono@^4.12.16 web-bot-auth@^0.1.3 zod@^4 @hono/standard-validator@^0.2
npm install -D @cloudflare/workers-types@^4 @cloudflare/vitest-pool-workers@^0.15 vitest@^4
```

**Version verification commands (run before locking):**

```bash
npm view hono version              # expect: 4.12.16 (verified 2026-05-03)
npm view web-bot-auth version      # expect: 0.1.3 (verified 2026-05-03)
npm view wrangler version          # expect: 4.87.0 (verified 2026-05-03)
npm view zod version               # expect: 4.4.3 (verified 2026-05-03)
npm view @hono/standard-validator version  # expect: 0.2.2 (verified 2026-05-03)
```

## Architecture Patterns

### System Architecture Diagram

```
                                  Phase 3 — Hosted Directory Surfaces
                                  =====================================

   ┌─────────────────────────┐                          ┌─────────────────────────────┐
   │ Python user (`wbauth`)  │                          │ Web Bot (any framework using │
   │                         │                          │  wbauth SDK or web-bot-auth) │
   │  wbauth register        │                          │                              │
   │   --identity key.pem    │                          │   signs HTTP request with    │
   │   --directory wbauth... │                          │   Signature-Agent: <our URL> │
   └────────────┬────────────┘                          └──────────────┬───────────────┘
                │ HTTPS                                                 │ HTTPS
                │ 1. POST /register/challenge {kid}                    │ GET /.well-known/.../{kid}
                │ 2. POST /register/submit  (RFC 9421-signed)          │
                ▼                                                       ▼
   ╔═══════════════════════════════════════════════════════════════════════════════════╗
   ║  Cloudflare Worker  (wbauth.silov801.workers.dev)   [Hono router on Workers Free] ║
   ║                                                                                   ║
   ║   ┌───────────────────────┐    ┌───────────────────────┐    ┌──────────────────┐ ║
   ║   │ /register/challenge   │    │ /register/submit      │    │ Read endpoints:  │ ║
   ║   │  • generate nonce     │    │  • validate body      │    │  /.well-known/   │ ║
   ║   │  • write challenge    │───▶│    (zod schema)       │───▶│    .../{kid}     │ ║
   ║   │    row + expiry       │    │  • verify Web Bot Auth│    │  /agents/{kid}   │ ║
   ║   │  • return {challenge, │    │    headers via        │    │  /agents         │ ║
   ║   │     expires_at}       │    │    web-bot-auth/crypto│    │  /static/all.json│ ║
   ║   └───────────┬───────────┘    │  • check blocklist    │    └────────┬─────────┘ ║
   ║               │                 │  • rate-limit gate    │             │           ║
   ║               │ writes          │  • UPSERT agents row  │             │ reads     ║
   ║               ▼                 └───────────┬───────────┘             ▼           ║
   ║   ┌───────────────────────────────────────────────────────────────────────────┐  ║
   ║   │  D1 (wbauth-directory)                                                    │  ║
   ║   │   • agents (kid PK + signature-agent-card columns + jwks blob)            │  ║
   ║   │   • registration_challenges (kid PK + nonce + expires_at)                 │  ║
   ║   │   • ratelimit (ip + day_bucket compound PK + count)                       │  ║
   ║   └───────────────────────────────────────────────────────────────────────────┘  ║
   ║                                                                                   ║
   ║   Worker Secret (read-only at runtime):                                           ║
   ║     DIRECTORY_PRIVATE_JWK = '{"kty":"OKP","crv":"Ed25519","d":"…","x":"…"}'      ║
   ║     ▲                                                                             ║
   ║     │ used by `signerFromJWK` for read-endpoint Signature/Signature-Input        ║
   ║     │ via `directoryResponseHeaders` helper                                       ║
   ╚═════│═════════════════════════════════════════════════════════════════════════════╝
         │
         │
   ┌─────┴──────────────────────────┐                  ┌──────────────────────────────────┐
   │ GitHub Actions (cron 02:00 UTC)│ ───── HTTPS ──── │ Snapshot sink:                   │
   │  • fetch /static/all.json      │  GET .../all.json│   gh-pages branch / wbauth-      │
   │  • write snapshot-YYYY-MM-DD   │                  │   snapshots repo (D-08-pending)  │
   │  • peaceiris/actions-gh-pages  │ ─── git push ──▶ │   /snapshots/                    │
   └────────────────────────────────┘                  └──────────────────────────────────┘
```

### Recommended Project Structure

```
directory/
├── wrangler.jsonc                # Updated: name=wbauth, new D1 binding
├── migrations/
│   ├── 0001_create_agents.sql              # Phase 3 Wave 1
│   ├── 0002_create_registration_challenges.sql
│   └── 0003_create_ratelimit.sql
├── src/
│   ├── index.ts                  # Hono app entry; mounts routers
│   ├── env.ts                    # Bindings type (DB, DIRECTORY_PRIVATE_JWK)
│   ├── blocklist.ts              # Reserved-name regex array (D-43)
│   ├── ratelimit.ts              # D1 small-row check + cleanup-on-write
│   ├── signing.ts                # Lazy signer init from secret JWK
│   ├── routes/
│   │   ├── register.ts           # /register/challenge + /register/submit
│   │   └── read.ts               # /.well-known/..., /agents, /agents/{kid}, /static/all.json
│   └── schemas.ts                # zod schemas for request bodies + Signature Agent Card shape
├── tests/
│   ├── handlers.test.ts          # Hono request/response assertions via app.request()
│   ├── verify.test.ts            # web-bot-auth verify happy path + rejection cases
│   └── ratelimit.test.ts         # D1 row count over 10 requests
├── package.json                  # Updated deps
├── tsconfig.json                 # New (Phase 1 had implicit; Phase 3 adds explicit)
└── README.md                     # Updated: Phase 3 contract + secret rotation procedure (D-56)

python/src/wbauth/
├── cli.py                        # Extended: register + serve subcommands
└── _http_server/                 # New: tiny static-JWKS server module
    └── jwks_server.py            # ~30 LOC stdlib http.server

python/scripts/
└── e2e_phase3.py                 # New: manual E2E gate (D-52)

.github/workflows/
└── snapshot.yml                  # New: nightly cron — disabled-by-default until D-08 resolves
```

### Pattern 1: Hono Worker Entry with D1 + Secret Binding

**What:** Single `Hono<{ Bindings: Env }>()` instance with typed bindings; routers mounted under path prefixes.

**When to use:** Always for Phase 3 — replaces the throwaway `export default { fetch }` from Phase 1.

**Example:**

```typescript
// directory/src/env.ts
export type Env = {
  DB: D1Database;
  DIRECTORY_PRIVATE_JWK: string; // JSON-stringified JWK
};

// directory/src/index.ts
// Source: hono.dev/docs/getting-started/cloudflare-workers (verified via Context7)
import { Hono } from "hono";
import type { Env } from "./env";
import { registerRouter } from "./routes/register";
import { readRouter } from "./routes/read";

const app = new Hono<{ Bindings: Env }>();

// Read endpoints — long cache, no auth
app.route("/", readRouter);

// Registration — POST only, rate-limited inside the router
app.route("/register", registerRouter);

// Health (no D1 hit; useful for uptime checks)
app.get("/healthz", (c) => c.json({ ok: true }));

export default app;
```

### Pattern 2: web-bot-auth Verifier Integration on `/register/submit`

**What:** The submit handler treats the incoming POST as the very thing being signed (the body IS the proof-of-key-ownership). Verify `Signature` + `Signature-Input` + `Signature-Agent` headers against the JWKS the client just submitted.

**When to use:** `POST /register/submit` only.

**Example:** see §4 below — full code sample with `verifierFromJWK` + `verify`.

### Pattern 3: Directory Response Signing via `directoryResponseHeaders`

**What:** For `GET /.well-known/http-message-signatures-directory/{kid}`, attach Signature/Signature-Input headers signed by the worker's own Ed25519 key — using the spec-aware helper from `web-bot-auth/http-message-sig` (re-exported from main as of 0.1.3).

**When to use:** Only the `/.well-known/...` endpoint per D-42 + spec. The plain `/agents/...` JSON endpoints stay unsigned (per D-41 — "JSON Cache-Control: max-age=60", no Signature requirement listed).

**Example:** see §3 + §4 below.

### Pattern 4: Per-IP Rate Limit with Cleanup-on-Write

**What:** D1 row keyed by `(ip, day_bucket)` where `day_bucket = floor(unixtime/86400)`. On each registration attempt, INSERT-or-UPDATE the row, read the count, reject if >=10. Once a day (best-effort, on the first write of any new day_bucket) DELETE rows where `day_bucket < today - 1`.

**When to use:** `/register/*` only (D-40). Read endpoints are unmetered.

**Example:** see §3 below.

### Anti-Patterns to Avoid

- **Storing the directory's Ed25519 private key as PKCS8 PEM in a secret.** Workers WebCrypto Ed25519 PKCS8 import support is documented inconsistently and community reports of "Invalid PKCS8 input" errors exist [CITED: community.cloudflare.com — "Persistent Invalid PKCS8 input Error with Worker Secrets"]. Use JSON-stringified JWK (`{"kty":"OKP","crv":"Ed25519","d":"…","x":"…","kid":"…"}`) and pass it through `web-bot-auth/crypto.signerFromJWK` — it handles the format internally and is the package's documented input shape.
- **Doing the verify work inside the route handler synchronously without try/catch.** `web-bot-auth.verify()` THROWS on every failure mode (expired, wrong tag, invalid sig). Catch and return 401 with the error message — surfacing the reason helps client-side debugging.
- **Calling `await env.DB.prepare(...).all()` in a tight loop.** Each call is a billable D1 read. Use `.batch([...])` or composite SQL for the rate-limit check + agents fetch.
- **Putting `wrangler` secrets in `wrangler.jsonc`.** Secrets are set via `wrangler secret put DIRECTORY_PRIVATE_JWK` and never committed [CITED: developers.cloudflare.com/workers/best-practices/workers-best-practices].
- **Caching D1 rows in module-level `let` variables.** Workers may run as multiple isolates; module state is per-isolate. Always read fresh from D1.
- **Running the E2E test (D-52) on every CI push.** D-52 explicitly says "manual run, not auto" — running it on push spams our own directory with junk registrations and burns the 100k req/day cap on noise.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| RFC 9421 signature verification | Custom signature-base canonicalizer | `web-bot-auth/crypto.verifierFromJWK` + `verify` | The spec is subtle (signature base canonicalization, derived components, content-digest, structured-fields quoting). Cloudflare's lib is the reference TS impl. |
| RFC 9421 signature production for the directory | Custom Signature-Input formatter | `web-bot-auth/http-message-sig.directoryResponseHeaders` | This helper is purpose-built for the spec's tag `"http-message-signatures-directory"` and component list (`@authority` with `req` flag) [CITED: ctx7 /cloudflare/web-bot-auth — directoryResponseHeaders APIDOC]. |
| Ed25519 keypair handling on Workers | Hand-rolled `crypto.subtle.importKey` PKCS8 | `signerFromJWK({kty,crv,d,x})` | Workers' WebCrypto Ed25519 PKCS8 support is ambiguous (see Open Question #2). JWK + library helper is unambiguously supported. |
| HTTP routing | Manual `if (url.pathname === ...)` ladder | Hono | Hono's `c.req.param('kid')`, validator middleware, `c.json()` shorthand pay for themselves at 5+ routes. |
| JSON body validation | `await request.json()` + manual shape check | `sValidator('json', zodSchema)` | Single-line schema enforcement; consistent error responses; type narrowing for `c.req.valid('json')`. |
| Per-IP IP extraction | `request.headers.get('cf-connecting-ip')` ad-hoc | `getConnInfo(c).remote.address` from `hono/cloudflare-workers` | Tested helper; `cf-connecting-ip` is the canonical Cloudflare header but the helper handles edge cases (IPv6, missing header) consistently [CITED: hono.dev/docs/helpers/conninfo]. |
| RFC 7638 thumbprint computation (Python register CLI side) | Re-derive kid from JWK | `Identity.kid` (already computed in Phase 1) | Identity already computes and exposes the kid. Don't re-derive. |
| JWK export for register submit body | Hand-build `{kty, crv, x}` | `Identity.export_jwks()` (Phase 1) | Already returns `{"keys":[…]}`. Reuse. |
| Static file serving for `wbauth serve` | Bare TCP socket loop | `http.server.ThreadingHTTPServer` from stdlib | 30 LOC stdlib path is the whole point of D-50; no Flask/FastAPI dependency. |

**Key insight:** Every cryptographic operation in Phase 3 has a battle-tested wrapper in `cloudflare/web-bot-auth` 0.1.3. The risk surface is purely in **wiring** (route handlers, D1 schema, blocklist regex, rate-limit accounting) — not in cryptography.

## Common Pitfalls

### Pitfall 1: `Cache-Control: immutable` on a kid-keyed JWKS endpoint

**What goes wrong:** D-41 says `/.well-known/.../{kid}` is `Cache-Control: public, max-age=300, immutable`. But `immutable` semantically means "this URL's response will never change" — and an agent can re-register with the same kid (after key rotation overlap) and update the JWKS. Cached `immutable` responses won't be re-validated for `max-age=300` even if the underlying record changes.

**Why it happens:** "Immutable" feels right for a JWKS-by-thumbprint endpoint (the kid IS the content-hash of the public key) — but the wrapping JWKS document includes other keys (multi-key rotation) and can change.

**How to avoid:** Drop `immutable`; use plain `Cache-Control: public, max-age=300`. The kid pinning still gives 5 minutes of CDN cache benefit. If absolute immutability is desired, address it via a versioned URL (out of v1 scope per CONTEXT.md `deferred`).

**Warning signs:** "I rotated my key and verifiers still see the old JWKS for 5 minutes" complaints from Phase 4 demo users.

**[FLAG TO PLANNER:** This contradicts the literal D-41 text. Recommend planner surfaces this in the discuss phase or adds a 1-line CONTEXT amendment dropping `immutable`. **]**

### Pitfall 2: Workers 10ms CPU limit + Ed25519 sign timing

**What goes wrong:** Free-tier Workers have a hard 10ms CPU budget per request. Ed25519 signing in WebCrypto is fast (<1ms) but JSON serialization + multiple D1 reads + signing can stack.

**Why it happens:** "I added one more D1 query" creep over the lifetime of the project.

**How to avoid:** For `/.well-known/.../{kid}`: 1 D1 read (`SELECT keys, signature_agent_url FROM agents WHERE kid = ?`) + 1 sign + JSON.stringify. Should run well under 10ms. Watch the `Worker exceeded CPU time` errors in `wrangler tail` and budget accordingly. CPU time excludes I/O wait per [CITED: developers.cloudflare.com/workers/platform/limits "CPU time measures only the time spent executing Worker code, not network requests like fetch calls or database queries"], so D1 wait time is free.

**Warning signs:** `Error 1101: Worker exceeded CPU time limit` in production logs.

### Pitfall 3: D1 JSON column queries

**What goes wrong:** D-36 stores JWKS as a `keys TEXT NOT NULL` JSON blob. If you ever try `WHERE json_extract(keys, '$.keys[0].kid') = ?` you'll discover D1 doesn't index JSON columns and the query scans every row.

**Why it happens:** It feels natural to query inside the JWKS blob ("find the agent whose JWKS contains key X").

**How to avoid:** Don't do it. The kid is the primary key; lookups go through `kid`. If multi-key reverse-lookup is ever needed (post-v1), denormalize into a `kid_aliases` table.

### Pitfall 4: Rate-limit table cleanup never runs

**What goes wrong:** The `ratelimit` table accumulates one row per (IP, day) forever. After a year, it's millions of rows and `INSERT` slows down (and counts toward the 100k writes/day limit).

**Why it happens:** "Cleanup-on-write" sounds simple but is easy to forget — the cleanup branch only fires when a NEW day_bucket is first written for any IP, and an idle directory might not get traffic for hours into a new day.

**How to avoid:** Cleanup-on-write of expired rows MUST run inside the same transaction as the rate-limit check (use `.batch([...])` to batch the SELECT/UPSERT with a `DELETE FROM ratelimit WHERE day_bucket < ?` where `?` = today_bucket - 1). Even if cleanup is delayed, the table grows linearly (1 row per IP per day used). At our scale, the 100k writes/day cap is never the bottleneck; storage is. 5GB / ~30 bytes/row = ~166M rows max. Year-long retention is fine even at 100k IPs/day. Still: clean up to be tidy.

### Pitfall 5: `Signature-Agent` header malformed in registration submit

**What goes wrong:** Web Bot Auth requires `Signature-Agent` to be a Structured Field string (double-quoted), HTTPS scheme, and ALSO listed in the signed component list. Three separate failure modes that all produce "verification failed" without distinguishing which.

**Why it happens:** The client (`wbauth.sign()`) already handles this — but if Phase 3's Python `wbauth register` re-implements the signing inline instead of calling `wbauth.sign()`, the bug surface returns.

**How to avoid:** `wbauth register` MUST construct a `NormalizedRequest` and call `sign()` from `wbauth.signer`. Reuse the Phase 1 primitive verbatim. Phase 1's daily-cron passes Cloudflare's verifier — by transitivity, registration submit will pass our Worker verifier (same library).

**Warning signs:** Worker logs show "verification failed" with the Signature-Agent header value mismatching what's in the signed component list.

### Pitfall 6: D1 migration ordering on production

**What goes wrong:** `wrangler d1 migrations apply wbauth-directory` on production runs all migrations in order. If a developer hand-edits an applied migration file, prod and local diverge silently.

**Why it happens:** "Quick fix to migration 0001" feels harmless during development.

**How to avoid:** Once a migration is applied to production (via `--remote`), it's immutable. To change schema later, create a new migration. Document this rule in `directory/README.md` per D-56's spirit.

### Pitfall 7: GitHub Actions snapshot job runs before D-08 resolves

**What goes wrong:** `.github/workflows/snapshot.yml` references `gh-pages` branch or a `wbauth-snapshots` repo that doesn't exist yet (D-08, GitHub-org choice, deferred to Phase 5 per Phase 1 carry-forward).

**Why it happens:** Phase 3 ships the workflow file; the cron triggers on its schedule regardless of repo state.

**How to avoid:** Ship the workflow with `if: false` at the job level OR with a placeholder schedule that never fires (e.g., commented-out `- cron: ...`). Add a TODO comment pointing to Phase 5 to enable it. Alternative: ship the script (`scripts/snapshot.sh`) and an example workflow file under `examples/` rather than `.github/workflows/`. Resolves the chicken-and-egg.

**Warning signs:** GitHub email "scheduled workflow failed" once a day after Phase 3 ships.

## Code Examples

Verified patterns from Context7 / official docs. Use as starting templates in plans.

### Example 1: Wrangler config for production

```jsonc
// directory/wrangler.jsonc — Phase 3 production
// Source: developers.cloudflare.com/workers/wrangler/configuration (verified via ctx7)
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "wbauth",
  "main": "src/index.ts",
  "compatibility_date": "2026-05-01",
  "compatibility_flags": ["nodejs_compat"],

  "d1_databases": [
    {
      "binding": "DB",
      "database_name": "wbauth-directory",
      "database_id": "<filled by `wrangler d1 create wbauth-directory`>",
      "migrations_dir": "migrations"
    }
  ],

  "observability": { "enabled": true }

  // Secrets are NOT in this file:
  //   wrangler secret put DIRECTORY_PRIVATE_JWK
}
```

### Example 2: D1 schema (managed migrations)

```bash
# One-time:
cd directory
npx wrangler d1 create wbauth-directory
# (paste returned database_id into wrangler.jsonc)
npx wrangler d1 migrations create wbauth-directory create_agents
# (edit generated migrations/0001_create_agents.sql; see below)
npx wrangler d1 migrations apply wbauth-directory --local   # for dev
npx wrangler d1 migrations apply wbauth-directory --remote  # for prod
```

```sql
-- directory/migrations/0001_create_agents.sql
-- Per CONTEXT.md D-36
CREATE TABLE IF NOT EXISTS agents (
  kid                  TEXT PRIMARY KEY,
  client_name          TEXT NOT NULL,
  client_uri           TEXT,
  signature_agent_url  TEXT NOT NULL,
  expected_user_agent  TEXT,
  contacts             TEXT,    -- JSON array as string
  purpose              TEXT,
  targeted_content     TEXT,
  rate_control         TEXT,
  keys                 TEXT NOT NULL,  -- JWKS JSON blob
  created_at           INTEGER NOT NULL,
  last_updated         INTEGER NOT NULL
);

-- Index for paginated /agents listing (ORDER BY created_at DESC LIMIT 50 OFFSET ?)
CREATE INDEX IF NOT EXISTS idx_agents_created_at ON agents(created_at DESC);
```

```sql
-- directory/migrations/0002_create_registration_challenges.sql
-- Per CONTEXT.md D-38 (two-step proof-of-key-ownership)
CREATE TABLE IF NOT EXISTS registration_challenges (
  kid         TEXT PRIMARY KEY,
  nonce       TEXT NOT NULL,        -- 128-bit random, hex-encoded
  expires_at  INTEGER NOT NULL      -- unixtime; cleanup-on-write of past rows
);
```

```sql
-- directory/migrations/0003_create_ratelimit.sql
-- Per CONTEXT.md D-40, D-48 (per-IP D1 small-row strategy)
CREATE TABLE IF NOT EXISTS ratelimit (
  ip          TEXT NOT NULL,
  day_bucket  INTEGER NOT NULL,     -- floor(unixtime / 86400)
  count       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (ip, day_bucket)
);
```

### Example 3: `POST /register/challenge` handler

```typescript
// directory/src/routes/register.ts
// Source: synthesized from hono.dev validator docs + ctx7 web-bot-auth verify pattern
import { Hono } from "hono";
import { sValidator } from "@hono/standard-validator";
import { getConnInfo } from "hono/cloudflare-workers";
import * as z from "zod";
import type { Env } from "../env";
import { checkAndIncrementRateLimit } from "../ratelimit";

export const registerRouter = new Hono<{ Bindings: Env }>();

const ChallengeBody = z.object({
  kid: z.string().min(20).max(80), // RFC 7638 base64url SHA-256 = ~43 chars
});

registerRouter.post("/challenge", sValidator("json", ChallengeBody), async (c) => {
  const { kid } = c.req.valid("json");
  const ip = getConnInfo(c).remote.address ?? "unknown";

  // Rate-limit gate (10/day/IP per D-40, D-48)
  const allowed = await checkAndIncrementRateLimit(c.env.DB, ip);
  if (!allowed) {
    return c.json({ error: "rate_limited", retry_after_seconds: 3600 }, 429);
  }

  // Generate 128-bit nonce as hex
  const nonceBytes = new Uint8Array(16);
  crypto.getRandomValues(nonceBytes);
  const nonce = Array.from(nonceBytes, (b) => b.toString(16).padStart(2, "0")).join("");

  const now = Math.floor(Date.now() / 1000);
  const expiresAt = now + 300; // 5 min

  // UPSERT — re-issuing a challenge for the same kid replaces the old nonce.
  await c.env.DB.prepare(
    `INSERT INTO registration_challenges (kid, nonce, expires_at)
     VALUES (?1, ?2, ?3)
     ON CONFLICT(kid) DO UPDATE SET nonce = ?2, expires_at = ?3`
  )
    .bind(kid, nonce, expiresAt)
    .run();

  return c.json({ challenge: nonce, expires_at: expiresAt });
});
```

### Example 4: `POST /register/submit` handler

```typescript
// directory/src/routes/register.ts (continued)
// Source: ctx7 /cloudflare/web-bot-auth — verify pattern + D-38, D-43
import { verify } from "web-bot-auth";
import { verifierFromJWK } from "web-bot-auth/crypto";
import { isReservedName } from "../blocklist";

const SubmitBody = z.object({
  kid: z.string(),
  challenge: z.string(),
  client_name: z.string().min(1).max(80),
  client_uri: z.string().url().optional(),
  signature_agent_url: z.string().url().refine((u) => u.startsWith("https://")),
  expected_user_agent: z.string().optional(),
  contacts: z.array(z.string()).optional(),
  purpose: z.string().optional(),
  targeted_content: z.string().optional(),
  rate_control: z.string().optional(),
  keys: z.object({
    keys: z.array(
      z.object({
        kty: z.literal("OKP"),
        crv: z.literal("Ed25519"),
        kid: z.string(),
        x: z.string(),
      })
    ).min(1),
  }),
});

registerRouter.post("/submit", sValidator("json", SubmitBody), async (c) => {
  const body = c.req.valid("json");
  const ip = getConnInfo(c).remote.address ?? "unknown";

  // Rate-limit also gates submit (separate from challenge — D-40 says "/register/*").
  const allowed = await checkAndIncrementRateLimit(c.env.DB, ip);
  if (!allowed) return c.json({ error: "rate_limited" }, 429);

  // Blocklist (D-43, D-44)
  const blocked = isReservedName(body.client_name);
  if (blocked) {
    return c.json(
      {
        error: "reserved_name",
        blocked_token: blocked,
        guidance:
          "If you represent this organization and want this name on agentpassport, contact <maintainer-email-TBD-Phase-5>",
      },
      422
    );
  }

  // Validate the kid in the body matches the kid in the JWKS
  const jwk = body.keys.keys.find((k) => k.kid === body.kid);
  if (!jwk) return c.json({ error: "kid_not_in_jwks" }, 400);

  // Validate challenge — must exist, not expired
  const ch = await c.env.DB.prepare(
    `SELECT nonce, expires_at FROM registration_challenges WHERE kid = ?`
  )
    .bind(body.kid)
    .first<{ nonce: string; expires_at: number }>();

  if (!ch) return c.json({ error: "no_challenge" }, 400);
  if (ch.nonce !== body.challenge) return c.json({ error: "wrong_challenge" }, 400);
  if (ch.expires_at < Math.floor(Date.now() / 1000)) {
    return c.json({ error: "challenge_expired" }, 400);
  }

  // Reconstruct the request the client signed and verify
  // (the client signed THIS POST request via wbauth.sign())
  const verifier = await verifierFromJWK(jwk);
  try {
    await verify(c.req.raw, verifier);
  } catch (err) {
    return c.json({ error: "signature_invalid", reason: String(err) }, 401);
  }

  // UPSERT agents row
  const now = Math.floor(Date.now() / 1000);
  await c.env.DB.prepare(
    `INSERT INTO agents (
       kid, client_name, client_uri, signature_agent_url, expected_user_agent,
       contacts, purpose, targeted_content, rate_control, keys,
       created_at, last_updated
     ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?11)
     ON CONFLICT(kid) DO UPDATE SET
       client_name = ?2,
       client_uri = ?3,
       signature_agent_url = ?4,
       expected_user_agent = ?5,
       contacts = ?6,
       purpose = ?7,
       targeted_content = ?8,
       rate_control = ?9,
       keys = ?10,
       last_updated = ?11`
  )
    .bind(
      body.kid,
      body.client_name,
      body.client_uri ?? null,
      body.signature_agent_url,
      body.expected_user_agent ?? null,
      JSON.stringify(body.contacts ?? []),
      body.purpose ?? null,
      body.targeted_content ?? null,
      body.rate_control ?? null,
      JSON.stringify(body.keys),
      now
    )
    .run();

  // Burn the challenge after successful registration
  await c.env.DB.prepare(`DELETE FROM registration_challenges WHERE kid = ?`).bind(body.kid).run();

  const directoryUrl = `${new URL(c.req.url).origin}/.well-known/http-message-signatures-directory/${body.kid}`;
  return c.json({ kid: body.kid, directory_url: directoryUrl }, 201);
});
```

### Example 5: `GET /.well-known/.../{kid}` signed JWKS handler

```typescript
// directory/src/routes/read.ts
// Source: ctx7 /cloudflare/web-bot-auth — directoryResponseHeaders APIDOC + D-41, D-42
import { Hono } from "hono";
import { directoryResponseHeaders } from "web-bot-auth/http-message-sig";
import { signerFromJWK } from "web-bot-auth/crypto";
import type { Env } from "../env";

export const readRouter = new Hono<{ Bindings: Env }>();

readRouter.get("/.well-known/http-message-signatures-directory/:kid", async (c) => {
  const kid = c.req.param("kid");

  const row = await c.env.DB.prepare(`SELECT keys FROM agents WHERE kid = ?`)
    .bind(kid)
    .first<{ keys: string }>();

  if (!row) return c.json({ error: "not_found" }, 404);

  const jwks = JSON.parse(row.keys);
  const body = JSON.stringify(jwks);

  // Sign the response using the directory's own key (D-42)
  const directoryJWK = JSON.parse(c.env.DIRECTORY_PRIVATE_JWK);
  const signer = await signerFromJWK(directoryJWK);

  const now = new Date();
  const sigHeaders = await directoryResponseHeaders(
    {
      response: {
        status: 200,
        headers: { "content-type": "application/http-message-signatures-directory+json" },
      },
      request: { method: "GET", url: c.req.url, headers: {} },
    },
    [signer],
    {
      created: now,
      expires: new Date(now.getTime() + 300_000), // 5 min validity
    }
  );

  return new Response(body, {
    status: 200,
    headers: {
      "content-type": "application/http-message-signatures-directory+json",
      "cache-control": "public, max-age=300", // see Pitfall 1: drop "immutable"
      Signature: sigHeaders["Signature"],
      "Signature-Input": sigHeaders["Signature-Input"],
    },
  });
});

// /agents/{kid} — full Signature Agent Card (unsigned, JSON, short cache)
readRouter.get("/agents/:kid", async (c) => {
  const kid = c.req.param("kid");
  const row = await c.env.DB.prepare(
    `SELECT kid, client_name, client_uri, signature_agent_url, expected_user_agent,
            contacts, purpose, targeted_content, rate_control, keys,
            created_at, last_updated
     FROM agents WHERE kid = ?`
  )
    .bind(kid)
    .first();

  if (!row) return c.json({ error: "not_found" }, 404);

  // Re-hydrate JSON-encoded columns
  const card = {
    ...row,
    contacts: JSON.parse((row as any).contacts ?? "[]"),
    keys: JSON.parse((row as any).keys),
  };
  return c.json(card, 200, { "cache-control": "public, max-age=60" });
});

// /agents — paginated list (50/page)
readRouter.get("/agents", async (c) => {
  const all = c.req.query("all") === "true";
  const page = Math.max(1, parseInt(c.req.query("page") ?? "1", 10));
  const limit = all ? 10000 : 50;
  const offset = (page - 1) * limit;

  const { results } = await c.env.DB.prepare(
    `SELECT kid, client_name, signature_agent_url, created_at
     FROM agents ORDER BY created_at DESC LIMIT ? OFFSET ?`
  )
    .bind(limit, offset)
    .all();

  return c.json({ page, count: results.length, agents: results }, 200, {
    "cache-control": "public, max-age=300",
  });
});
```

### Example 6: Rate-limit module

```typescript
// directory/src/ratelimit.ts
// Source: synthesized from D-48 + Pitfall 4 cleanup-on-write pattern
const PER_IP_PER_DAY = 10;

export async function checkAndIncrementRateLimit(
  db: D1Database,
  ip: string
): Promise<boolean> {
  const dayBucket = Math.floor(Date.now() / 1000 / 86400);

  // Atomic UPSERT-then-check via .batch (single round-trip)
  const [, , countRow] = await db.batch([
    db.prepare(`DELETE FROM ratelimit WHERE day_bucket < ?`).bind(dayBucket - 1),
    db
      .prepare(
        `INSERT INTO ratelimit (ip, day_bucket, count) VALUES (?1, ?2, 1)
         ON CONFLICT(ip, day_bucket) DO UPDATE SET count = count + 1`
      )
      .bind(ip, dayBucket),
    db
      .prepare(`SELECT count FROM ratelimit WHERE ip = ? AND day_bucket = ?`)
      .bind(ip, dayBucket),
  ]);

  const count = (countRow.results?.[0] as { count: number } | undefined)?.count ?? 0;
  return count <= PER_IP_PER_DAY;
}
```

### Example 7: Reserved-name blocklist module

```typescript
// directory/src/blocklist.ts
// Per D-43
const TOKENS = [
  "google", "openai", "anthropic", "cloudflare", "microsoft",
  "meta", "apple", "amazon", "aws", "github", "stripe", "shopify",
];
const SUFFIXES = ["bot", "agent", "crawler"];

export function isReservedName(name: string): string | null {
  const lower = name.toLowerCase();

  // Exact match (case-insensitive)
  for (const t of TOKENS) {
    if (lower === t) return t;
  }
  // Substring match if combined with a bot-y suffix
  for (const t of TOKENS) {
    if (lower.includes(t)) {
      for (const s of SUFFIXES) {
        if (lower.includes(s)) return t;
      }
    }
  }
  return null;
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| FastAPI + SQLite-on-Fly-volume directory backend (PROJECT.md original; STACK.md primary recommendation) | TypeScript + Cloudflare Workers + D1 | Phase 1 D-02 (zero-billing pivot, 2026-05-03) | Phase 3 plans must NOT propose FastAPI; the deferred section explicitly says "TypeScript-on-Workers vs Python-on-Fly.io path is rejected and should not be re-proposed without explicit re-discussion". |
| `wbauth serve` as a full FastAPI directory backend (CLI-05 original wording) | Stdlib http.server static JWKS host (~30 LOC, D-50) | CONTEXT.md D-50 (Phase 3) | Trims `wbauth serve` from "self-hostable directory" to "self-hostable single-JWKS server". The full directory experience IS the hosted Worker. |
| `pnpm` (D-10 original) | `npm` workspaces (D-10 updated 2026-05-03) | Phase 1 Plan 02 (pnpm not on dev machine) | Use `npm install` everywhere in `directory/`; lockfile is `package-lock.json`. |
| Cloudflare debug at `crawltest.com/cdn-cgi/web-bot-auth` (REQUIREMENTS.md original) | Cloudflare research verifier `http-message-signatures-example.research.cloudflare.com` | Phase 1 Plan 04 empirical discovery | `crawltest.com` is the verified-bots gate (closed; requires Cloudflare-side approval — that's Phase 5 DIST-08). The research verifier is the open-spec gate — use for E2E (D-52). |

**Deprecated/outdated:**
- `NODE-ED25519` algorithm string in WebCrypto: still works but is the legacy non-standard form per [CITED: developers.cloudflare.com/workers/runtime-apis/web-crypto "Legacy non-standard EdDSA is supported for the Ed25519 curve via NODE-ED25519, in addition to the Secure Curves version"]. Plain `"Ed25519"` is the modern algorithm name. We sidestep this entirely by using `web-bot-auth/crypto.signerFromJWK` which encapsulates the algorithm choice.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `web-bot-auth/crypto.signerFromJWK` accepts a JWK with the `d` field set and uses a Workers-supported import path internally | §4 Pattern 3 + Example 5 | If Workers WebCrypto can't import JWK Ed25519 with `d`, the directory can't sign responses. Mitigation: smoke-test on the live Worker in Wave 1; fallback is to import `x` only (verifier-only) and skip response signing temporarily. [ASSUMED — Cloudflare's lib has a Workers example in `examples/verification-workers/` per the README; signing on Workers is documented for Puppeteer use case, but the directory-server signing path specifically is community-untested in our review.] |
| A2 | `verify(c.req.raw, verifier)` works on Hono's `c.req.raw` (a real `Request` object) without modification | §4 Example 4 | If the Hono request object isn't compatible (e.g., body already consumed), verification fails with a confusing error. Mitigation: in handler tests, assert `c.req.raw` is a `Request` instance and body is intact. [ASSUMED based on the docs example using a stock `new Request()` object.] |
| A3 | Hono `app.request(req)` test pattern works under `@cloudflare/vitest-pool-workers` with a real D1 binding | §4 tests | If not, fall back to `npx wrangler dev` + curl-based integration tests. [ASSUMED — the vitest-pool-workers docs document `applyD1Migrations` for exactly this scenario, but the combination with Hono's test pattern is unverified.] |
| A4 | Workers Free tier 100k req/day is per Worker (not per account) | §3 §6 | If per-account, Phase 1's `wbauth-day1-test` Worker shares the budget. Mitigation: either delete day1-test (CONTEXT.md says optional) or accept slight headroom loss. [ASSUMED — Cloudflare docs are ambiguous; conservative interpretation is per-account.] |
| A5 | `wrangler d1 migrations apply --remote` works against the production D1 from a developer machine (no CI required) | §3 Example 2 + Plan layout | If GH OIDC is required for prod migrations, dev-driven migration apply fails. Mitigation: locked Cloudflare account already authenticated via `wrangler login`. [ASSUMED based on Phase 1 Plan 01 working pattern.] |
| A6 | The directory's own kid does not need to be registered in `agents` table for the published `/.well-known/http-message-signatures-directory/` (no-kid) endpoint to work | §3 §4 Example 5 | If verifiers expect to GET the directory's own JWKS the same way they GET an agent's JWKS, we need a "self" route that returns the directory's public JWK without DB hit. Mitigation: add a special-case route `GET /.well-known/http-message-signatures-directory` (no kid, root) that serves the directory's public JWK derived from `DIRECTORY_PRIVATE_JWK`. Recommend planner adds this as an explicit task. [ASSUMED — the spec (per WebFetch of draft-meunier-...-directory-05) says the well-known URI returns the directory's own keys; per-kid sub-paths aren't standard but D-41 specifies them as our convention.] |
| A7 | Hono's `getConnInfo(c).remote.address` returns `cf-connecting-ip` value on Cloudflare Workers | §3 Example 3 | If it returns the wrong value (e.g., the closest hop), rate-limiting becomes broken. Mitigation: assert against `c.req.header('cf-connecting-ip')` in tests; both should match. [CITED: hono.dev/docs/helpers/conninfo — Cloudflare-Workers-specific helper documented.] |
| A8 | The phase requirement IDs in CONTEXT.md (DIR-01..05,07,08; CLI-04,05) match the canonical REQUIREMENTS.md IDs | §Phase Requirements | If a Phase 3 requirement ID is misaligned, the planner builds the wrong feature. Mitigation: cross-checked the IDs against REQUIREMENTS.md lines 44-65 — all 9 IDs match. [VERIFIED: Read of REQUIREMENTS.md.] |

## Open Questions

1. **Directory's own JWKS publication path**
   - **What we know:** D-42 says "directory holds its own Ed25519 keypair" and "kid for the directory's own key is published at the root of `/.well-known/http-message-signatures-directory/` so verifiers can trust the directory's signed responses".
   - **What's unclear:** Is the root path `/.well-known/http-message-signatures-directory` (no trailing slash, no kid) — and does it return ONLY the directory's own key, or all agents' keys, or both? The spec (per WebFetch above) describes this single endpoint as "all active keys" but our convention introduces a per-kid sub-path for individual agents.
   - **Recommendation:** Implement both: root path serves only the directory's own key (1-element JWKS); per-kid sub-path serves the agent's JWKS. Document this in the directory README so external verifiers know which to fetch.

2. **Workers WebCrypto Ed25519 PKCS8 vs JWK private-key import**
   - **What we know:** Cloudflare docs say "Unlike NodeJS, Cloudflare will not support raw import of private keys" but don't enumerate which formats DO work for Ed25519 private keys.
   - **What's unclear:** Whether `format: "pkcs8"` or `format: "jwk"` (with `d` field) is officially supported for `algorithm: "Ed25519"` private-key import. Community reports of "Invalid PKCS8 input" exist.
   - **Recommendation:** Use `web-bot-auth/crypto.signerFromJWK` (passes JWK including `d` to whatever import path the lib uses). If it fails on the live Worker, file a Cloudflare community issue and fall back to a hand-rolled `crypto.subtle.importKey("jwk", {...d}, {name:"Ed25519"}, false, ["sign"])`. Smoke-test on first deploy.

3. **GitHub Actions snapshot target before D-08 resolves**
   - **What we know:** D-45 specifies `gh-pages` branch / `wbauth-snapshots` repo; D-08 (GitHub-org choice) is deferred to Phase 5.
   - **What's unclear:** Whether to ship `.github/workflows/snapshot.yml` in Phase 3 (and risk Pitfall 7 "scheduled workflow failed" daily emails) or defer the workflow file to Phase 5.
   - **Recommendation:** Ship `scripts/snapshot.sh` in Phase 3 (the actual logic — fetch + write). Ship `.github/workflows/snapshot.yml` with the schedule **commented out** and a TODO pointing to Phase 5 D-08 resolution. Phase 5 enables the cron in the same commit that adds the GitHub remote. This satisfies DIR-05 ("snapshot job exists") without triggering Pitfall 7.

4. **Cache-Control `immutable` on a kid-keyed but multi-key endpoint (Pitfall 1)**
   - **What we know:** D-41 literally says `Cache-Control: public, max-age=300, immutable` for `/.well-known/.../{kid}`.
   - **What's unclear:** Whether the user intended `immutable` semantically (response will NEVER change) or just "cache aggressively". Multi-key rotation (allowed by D-37) means the JWKS at a given kid CAN change.
   - **Recommendation:** Drop `immutable`. Keep `max-age=300`. Surface to user in discuss-phase if planner is uncertain.

5. **Reserved-name blocklist case sensitivity for substring rule (D-43)**
   - **What we know:** D-43 says "exact (case-insensitive)" for the strict list, then "any `client_name` containing those tokens as substrings IF combined with `bot`/`agent`/`crawler`".
   - **What's unclear:** Is the substring check ALSO case-insensitive? "GoogleBot" — does it match? My implementation in §3 Example 7 lowercases first; this is the safe choice.
   - **Recommendation:** Lowercase before substring check. Document in `blocklist.ts` comment.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | wrangler, vitest, hono build | ✓ | 22.22.2 (Phase 1 verified) | — |
| npm | dependency install | ✓ | 10.9.7 (Phase 1 verified) | — |
| `npx wrangler` | Worker deploy + D1 migrations | ✓ | 4.87.0 (devDep in `directory/`) | — |
| Cloudflare Workers Free tier | Production hosting | ✓ | account silov801@gmail.com / 2a1e5d83dbc5d553a3537d7a79009899 | — |
| Cloudflare D1 Free tier | Persistent storage | ✓ | 5GB + 5M reads/day + 100k writes/day | — |
| Python 3.11+ | `wbauth register` / `wbauth serve` | ✓ | per `pyproject.toml` requires-python=>=3.11 | — |
| `httpx` | Python register CLI HTTPS POST | ✓ | already in `python/pyproject.toml` (Phase 2) | — |
| `cryptography` | Used transitively via Identity | ✓ | already (Phase 1) | — |
| `wbauth.sign()` Python primitive | register CLI signing | ✓ | already (Phase 1) | — |
| `web-bot-auth` 0.1.3 npm | TS verify + sign + directoryResponseHeaders | ✓ | already in `typescript/package.json`; needs adding to `directory/package.json` | — |
| `hono` 4.12.x | Router | ✗ | — to be installed | None — install. |
| `zod` 4.x | Body validation | ✗ | — to be installed | hand-roll JSON validation (~50 LOC); zod recommended. |
| `@hono/standard-validator` 0.2.x | Hono ⇄ zod | ✗ | — to be installed | use raw `validator()` from `hono/validator` with manual zod parse. |
| `@cloudflare/vitest-pool-workers` 0.15.x | Worker-aware test infra | ✗ | — to be installed | run integration tests via `wrangler dev` + curl. Vitest-pool-workers is preferred. |
| GitHub Pages | Snapshot sink | ⚠ blocked on D-08 | — | Defer enabling the workflow until Phase 5. |
| GitHub Actions runner | Cron snapshot job | ✓ (when D-08 resolves) | — | — |
| `gh-pages` branch / `wbauth-snapshots` repo | Snapshot destination | ✗ | does not exist (D-08 deferred) | Per Open Question #3, ship script + disabled workflow; Phase 5 enables. |

**Missing dependencies with no fallback:**
- None.

**Missing dependencies with fallback:**
- `hono`, `zod`, `@hono/standard-validator`, `@cloudflare/vitest-pool-workers` — all on npm; install in Wave 1.
- GitHub Pages snapshot sink — defer enable to Phase 5 (Open Question #3).

## Validation Architecture

`workflow.nyquist_validation` is `false` in `.planning/config.json` — **section omitted** per RESEARCH.md template.

## Security Domain

`workflow.security_enforcement: true` and `security_asvs_level: 1` per `.planning/config.json`. Phase 3 introduces the first public-network attack surface in the project (read endpoints + registration) so this section is mandatory.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Proof-of-key-ownership via RFC 9421 signature verify (D-38). The kid IS the identity; no passwords/tokens to manage. |
| V3 Session Management | no | Stateless — no cookies, no session tokens. Each registration submit re-authenticates via signature. |
| V4 Access Control | yes | Reserved-name blocklist (D-43, D-44) is the only access-control surface. Read endpoints are intentionally public per spec. |
| V5 Input Validation | yes | `zod` schemas on every POST body; strict `signature_agent_url` URL + scheme check; `client_name` length limits. |
| V6 Cryptography | yes | `web-bot-auth/crypto` for verify + sign — never hand-roll. Workers WebCrypto for randomness (`crypto.getRandomValues` for nonces). |
| V7 Error Handling & Logging | partial | Worker errors return JSON with error codes; no stack traces leaked. `wrangler tail` for ops debugging — secrets MUST never appear in logs. |
| V8 Data Protection | yes | The directory key is the most sensitive secret. Stored as Cloudflare Worker secret (encrypted-at-rest), never logged, never in `wrangler.jsonc`, rotation procedure documented per D-56. |
| V9 Communication | yes | Workers force HTTPS at the edge — no HTTP fallback. `signature_agent_url` is enforced HTTPS in zod schema. |
| V10 Malicious Code | n/a | No file uploads, no eval, no dynamic code paths. |
| V11 Business Logic | yes | Rate limit (10/IP/day, D-40) + blocklist + nonce-burn-after-use prevent replay/abuse. |
| V12 Files & Resources | n/a | No filesystem on Workers. |
| V13 API & Web Service | yes | Strict content-type on response (`application/http-message-signatures-directory+json` per spec); CORS NOT enabled (no browser-side consumers in v1). |
| V14 Configuration | yes | Secrets via `wrangler secret put`; `wrangler.jsonc` carries no secrets; `.dev.vars` in `.gitignore` already from Phase 1. |

### Known Threat Patterns for Cloudflare Worker + D1 + JWKS Directory

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Replay of a captured registration submit (with signature) | Spoofing | Nonce challenge expires in 5 min; nonce burned after successful registration (DELETE on success). |
| Spam registration to inflate `agents` rows beyond storage cap | DoS | Per-IP rate limit (10/day, D-40 + D-48). 5GB / row size = ~10M rows = needs 2700 days at 10/IP/day per IP. Storage attack is structurally hard. |
| Impersonation of major bot ("ChatGPT bot" registration) | Spoofing | Reserved-name blocklist (D-43). |
| Unauthorized JWKS overwrite (taking over an existing kid) | Tampering | The kid IS the public-key thumbprint — to overwrite, attacker needs the corresponding private key. Cryptographically prevented. |
| Directory-key compromise (worker secret leak) | Spoofing of directory itself | Secret rotation via `wrangler secret put DIRECTORY_PRIVATE_JWK` + publish new directory kid. Procedure documented per D-56. |
| Cache poisoning of `/.well-known/.../{kid}` | Tampering | Response is signed (Signature header); CDN can cache the bytes but verifiers re-verify the signature. CDN cache cannot forge a signature. |
| D1 SQL injection via blob columns | Tampering | All values passed via `.bind(...)`. Never string-concatenate into SQL. |
| Verbose error leakage (stack trace exposing impl details) | Information disclosure | Catch-all `app.onError` returns generic `{error:"internal"}` 500; detailed errors only in `wrangler tail` (operator-only). |
| Free-tier exhaustion DoS (100k req/day saturated) | DoS | At 100k cap, Worker returns 429 — read endpoints fail open with cached CDN responses for 5 min. Acceptable per D-47. |
| Worker time-window collision in rate-limit (race between two requests in same ms) | Spoofing | D1 `.batch([...])` with INSERT-ON-CONFLICT-UPDATE makes the count increment atomic. SELECT after UPDATE returns the post-increment value. |

### Specific Security Tasks for Phase 3 Plans

The planner should ensure the plan includes:
1. **Secret-rotation runbook in `directory/README.md`** (D-56) — how to generate a new JWK, `wrangler secret put`, and trigger the directory's own kid republication.
2. **`onError` global handler** that returns generic 500 with no stack details.
3. **Test for blocklist false-positives** ("googlestyle-app" should NOT be blocked per D-43).
4. **Test that nonce burn happens BEFORE the response is returned** (regression guard against replay).
5. **Wrangler observability enabled** (`observability: { enabled: true }` in `wrangler.jsonc`) — gives free request-level logs without enabling paid features.

## §1 — TypeScript Framework + Dependency Choice (output schema mapping)

**Recommendation:** Hono 4.12.16. Rationale and alternatives consolidated in `## Standard Stack` and `## Architecture Patterns` Pattern 1.

## §2 — Wrangler Config + D1 Schema (output schema mapping)

Concrete files in `## Code Examples` Examples 1 + 2. Migration strategy: wrangler-managed under `directory/migrations/` per D-55 resolution.

## §3 — Worker Code Structure (output schema mapping)

Project layout in `## Architecture Patterns` "Recommended Project Structure". Handler samples in Examples 3, 4, 5, 6, 7. Key modules: `routes/register.ts`, `routes/read.ts`, `blocklist.ts`, `ratelimit.ts`, `signing.ts`, `env.ts`, `schemas.ts`, `index.ts`.

## §4 — web-bot-auth 0.1.3 Verifier Integration (output schema mapping)

Pattern 2 + Example 4 + Example 5. Key API surface (verified via Context7 `/cloudflare/web-bot-auth`):

```typescript
import { verify, signatureHeaders } from "web-bot-auth";
import { signerFromJWK, verifierFromJWK } from "web-bot-auth/crypto";
import { directoryResponseHeaders } from "web-bot-auth/http-message-sig"; // re-exported subpath

// Verify incoming registration submit
const verifier = await verifierFromJWK(submittedJWK);
await verify(c.req.raw, verifier); // throws on failure with descriptive message

// Sign directory response
const signer = await signerFromJWK(directoryJWK);
const headers = await directoryResponseHeaders(
  { request: {method,url,headers}, response: {status,headers} },
  [signer],
  { created, expires }
);
```

Async fetch+verify pattern: the typical flow is **(a)** read the incoming `Request` from Hono's `c.req.raw`, **(b)** identify the kid from the body, **(c)** load the verifier from the submitted JWK (NOT from D1 — for registration, the submitted body IS the source of truth), **(d)** call `await verify(req, verifier)` inside a try/catch, **(e)** on success, persist; on failure, return 401 with the error message.

## §5 — GitHub Action Snapshot Workflow (output schema mapping)

Per Open Question #3, ship the script and a workflow file with cron disabled. Concrete workflow:

```yaml
# .github/workflows/snapshot.yml
# Phase 3 ships this DISABLED (cron commented out).
# Phase 5 enables when D-08 (GitHub org/account choice) resolves.
name: nightly-directory-snapshot

on:
  workflow_dispatch: {}
  # schedule:
  #   - cron: '0 2 * * *'   # 02:00 UTC daily — ENABLE IN PHASE 5

jobs:
  snapshot:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - name: Fetch directory snapshot
        run: |
          mkdir -p ./snapshot-build/snapshots
          DATE=$(date -u +%Y-%m-%d)
          curl -fsSL "https://wbauth.silov801.workers.dev/static/all.json" \
            -o "./snapshot-build/snapshots/directory-snapshot-${DATE}.json"
          cp "./snapshot-build/snapshots/directory-snapshot-${DATE}.json" \
            "./snapshot-build/snapshots/latest.json"
      - name: Prune snapshots older than 30 days
        run: |
          find ./snapshot-build/snapshots -name 'directory-snapshot-*.json' -mtime +30 -delete || true
      - name: Deploy to gh-pages
        uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./snapshot-build
          publish_branch: gh-pages
          keep_files: true   # don't blow away other gh-pages content
```

Auth pattern: `secrets.GITHUB_TOKEN` (built-in, no PAT needed) per `peaceiris/actions-gh-pages@v4` README pattern. Resolves D-45's "PAT vs GITHUB_TOKEN" question.

## §6 — Python `wbauth register` CLI Implementation Reference (output schema mapping)

```python
# python/src/wbauth/cli.py — extension to existing argparse tree
# Source: synthesized from existing cli.py patterns + D-49

def _build_register_parser(sub):
    reg = sub.add_parser(
        "register",
        help="Register an Identity with the hosted directory.",
        description=(
            "Two-step proof-of-key-ownership flow. (1) POST /register/challenge → "
            "receive nonce. (2) sign + POST /register/submit. Exits 0 on success."
        ),
    )
    reg.add_argument("--identity", required=True, help="Path to private key PEM.")
    reg.add_argument(
        "--directory",
        default="https://wbauth.silov801.workers.dev",
        help="Directory base URL.",
    )
    reg.add_argument("--client-name", default=None, help="Public agent name.")
    reg.add_argument("--purpose", default=None, help="Why this agent exists.")
    reg.add_argument("--client-uri", default=None, help="Public homepage URL.")
    reg.add_argument(
        "--expected-user-agent", default=None,
        help="The User-Agent string verifiers should expect from this agent."
    )
    return reg

async def _do_register(
    *, identity_path: str, directory_url: str, client_name: str, purpose: str | None,
    client_uri: str | None, expected_user_agent: str | None,
) -> dict:
    """Two-step proof-of-key-ownership flow per D-38."""
    import httpx
    from .identity import Identity
    from .normalized_request import NormalizedRequest
    from .signer import sign

    # Use a placeholder signature_agent_url just to construct Identity;
    # the directory will return the canonical URL after registration.
    identity = Identity.load_or_generate(
        identity_path,
        signature_agent_url=f"{directory_url}/.well-known/http-message-signatures-directory/_temp",
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Step 1: challenge
        r1 = await client.post(
            f"{directory_url}/register/challenge",
            json={"kid": identity.kid},
        )
        r1.raise_for_status()
        challenge = r1.json()["challenge"]

        # Step 2: build signed submit
        canonical_signature_agent = (
            f"{directory_url}/.well-known/http-message-signatures-directory/{identity.kid}"
        )
        # Re-construct Identity with the canonical URL so the signature commits to it.
        identity_canonical = Identity.load_or_generate(
            identity_path, signature_agent_url=canonical_signature_agent,
        )

        body = {
            "kid": identity_canonical.kid,
            "challenge": challenge,
            "client_name": client_name,
            "client_uri": client_uri,
            "signature_agent_url": canonical_signature_agent,
            "expected_user_agent": expected_user_agent,
            "contacts": [],
            "purpose": purpose,
            "keys": identity_canonical.export_jwks(),
        }
        body_bytes = json.dumps(body).encode("utf-8")

        # Sign the POST itself — Web Bot Auth headers cover @authority + signature-agent
        submit_url = f"{directory_url}/register/submit"
        req = NormalizedRequest(method="POST", url=submit_url, headers={})
        sig = sign(req, identity_canonical, created=datetime.datetime.now(datetime.timezone.utc))

        r2 = await client.post(
            submit_url,
            content=body_bytes,
            headers={
                "content-type": "application/json",
                "Signature": sig.signature,
                "Signature-Input": sig.signature_input,
                "Signature-Agent": sig.signature_agent,
            },
        )
        r2.raise_for_status()
        return r2.json()


def _dispatch_register(args) -> int:
    try:
        result = asyncio.run(_do_register(
            identity_path=args.identity,
            directory_url=args.directory,
            client_name=args.client_name or input("client_name: ").strip(),
            purpose=args.purpose,
            client_uri=args.client_uri,
            expected_user_agent=args.expected_user_agent,
        ))
    except httpx.HTTPStatusError as e:
        print(f"error: registration rejected: HTTP {e.response.status_code} {e.response.text}",
              file=sys.stderr)
        return 1
    except Exception as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(f"Registered. directory_url: {result['directory_url']}")
    return 0
```

## §7 — Python `wbauth serve` Minimal JWKS Server Reference (output schema mapping)

```python
# python/src/wbauth/_http_server/jwks_server.py
# Per D-50 — ~30 LOC stdlib http.server static JWKS host
"""Tiny static JWKS server for self-hosters.

Serves a single JWKS file at /.well-known/http-message-signatures-directory/{kid}
with Content-Type per draft-meunier-http-message-signatures-directory-05.
"""
from __future__ import annotations
import http.server
import json
import re
from pathlib import Path

CONTENT_TYPE = "application/http-message-signatures-directory+json"
PATH_RE = re.compile(r"^/\.well-known/http-message-signatures-directory/([^/]+)$")


def make_handler(jwks_path: Path):
    jwks_bytes = jwks_path.read_bytes()
    jwks = json.loads(jwks_bytes)
    served_kids = {k["kid"] for k in jwks.get("keys", [])}

    class JWKSHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            m = PATH_RE.match(self.path)
            if not m or m.group(1) not in served_kids:
                self.send_error(404, "kid not served by this JWKS")
                return
            self.send_response(200)
            self.send_header("content-type", CONTENT_TYPE)
            self.send_header("content-length", str(len(jwks_bytes)))
            self.send_header("cache-control", "public, max-age=300")
            self.end_headers()
            self.wfile.write(jwks_bytes)

        def log_message(self, format, *args):
            pass  # quiet stdlib request log

    return JWKSHandler


def serve(jwks_path: str | Path, port: int = 8080) -> None:
    handler = make_handler(Path(jwks_path))
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), handler)
    print(f"Serving JWKS from {jwks_path} on port {port}")
    server.serve_forever()
```

```python
# python/src/wbauth/cli.py — `serve` subparser snippet
def _build_serve_parser(sub):
    sv = sub.add_parser(
        "serve", help="Serve a single JWKS file at the well-known path.",
        description="Stdlib http.server-based static JWKS host. NO registration, NO list endpoints.",
    )
    sv.add_argument("--jwks", required=True, help="Path to the JWKS JSON file.")
    sv.add_argument("--port", type=int, default=8080, help="TCP port (default: 8080).")
    return sv


def _dispatch_serve(args) -> int:
    from ._http_server.jwks_server import serve
    try:
        serve(args.jwks, args.port)
    except KeyboardInterrupt:
        return 130
    return 0
```

The `wbauth keygen --jwks-output <path>` extension (D-51):

```python
# python/src/wbauth/cli.py — keygen handler extension
# Add to existing kg parser:
kg.add_argument(
    "--jwks-output", default=None,
    help="If set, also write the public JWKS document to this path."
)

# In _dispatch_keygen, after Identity construction:
if args.jwks_output:
    Path(args.jwks_output).write_text(json.dumps(identity.export_jwks(), indent=2))
    print(f"Wrote JWKS to {args.jwks_output}")
```

## §8 — E2E Manual-Test Script (output schema mapping)

```python
# python/scripts/e2e_phase3.py
# Per D-52 — manual run, NOT CI. Run before tagging Phase 3 complete.
"""Phase 3 exit-criterion gate.

Generates a fresh identity, registers with the live Worker, fetches the JWKS,
asserts signature, signs a probe request via wbauth.sign(), POSTs to Cloudflare
research verifier, asserts success banner.

Usage:
    cd python
    uv run python ../scripts/e2e_phase3.py [--directory https://wbauth.silov801.workers.dev]
"""
from __future__ import annotations
import argparse
import asyncio
import datetime
import json
import sys
import tempfile
from pathlib import Path

import httpx

from wbauth import Identity, NormalizedRequest, sign

CF_VERIFIER = "https://http-message-signatures-example.research.cloudflare.com/"
SUCCESS_BANNER = "You successfully authenticated as owning the test public key"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default="https://wbauth.silov801.workers.dev")
    args = parser.parse_args()

    # Step 1 — fresh identity in tmp
    with tempfile.TemporaryDirectory() as td:
        keypath = Path(td) / "key.pem"
        canonical_url = f"{args.directory}/.well-known/http-message-signatures-directory/_temp"
        identity = Identity.load_or_generate(keypath, signature_agent_url=canonical_url)
        kid = identity.kid
        print(f"[1/5] Generated kid: {kid}")

        # Step 2 — register
        from wbauth.cli import _do_register
        result = await _do_register(
            identity_path=str(keypath),
            directory_url=args.directory,
            client_name=f"wbauth-e2e-{kid[:8]}",
            purpose="Phase 3 E2E exit-criterion test",
            client_uri=None,
            expected_user_agent=None,
        )
        print(f"[2/5] Registered: directory_url={result['directory_url']}")

        # Step 3 — fetch and validate JWKS
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(result["directory_url"])
            r.raise_for_status()
            assert "Signature" in r.headers, "Missing Signature header on JWKS response"
            jwks = r.json()
            assert any(k["kid"] == kid for k in jwks["keys"]), "kid not in fetched JWKS"
            print(f"[3/5] JWKS fetched and signed (Signature header present)")

        # Step 4 — sign a probe with the registered URL
        identity_signed = Identity.load_or_generate(
            keypath, signature_agent_url=result["directory_url"]
        )
        req = NormalizedRequest(method="GET", url=CF_VERIFIER, headers={})
        sig = sign(req, identity_signed, created=datetime.datetime.now(datetime.timezone.utc))

        # Step 5 — POST (well, GET) to Cloudflare research verifier
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(
                CF_VERIFIER,
                headers={
                    "Signature": sig.signature,
                    "Signature-Input": sig.signature_input,
                    "Signature-Agent": sig.signature_agent,
                },
            )
        if r.status_code == 200 and SUCCESS_BANNER in r.text:
            print("[5/5] Cloudflare research verifier: PASS (success banner present)")
            return 0
        print(f"[5/5] FAIL: status={r.status_code}, banner missing", file=sys.stderr)
        print(r.text[:500], file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

NOTE: This script reuses the verifier from registration (your own kid). Cloudflare's research verifier accepts the RFC 9421 test key per Phase 1 plan 04 finding — since v1 only validates the test key, the E2E above will fail at Step 5 unless the research verifier is upgraded to consult the Signature-Agent header's JWKS URL (which it does, per the spec). **[FLAG TO PLANNER:** Confirm by manual test on the live verifier before committing to this E2E script — Phase 1's plan 04 SUMMARY noted the research verifier validates the publicly-known test key; Cloudflare's docs imply the directory-aware path works for any registered kid, but Phase 1 didn't exercise that path. If the verifier rejects, fall back to: register with the test key (set Identity.from_test_key), and the E2E proves the register→fetch→sign→verify chain even though it's the test kid. **]**

## Sources

### Primary (HIGH confidence)
- Context7 `/websites/hono_dev` — Hono Cloudflare Workers + D1 + getConnInfo + validation docs
- Context7 `/websites/developers_cloudflare_workers` — Workers limits, D1 migrations, secrets, Web Crypto, vitest-pool-workers
- Context7 `/cloudflare/web-bot-auth` — `signatureHeaders`, `verify`, `signerFromJWK`, `verifierFromJWK`, `directoryResponseHeaders` API surface and code examples
- npm registry (`npm view`) — verified versions: hono 4.12.16, web-bot-auth 0.1.3, wrangler 4.87.0, zod 4.4.3, @cloudflare/workers-types 4.20260504.1, @hono/standard-validator 0.2.2, @cloudflare/vitest-pool-workers 0.15.2 — all checked 2026-05-03
- IETF draft-meunier-http-message-signatures-directory-05 (via WebFetch) — wire format, content-type, signing tag

### Secondary (MEDIUM confidence)
- developers.cloudflare.com/workers/runtime-apis/web-crypto (via WebFetch) — Ed25519 import format question (not fully resolved; see Open Question #2)
- developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/ (via WebFetch) — confirms no tier statement in docs (justifies the D1 strategy)
- developers.cloudflare.com/workers/platform/pricing/ — D1 free tier limits (5M reads, 100k writes, 5GB)

### Tertiary (LOW confidence — flagged for validation)
- community.cloudflare.com posts about PKCS8 import on Workers — anecdotal, sidestepped via JWK route
- A1 (web-bot-auth signing on Workers) — assumed to work based on the lib's documented Workers examples; not empirically verified for the directory-server signing path

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every library version verified via npm registry; Hono + web-bot-auth APIs verified via Context7
- Architecture: HIGH — patterns are direct synthesis of CONTEXT.md decisions + cited library APIs
- Pitfalls: MEDIUM-HIGH — 3 verified from official docs (CPU limits, secrets management, structured fields), 4 derived from D1 + free-tier mechanics (cleanup-on-write, immutable cache, ratelimit accumulation, snapshot timing)
- Open questions: 5 surfaced explicitly so planner/discuss can resolve before execution

**Research date:** 2026-05-03
**Valid until:** 2026-06-03 (30 days for Cloudflare/Hono — stable; web-bot-auth 0.1.3 was bumped 2 months ago so still recent)
