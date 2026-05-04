# Phase 3: Hosted Directory & Cloudflare Submission - Context

**Gathered:** 2026-05-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 stands up the public agent identity directory at `https://wbauth.silov801.workers.dev` — a TypeScript Cloudflare Worker backed by D1 SQLite — with proof-of-key-ownership registration, signed JWKS serving per draft-meunier-http-message-signatures-directory-05, and a nightly GitHub Pages snapshot mirror as disaster recovery. End-to-end flow: an agent registers via `wbauth register`, gets a stable kid-addressable URL, signs a request via `wbauth sign()`, the Cloudflare research verifier accepts using the registered directory URL.

Plus: a minimal `wbauth serve` CLI command that runs a 30-LOC Python static-file server for users who want to self-host a single JWKS file without depending on `wbauth.silov801.workers.dev`.

**SCOPE CHANGE: DIST-08 (Cloudflare verified-bot submission) is moved from Phase 3 to Phase 5 (Pre-Army Hardening).** Cloudflare requires a public source repo for submission review; D-08 (GitHub org/account) was deferred to be resolved at `git remote add` time. Submitting without a public repo would be rejected by Cloudflare's review process. The submission becomes part of the "push to GitHub + file submission + register reference bot" hardening sequence.

Covers v1 requirements: DIR-01, DIR-02, DIR-03, DIR-04, DIR-05, DIR-07, DIR-08, CLI-04, CLI-05.
DIST-08 deferred to Phase 5.

</domain>

<decisions>
## Implementation Decisions

### Carrying Forward (Locked in Earlier Phases)
- **L-01 → L-12: All Phase 1 + Phase 2 carry-forwards apply.** Most relevant for Phase 3:
  - Package name `wbauth` (Phase 1 D-05)
  - Zero-billing architecture, Cloudflare Workers + D1 (Phase 1 D-01, D-02)
  - No custom domain in v1 — use `*.workers.dev` URL (Phase 1 D-03)
  - Identity API: `Identity.load_or_generate(path, signature_agent_url=...)` (Phase 1 D-09)
  - Signer is `wbauth.sign()` pure function (Phase 1 D-09 + verification)
  - Cloudflare research verifier (`http-message-signatures-example.research.cloudflare.com`) is the conformance oracle; crawltest.com is Phase 5 (post-submission, post-Cloudflare-approval)

### Phase 3 Implementation Decisions

#### Production Worker
- **D-33: Production Worker URL = `https://wbauth.silov801.workers.dev`.** Short, brand-aligned, easy to remember. Created as a NEW Worker (not a rename of `wbauth-day1-test`). The day1-test Worker stays as historical artifact (no deletion in this phase — clean up later if desired).
- **D-34: D1 database = `wbauth-directory` (new).** Separate from `wbauth-day1-test` D1 (the Phase 1 hello-world test bed). Single-table schema (per RESEARCH.md guidance — directory is read-heavy, write-rare).
- **D-35: Worker codebase replaces existing `directory/` workspace contents.** The throwaway hello-world `src/index.ts` from Phase 1 is overwritten with the production directory router. This was the planner's intent in Phase 1 — `directory/` workspace is reused, not duplicated.

#### Schema (D1)
- **D-36: Single `agents` table.** Columns: `kid TEXT PRIMARY KEY`, `client_name TEXT NOT NULL`, `client_uri TEXT`, `signature_agent_url TEXT NOT NULL`, `expected_user_agent TEXT`, `contacts TEXT` (JSON array), `purpose TEXT`, `targeted_content TEXT`, `rate_control TEXT`, `keys TEXT NOT NULL` (JWKS JSON blob), `created_at INTEGER NOT NULL`, `last_updated INTEGER NOT NULL`. Multi-key support (key rotation) lives inside the JWKS JSON blob — no separate `keys` table. Simpler queries, atomic writes.
- **D-37: No user accounts table.** Identity == kid. Proof-of-key-ownership replaces auth. Re-registration with the same kid requires signing a fresh nonce (overwrite atomically).

#### Registration Flow (DIR-02)
- **D-38: Two-step proof-of-key-ownership.**
  1. Client → `POST /register/challenge` with `{"kid": "..."}` → server returns `{"challenge": "<random-128-bit-nonce>", "expires_at": <ts+300>}`.
  2. Client signs `{"action": "register", "kid": "...", "challenge": "..."}` payload via Web Bot Auth signer using the kid's private key, POSTs to `/register/submit` with the full Signature Agent Card body + the signature headers. Server verifies signature via the same RFC 9421 verification path the SDK exports, then INSERTs/UPDATEs the row.
- **D-39: No email, no OAuth, no CAPTCHA.** Per CONTEXT.md from Phase 2: "no third-party identity provider".
- **D-40: Per-IP rate limit on `/register/*`.** 10 register attempts per IP per day (Cloudflare KV-backed counter or D1 row with TTL). Doesn't apply to read endpoints.

#### Read API (DIR-03)
- **D-41: Read endpoints.**
  - `GET /.well-known/http-message-signatures-directory/{kid}` — JWKS for a single kid; content-type `application/http-message-signatures-directory+json`; signed (response carries `Signature` + `Signature-Input`); CDN-cached `Cache-Control: public, max-age=300, immutable`.
  - `GET /agents/{kid}` — full Signature Agent Card (all fields), JSON; `Cache-Control: public, max-age=60`.
  - `GET /agents` — paginated list (50 per page), `?page=N`; for browsing/discovery; `Cache-Control: public, max-age=300`.
  - `GET /static/all.json` — full directory snapshot (snapshot job writes; no DB hit on read); CDN immutable.
- **D-42: Directory response signing.** Worker holds its own Ed25519 keypair (stored as Cloudflare Worker secret via `wrangler secret put DIRECTORY_PRIVATE_KEY`). `kid` for the directory's own key is published at the root of `/.well-known/http-message-signatures-directory/` so verifiers can trust the directory's signed responses.

#### Reserved-Name Blocklist (DIR-04)
- **D-43: Block `client_name` registration matching exact (case-insensitive) any of:** `google`, `openai`, `anthropic`, `cloudflare`, `microsoft`, `meta`, `apple`, `amazon`, `aws`, `github`, `stripe`, `shopify`. Also block any `client_name` containing those tokens as substrings IF combined with `bot`/`agent`/`crawler` (e.g., `google-bot` blocked, `googlestyle-app` allowed). Implementation: small TypeScript regex array. List is in `directory/src/blocklist.ts` for easy update.
- **D-44: Blocklist enforcement message.** Reject with HTTP 422 + JSON body `{"error": "reserved_name", "blocked_token": "google", "guidance": "If you represent this organization and want this name on agentpassport, contact <maintainer email TBD in Phase 5>"}`. Honest signal so well-meaning third parties don't burn cycles.

#### Snapshot & Disaster Recovery (DIR-05)
- **D-45: Nightly GitHub Action job at 02:00 UTC** queries `GET /agents?all=true` against the live Worker, writes a single `directory-snapshot.json` to a separate `snapshots/` directory in the repo's `gh-pages` branch (or a dedicated `wbauth-snapshots` repo). Script lives at `.github/workflows/snapshot.yml` + `scripts/snapshot.sh`. If the Worker is down for >24h, agents can fetch the most recent snapshot from `https://<github-org>.github.io/wbauth-snapshots/directory-snapshot.json`. Snapshot URL is documented in README.
- **D-46: Snapshot retention.** Last 30 days as separate dated files (`directory-snapshot-2026-05-04.json`); plus a `latest` symlink/copy. Keeps history small (each snapshot likely <100 KB at this scale).

#### Spend Caps & Abuse (DIR-07)
- **D-47: Cloudflare Workers Free tier limits.** 100k requests/day, 10ms CPU per invocation. D1: 5M reads/day, 100k writes/day, 5GB storage. Free tier is hard-capped — no spend possible. We do NOT enable Workers Paid in v1. If we exceed limits, the Worker returns 429 — acceptable for v1 (load is expected to be tiny).
- **D-48: Per-IP rate limit on registration enforced via D1 small-row strategy.** 10 attempts per IP per day. Cloudflare's built-in IP rate limiting is paid-only; D1 is free. Use D1 row with INSERT IGNORE + count check + cleanup-on-write of expired rows.

#### CLI (`wbauth register`, `wbauth serve`)
- **D-49: `wbauth register --identity <key.pem> [--directory <url>]`** — defaults `--directory https://wbauth.silov801.workers.dev`. Prompts user for `client_name` and `purpose` (or accepts `--client-name`/`--purpose` args). Runs the two-step proof-of-key-ownership flow. Exit 0 on success, 1 on rejection with reason printed to stderr.
- **D-50: `wbauth serve [--port 8080] --jwks <path>`** — minimal Python http.server-based static JWKS server. ~30 LOC. Serves a single JWKS file at `/.well-known/http-message-signatures-directory/{kid}` with the correct content-type. Designed for users who want to self-host a single agent's JWKS without depending on the hosted directory. Does NOT replicate the full directory backend (no registration, no list endpoints — that's what the hosted directory is for).
- **D-51: Self-hosters generate the JWKS file via** `wbauth keygen --jwks-output <path>` (extend the existing `keygen` subcommand with a `--jwks-output` flag in this phase). The JWKS file is then served by `wbauth serve`.

#### End-to-End Validation (DIR-08)
- **D-52: Phase 3 exit criterion is a live E2E flow.** Generate identity locally → `wbauth register` to live Worker → confirm `GET /.well-known/http-message-signatures-directory/{kid}` returns the JWKS with valid signature → sign a probe request via `wbauth.sign()` with the registered directory URL → POST to Cloudflare research verifier → verifier responds 200 OK. This is captured in a CI test (manual run, not auto — running it on every CI push would spam our own directory with test registrations).

#### DIST-08 Movement
- **D-53: DIST-08 (Cloudflare verified-bot submission) moves from Phase 3 to Phase 5.** Cloudflare's submission review requires a public GitHub repo URL; D-08 (GitHub org/account decision) was deferred to be resolved at `git remote add`. Phase 5 (Pre-Army Hardening) will: (a) resolve D-08, (b) push to GitHub, (c) file Cloudflare submission with the public repo + workers.dev URL + register reference bot via the directory we just built. This bundles all "go-public" actions in one phase. Phase 3 builds the directory; Phase 5 makes it discoverable.

### Claude's Discretion
- D-54: Exact TypeScript framework choice (Hono vs raw fetch handler vs itty-router). Planner picks based on size + maintenance — leaning Hono for ergonomics, raw fetch handler for absolute minimum surface.
- D-55: D1 migrations strategy (wrangler-managed vs raw SQL files). Pick simpler.
- D-56: Worker secret rotation procedure documentation (in directory README — explain how to rotate `DIRECTORY_PRIVATE_KEY` if compromised).
- D-57: Internal TypeScript module organization beyond what's named in D-36 schema and D-41 endpoints.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project & Requirements
- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md` — DIR-01..05,07,08 + CLI-04,05 + DIST-08 (the latter moved to Phase 5 per D-53)
- `.planning/ROADMAP.md` — Phase 3 boundaries (NOTE: planner should update Phase 3 plan list to remove DIST-08 from Phase 3 and add to Phase 5)

### Prior Phases
- `.planning/phases/01-foundation-cryptographic-root/01-CONTEXT.md` — D-01..D-11 (zero-billing, wbauth name, TypeScript-on-Workers directory, npm workspaces)
- `.planning/phases/01-foundation-cryptographic-root/01-VERIFICATION.md` — Phase 1 audit
- `.planning/phases/01-foundation-cryptographic-root/01-01-SUMMARY.md` — Day-1 hosting outcome (existing `directory/` workspace, wrangler.jsonc shape, D1 binding pattern, account ID + email)
- `.planning/phases/02-python-adapters-policy-inspector/02-CONTEXT.md` — Phase 2 carry-forwards
- `.planning/phases/02-python-adapters-policy-inspector/02-VERIFICATION.md` — Phase 2 audit (17/17 PASS)

### Existing Code (read these before extending)
- `directory/wrangler.jsonc` — current worker config (Phase 1 day1-test setup)
- `directory/src/index.ts` — throwaway hello-world handler (Phase 3 replaces)
- `directory/schema.sql` — Phase 1 hello D1 schema (Phase 3 replaces with full agents table)
- `directory/package.json` — current TS deps
- `python/src/wbauth/cli.py` — current CLI (Phase 3 extends with `register` and `serve` subcommands)
- `python/src/wbauth/identity.py` — Identity object (Phase 3 needs JWKS export, already in Phase 1)
- `python/src/wbauth/signer.py` — sign() function (Phase 3 register CLI uses this)
- `python/src/wbauth/_smoke/cloudflare_debug.py` — Cloudflare verifier probe pattern (Phase 3 E2E validation reuses this)

### External Specs
- IETF draft-meunier-http-message-signatures-directory-05 — JWKS directory format MUST be followed for D-41
- IETF draft-meunier-webbotauth-registry-01 — Signature Agent Card schema for D-36 columns
- IETF RFC 9421 — signed directory responses per D-42
- Cloudflare Workers docs — Workers + D1 + secrets + free tier limits
- Cloudflare verified-bot submission policy — for Phase 5 DIST-08 (background context for understanding why we defer)

### Library Docs
- Hono (TypeScript Cloudflare Workers framework) — most likely framework choice
- `@cloudflare/workers-types` — typing for Worker bindings
- D1 client API
- Cloudflare's `web-bot-auth` 0.1.3 npm — TS verifier reference (Phase 3's directory verifies signatures during registration; same library Phase 4 uses)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `directory/wrangler.jsonc` already configured with D1 binding pattern from Phase 1 (see `01-01-SUMMARY.md`).
- Cloudflare account `silov801@gmail.com` (Account ID 2a1e5d83dbc5d553a3537d7a79009899) confirmed working with free tier.
- `npx wrangler` CLI confirmed working from project root (Phase 1 Plan 01-01 verified).
- `wbauth.sign()` and `wbauth.verifier` (from Plan 01-03) are the reusable cryptographic primitives — registration verifier reuses the same Python verification code path against signed challenges. TypeScript verifier in the Worker uses Cloudflare's `web-bot-auth` 0.1.3 npm package (already a dep from Phase 1 test vector cross-language conformance).
- Test vector format from Phase 1 — useful for unit-testing the directory's signing logic.

### Established Patterns
- TDD cycle (RED → GREEN → REFACTOR) per task — apply to TypeScript Worker code via vitest.
- Atomic commits per task.
- npm workspaces — `directory/` workspace already in `pnpm-workspace.yaml` equivalent (root `package.json`).
- macOS workaround: `bash scripts/post-sync.sh` after `uv sync` (and now also `chflags nohidden` on .pth files — see Phase 2 verification note).

### Integration Points
- Phase 4 (TypeScript SDK) consumes the directory by reading JWKS via the SDK's `inspect()` policy fetcher. Directory must be live by end of Phase 3.
- Phase 5 (Hardening + DIST-08) consumes the directory to: (a) register the reference demo bot, (b) submit to Cloudflare's verified-bot directory.
- Python `wbauth register` CLI (D-49) consumes the directory via HTTPS — uses httpx (already a dep from Phase 2) for the registration POST.

</code_context>

<specifics>
## Specific Ideas

- **Branding**: production directory URL `https://wbauth.silov801.workers.dev`. Display in CLI register output and README hero. Day1-test stays — historical artifact.
- **Directory's own kid**: published at the root path `/.well-known/http-message-signatures-directory/` (no trailing kid) so external verifiers can discover the directory's signing identity.
- **README hero example for the directory**: `curl https://wbauth.silov801.workers.dev/.well-known/http-message-signatures-directory/<your-kid>` returns JWKS with HTTP signature.

</specifics>

<deferred>
## Deferred Ideas

- **Custom domain `wbauth.dev` / `wbauth.io`** — post-army (Phase 1 D-03 carries forward).
- **`wbauth serve` as full directory backend** (not just JWKS server) — v1.x if multi-process self-hosting demand surfaces. Original plan was Python FastAPI; with the TS+Workers shift, full self-hosting requires Node + wrangler — unjustified complexity for v1.
- **Web UI / browse experience for the directory** — REQUIREMENTS.md `DIR-UI-01`, post-army.
- **Real-time directory mirroring / multi-region replication** — REQUIREMENTS.md `DIR-MIRROR-01`, post-army.
- **Site-side verification SDK** — REQUIREMENTS.md `SITE-VERIFY-01`, v2.
- **DIST-08 (Cloudflare verified-bot submission)** — moved to Phase 5 per D-53. Not "deferred" — actively scheduled, just in the right phase.

</deferred>

---

*Phase: 3-Hosted Directory & Cloudflare Submission*
*Context gathered: 2026-05-04*
