# Requirements: Agent Identity & Policy Toolkit

**Defined:** 2026-05-03
**Core Value:** AI-агенты получают идентичность и знают свои права на сайте — до того, как сделают первый запрос. Если ничего другое не работает, эти две вещи (signed identity + pre-flight policy) должны работать в одну строку импорта.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Identity & Signing

- [ ] **IDENT-01**: Developer can generate Ed25519 keypair via Python API and CLI (`agentid keygen`); private key written with `0o600` permissions; loading refuses files with wider permissions
- [ ] **IDENT-02**: Developer can construct a long-lived `Identity` object that holds keypair + agent metadata (signature-agent URI, expected user-agent string)
- [ ] **IDENT-03**: SDK signs an HTTP request via pure function `sign(NormalizedRequest, Identity) -> SignatureHeaders` producing valid RFC 9421 `Signature`, `Signature-Input`, and `Signature-Agent` headers with Web Bot Auth profile defaults (Ed25519, `tag="web-bot-auth"`, `expires = created + 60s`)
- [ ] **IDENT-04**: Generated signatures pass byte-equal verification against `spec/test-vectors/` golden files (cross-language oracle for Python and TS parity)
- [ ] **IDENT-05**: Generated signatures pass Cloudflare's debug verifier endpoint (`http-message-signatures-example.research.cloudflare.com/debug`) in CI smoke tests
- [ ] **IDENT-06**: SDK exports JWKS for the active keypair with `kid = base64url(sha256(JWK))` per RFC 7638
- [ ] **IDENT-07**: SDK supports key rotation lifecycle (multi-key Identity holds active + retiring key with overlap window); old key remains usable until explicit retirement
- [ ] **IDENT-08**: Identity object's `__repr__` and `__str__` return REDACTED instead of leaking private key material

### HTTP Client Adapters

- [ ] **ADAPT-01**: Python `httpx` adapter — `WebBotAuth(identity)` subclass of `httpx.Auth`; drop-in via `httpx.Client(auth=WebBotAuth(identity))`
- [ ] **ADAPT-02**: Python `requests` adapter — transport adapter usable via `session.mount(...)` or `auth=` parameter
- [ ] **ADAPT-03**: Python Playwright integration helper — `attach_signing(page, identity)` registers `page.route("**/*", handler)` that signs outgoing requests (NOT `set_extra_http_headers`, which is static)
- [ ] **ADAPT-04**: TypeScript `fetch` adapter — `createSignedFetch(identity)` returns a wrapped fetch with identical signature semantics
- [ ] **ADAPT-05**: TypeScript Playwright integration helper — `applyTo(page, identity)` mirroring Python behavior
- [ ] **ADAPT-06**: All adapters validated against shared `spec/test-vectors/` to guarantee byte-equality across languages and clients
- [ ] **ADAPT-07**: Each adapter file is ≤50 LOC of glue; complexity lives in the pure signer

### Pre-flight Policy Inspector

- [ ] **POLICY-01**: SDK exposes async `inspect(url) -> SitePolicy` that fans out parallel fetches to robots.txt, ai.txt, llms.txt, .well-known/http-message-signatures-directory, and returns one unified frozen dataclass
- [ ] **POLICY-02**: Per-endpoint timeout 3s; partial failures isolated (`return_exceptions=True`); `SitePolicy` exposes `partial: bool` and `errors: dict[str, Exception]`
- [ ] **POLICY-03**: robots.txt parsed via `protego` (RFC 9309 compliant); HTML 200 responses on `/robots.txt` raise explicit parse error rather than silently returning "allowed"
- [ ] **POLICY-04**: ai.txt v1.1.1 parser returns structured object with `[identity]`, `[permissions]`, `[restrictions]`, `[attribution]`, `[contact]`, `[content-types]` sections
- [ ] **POLICY-05**: llms.txt parser returns structured object; labeled with `enforcement: "voluntary"` so it is not sold as access control
- [ ] **POLICY-06**: SDK exposes `policy.verdict` returning `"allowed" | "restricted" | "forbidden"` with `reasons: list[str]` derived from rule engine (robots authoritative; ai.txt restriction → restricted; signing-required → restricted with mitigation hint)
- [ ] **POLICY-07**: Per-host LRU cache respects origin `Cache-Control`/`ETag` (defaults: robots.txt 24h, ai.txt 1h, llms.txt 24h); cache is in-process, no external dependency
- [ ] **POLICY-08**: `inspect(url)` works without any hosted directory or external service of ours; SDK has zero hard cloud dependencies

### Hosted Directory (agentpassport.dev)

- [ ] **DIR-01**: FastAPI backend exposes `POST /register` accepting Signature Agent Card (per draft-meunier-webbotauth-registry-01); fields are mostly optional with ≥1 required (`client_name`, `client_uri`, `contacts`, `expected-user-agent`, `keys`, etc.)
- [ ] **DIR-02**: Registration uses proof-of-key-ownership flow: server issues nonce, caller signs with claimed private key, server verifies via the same code path the SDK exports; no email, no OAuth, no third-party identity provider
- [ ] **DIR-03**: Backend serves `GET /.well-known/http-message-signatures-directory/{id}` returning JWKS with `Content-Type: application/http-message-signatures-directory+json`; the directory response itself is signed
- [ ] **DIR-04**: Read endpoints CDN-cached with `Cache-Control: immutable` on `/keys/<thumbprint>`; per-IP rate limiting on registration (10/day); reserved-name blocklist (google, openai, anthropic, cloudflare, microsoft, meta, apple, amazon)
- [ ] **DIR-05**: Snapshot job mirrors full directory to `/static/all.json` and to a GitHub Pages mirror nightly (disaster recovery — works even if backend is down)
- [ ] **DIR-06**: Hosting confirmed working with Russian payment card on day 1 (Fly.io primary; Railway fallback; Cloudflare Workers + D1 zero-billing fallback if both rejected); domain auto-renewal enabled for >18 months
- [ ] **DIR-07**: Hard spending caps configured on infrastructure ($20/month limit on directory hosting); abuse vectors (spam registrations, claimed-as-Google identity attempts) handled via blocklist + rate limit + manual review queue
- [ ] **DIR-08**: End-to-end flow validated: register identity → sign HTTP request via SDK → Cloudflare debug endpoint confirms verification passes using the registered directory URL

### Command Line Interface

- [ ] **CLI-01**: `agentid keygen [--output PATH]` generates Ed25519 keypair, writes private key with `0o600`, prints public JWK fingerprint
- [ ] **CLI-02**: `agentid inspect <url>` runs the policy inspector and prints structured `SitePolicy` (machine-readable JSON via `--json`; human-readable summary by default with verdict + reasons)
- [ ] **CLI-03**: `agentid verify --domain <domain>` runs Cloudflare's debug verifier against the user's identity and prints pass/fail per criterion (canonicalization, header presence, expiry window, signed components)
- [ ] **CLI-04**: `agentid register --directory <url> --identity <path>` publishes identity to the hosted directory using the proof-of-ownership flow
- [ ] **CLI-05**: `agentid serve [--port N]` runs a local self-hostable JWKS directory server (FastAPI) for users who don't want to depend on agentpassport.dev
- [ ] **CLI-06**: All CLI commands return non-zero exit codes on failure and emit machine-readable errors to stderr

### Distribution & Documentation

- [ ] **DIST-01**: Documentation site built with Astro Starlight on GitHub Pages (zero billing, builds reproducibly years later); contains: 60-second quickstart, API reference, "why this exists" narrative, FAQ
- [ ] **DIST-02**: README on GitHub: GIF demo at top, code-before-prose, time-to-understanding ≤30s; reviewed by native-English speaker before launch
- [ ] **DIST-03**: 60-second Loom demo: agent fails on Cloudflare-protected site → installs SDK → 3 lines added → request passes; embedded on landing and README
- [ ] **DIST-04**: Working integration recipe + tested example for **Browser Use** (`examples/browser_use_demo.py`)
- [ ] **DIST-05**: Working integration recipe + tested example for **Stagehand** (`examples/stagehand_demo.ts`)
- [ ] **DIST-06**: Working integration recipe + tested example for **Playwright + OpenAI Agents SDK** (`examples/openai_agents_demo.py`)
- [ ] **DIST-07**: Pull requests submitted to `examples/` directories of Browser Use, Stagehand, and mcp-agent adding our SDK
- [ ] **DIST-08**: Reference demo bot registered in agentpassport.dev directory AND submission filed to Cloudflare's verified-bot directory (filed on day 1 of Phase 4 due to opaque review timeline; approval by army leave is best-effort)

### Pre-Army Hardening

- [ ] **HARDEN-01**: All Python and TS dependencies have explicit upper bounds; `uv.lock` and `pnpm-lock.yaml` committed; PyPI publishing via OIDC trusted publishers (no token to rotate); npm publishing with provenance from GitHub Actions
- [ ] **HARDEN-02**: Dependabot configured (not Renovate — fewer PRs during absence); monthly scheduled CI canary verifies "still installs cleanly" + "Cloudflare verifier still accepts our signatures"
- [ ] **HARDEN-03**: `v1.x-frozen` git branch created with explicit 12-month compatibility promise documented in `MAINTAINER_AWAY.md` at repo root (includes expected return date and contact for moderators)
- [ ] **HARDEN-04**: Daily conformance canary (GitHub Action → Cloudflare debug → opens GitHub issue + Discord alert on failure) runs without manual intervention
- [ ] **HARDEN-05**: 2FA backup codes for GitHub, PyPI, npm, registrar printed and stored with trusted offline party; designated repo moderator(s) added with triage permissions
- [ ] **HARDEN-06**: Pinned status issue at top of repo explains maintainer absence and routes urgent security reports; CONTRIBUTING.md documents triage path during absence
- [ ] **HARDEN-07**: Domain auto-renewal verified to cover >18 months; DNS, TLS cert (Let's Encrypt auto-renew), CDN config all set to auto-mode with no manual touch points

## v2 Requirements

Deferred. Tracked but not in current roadmap.

### Differentiators (post-v1, pre-army if time)

- **D-AUTO-01**: Auto-detection — `policy.signing_required: bool` heuristic (Cloudflare 403 + Turnstile fingerprint + future `Accept-Signature` response header)
- **D-MCP-01**: MCP discovery — parse `.well-known/mcp` and `.well-known/mcp/server-card.json` per SEP-1960/1649; surface as `policy.mcp_endpoints`
- **D-A2A-01**: A2A AgentCard discovery — parse `/.well-known/agent-card.json` per A2A v0.3
- **D-OTEL-01**: OpenTelemetry hook — emit spans for every signed request and `inspect()` call (plays nicely with Laminar, AgentOps, OpenLLMetry)
- **D-RECEIPT-01**: Receipts — local SQLite log of signed evidence per `inspect()` result with timestamp + hash; optional cloud counter-signing
- **ADAPT-AIOHTTP-01**: `aiohttp` ClientSession middleware (trigger: 5+ users ask)
- **ADAPT-UNDICI-01**: TypeScript `undici` Dispatcher (trigger: Stagehand or Browser Use TS users specifically)

### Post-Army (v2+)

- **DIR-UI-01**: Web search/browse UI for the directory (`whois`-style)
- **DIR-MIRROR-01**: Real-time directory mirroring / multi-region replication
- **SITE-VERIFY-01**: Site-side verification SDK / origin-server middleware (chicken-and-egg, requires sales)
- **KMS-01**: KMS adapters (AWS KMS, GCP KMS, HashiCorp Vault) as separate packages
- **PAID-01**: Paid hosted-directory tier (post-army, post-relocation; depends on jurisdiction situation)
- **WEBMCP-01**: WebMCP integration (trigger: WebMCP exits Chrome flag, Firefox/Safari sign on)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Stealth / fingerprint spoofing / undetected-chromedriver patterns | Contradicts the "agents should be honest" thesis; ethical/legal risk; would taint Cloudflare partnership; Hyperbrowser owns this market |
| CAPTCHA solving (2Captcha-style) | We bypass interstitial bot challenges by signed identity, not by solving; CAPTCHA solving is a regulated commercial service we don't want to mediate |
| Vision-based browser automation | Browser Use, Stagehand, Skyvern own this; 12-24 month catch-up against funded incumbents |
| Observability / replay / session recording | Out of scope per PROJECT.md; Laminar (S24, $3M), AgentOps own this; requires continuous infra incompatible with army-leave constraint |
| Site-side verification SDK in v1 | Two-sided market; chicken-and-egg adoption; requires sales to non-developer site owners; deferred to v2 |
| Site-side MCP-converter (auto-emit MCP server from existing site) | FastMCP, Stainless, Speakeasy Gram, Klavis already attack this; requires non-developer sales |
| gRPC / WebSocket signing | Web Bot Auth is HTTP-only; spec doesn't cover non-HTTP; tiny audience would balloon code surface |
| Web UI / dashboard for directory in v1 | JSON API + CLI + static `whois`-style page sufficient; UI is multiplicative complexity |
| Paid tier in v1 | Adoption beats revenue at this stage; RU jurisdiction blocks Stripe; Apache 2.0 + free directory maximizes distribution |
| Built-in proxy/IP rotation | Combining positive identity (signed) with negative identity (rotating IPs) is incoherent |
| RSA / non-Ed25519 signature algorithms | Cloudflare emphasizes Ed25519; RSA keys are 6× larger and 30× slower; expanding algorithm support increases attack surface and test matrix |
| Automated policy enforcement (raise/halt agent on `forbidden` verdict) | Policy interpretation is a user decision; embedding enforcement creates liability and removes user control; we expose verdict, they enforce |
| Real-time directory mirroring / multi-region replication in v1 | Premature optimization; Web Bot Auth allows multiple directories per agent; HA users can self-host |
| Built-in browser-launcher / Playwright wrapper | Bundles two complex systems into one opinionated wrapper; Browser Use is already this wrapper; reduces drop-in compatibility |
| US C-Corp / Stripe payouts / VC fundraising in v1 | OFAC blocks RU-based incorporation; deferred until post-army relocation; project is reputation play |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| IDENT-01 | Phase 1 | Pending |
| IDENT-02 | Phase 1 | Pending |
| IDENT-03 | Phase 1 | Pending |
| IDENT-04 | Phase 1 | Pending |
| IDENT-05 | Phase 1 | Pending |
| IDENT-06 | Phase 1 | Pending |
| IDENT-07 | Phase 1 | Pending |
| IDENT-08 | Phase 1 | Pending |
| ADAPT-01 | Phase 2 | Pending |
| ADAPT-02 | Phase 2 | Pending |
| ADAPT-03 | Phase 2 | Pending |
| ADAPT-04 | Phase 4 | Pending |
| ADAPT-05 | Phase 4 | Pending |
| ADAPT-06 | Phase 2 | Pending |
| ADAPT-07 | Phase 2 | Pending |
| POLICY-01 | Phase 2 | Pending |
| POLICY-02 | Phase 2 | Pending |
| POLICY-03 | Phase 2 | Pending |
| POLICY-04 | Phase 2 | Pending |
| POLICY-05 | Phase 2 | Pending |
| POLICY-06 | Phase 2 | Pending |
| POLICY-07 | Phase 2 | Pending |
| POLICY-08 | Phase 2 | Pending |
| DIR-01 | Phase 3 | Pending |
| DIR-02 | Phase 3 | Pending |
| DIR-03 | Phase 3 | Pending |
| DIR-04 | Phase 3 | Pending |
| DIR-05 | Phase 3 | Pending |
| DIR-06 | Phase 1 | Pending |
| DIR-07 | Phase 3 | Pending |
| DIR-08 | Phase 3 | Pending |
| CLI-01 | Phase 2 | Pending |
| CLI-02 | Phase 2 | Pending |
| CLI-03 | Phase 2 | Pending |
| CLI-04 | Phase 3 | Pending |
| CLI-05 | Phase 3 | Pending |
| CLI-06 | Phase 2 | Pending |
| DIST-01 | Phase 5 | Pending |
| DIST-02 | Phase 5 | Pending |
| DIST-03 | Phase 5 | Pending |
| DIST-04 | Phase 4 | Pending |
| DIST-05 | Phase 4 | Pending |
| DIST-06 | Phase 4 | Pending |
| DIST-07 | Phase 4 | Pending |
| DIST-08 | Phase 3 | Pending |
| HARDEN-01 | Phase 5 | Pending |
| HARDEN-02 | Phase 5 | Pending |
| HARDEN-03 | Phase 5 | Pending |
| HARDEN-04 | Phase 5 | Pending |
| HARDEN-05 | Phase 5 | Pending |
| HARDEN-06 | Phase 5 | Pending |
| HARDEN-07 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 52 total (note: original document stated 47; actual count across IDENT-08 + ADAPT-07 + POLICY-08 + DIR-08 + CLI-06 + DIST-08 + HARDEN-07 = 52)
- Mapped to phases: 52 / 52 (100%)
- Unmapped: 0
- Per-phase distribution:
  - Phase 1 (Foundation & Cryptographic Root): 9 requirements (IDENT-01..08, DIR-06)
  - Phase 2 (Python Adapters & Policy Inspector): 17 requirements (ADAPT-01,02,03,06,07; POLICY-01..08; CLI-01,02,03,06)
  - Phase 3 (Hosted Directory & Cloudflare Submission): 10 requirements (DIR-01..05,07,08; CLI-04,05; DIST-08)
  - Phase 4 (TypeScript SDK & Framework Integrations): 6 requirements (ADAPT-04,05; DIST-04,05,06,07)
  - Phase 5 (Pre-Army Hardening, Docs & Launch): 10 requirements (DIST-01,02,03; HARDEN-01..07)

**Notes on mapping rationale:**
- DIR-06 (Russian payment card hosting confirmation) is in Phase 1, not Phase 3, because it is the Day-1 hosting blocker that determines whether the directory backend is Python-on-Fly.io or TypeScript-on-Cloudflare-Workers. Discovering this at directory-build time is fatal.
- DIST-08 (Cloudflare verified-bot submission) is in Phase 3, not Phase 5, because the opaque review timeline means late submission = no proof by army leave. Filed on Day 1 of Phase 3.
- ADAPT-04 and ADAPT-05 (TypeScript adapters) are in Phase 4 alongside framework demos, run in parallel with Phase 3 directory work via shared `spec/test-vectors/` contracts.

---
*Requirements defined: 2026-05-03*
*Last updated: 2026-05-03 — traceability filled by roadmapper*
