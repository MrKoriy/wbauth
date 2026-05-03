# Feature Research

**Domain:** Agent Identity & Policy Toolkit (OSS Python+TypeScript SDK + hosted directory)
**Researched:** 2026-05-03
**Confidence:** HIGH for spec/Cloudflare/AWS surfaces; MEDIUM for niche framework integration ergonomics; HIGH for anti-feature reasoning

## Executive context

The market state on 3 May 2026:

- **IETF Web Bot Auth** is at draft-meunier-web-bot-auth-architecture-05 (March 2026), with a companion HTTP Message Signatures Directory draft (-05) and a Registry/Signature Agent Card draft (-01). The architecture is built on RFC 9421 (HTTP Message Signatures, Feb 2024). It is a *draft*, not a finalised RFC, and Cloudflare/AWS explicitly note the protocol may change.
- **Verifier-side** is largely solved: Cloudflare ships verification (Web Bot Auth + Signed Agents + Verified Bots), Akamai EdgeWorker collects the three headers natively, DataDome verifies, HUMAN AgenticTrust adds intent monitoring. Visa Trusted Agent Protocol and Mastercard Verifiable Intent both layer on Web Bot Auth.
- **Provider-side** has *only* infrastructure-vendor implementations: AWS Bedrock AgentCore Browser ships service-key signing in preview (`browserSigning: { enabled: true }` flag, no per-agent keys yet); Google ships `Google-Agent` with identity at `https://agent.bot.goog`; Cloudflare ships a Rust + TypeScript reference (`cloudflare/web-bot-auth`); a `npm install web-bot-auth` exists but is browser-extension/Workers focused.
- **No drop-in agent-side SDK exists** for Browser Use, Stagehand, Skyvern, Playwright+LLM, or OpenAI Agents SDK. The `pyauth/requests-http-signature` library implements RFC 9421 for `requests` (so generic signing exists), but it is Web Bot Auth-unaware (no `tag="web-bot-auth"`, no signature-agent header semantics, no JWK directory hosting helper, no Cloudflare-friendly defaults).
- **Policy signal landscape** is fragmented: `robots.txt` (RFC 9309, mature), `ai.txt` v1.1.1 (March 2026, behavioural directives), `llms.txt` (community convention, ~844k sites, no formal RFC, unproven AI-citation impact), `.well-known/http-message-signatures-directory` (Web Bot Auth keys), `.well-known/mcp` and `.well-known/mcp/server-card.json` (SEPs 1960 and 1649/2127, not merged but widely implemented), `.well-known/agent-card.json` (A2A v0.3, ~150 enterprise deployments via Google Cloud Next 2026). No unified fetcher exists.
- **The wedge is real and unowned.** Both halves of the project (identity SDK + policy inspector) have inputs that are stable enough to build against, no dominant agent-side SDK, and clear distribution channels (Browser Use Discord, MCP CWG, AAIF Slack).

## Feature Landscape

### Table Stakes (Users Expect These)

Without these, the SDK does not work for its stated job: drop a few lines of code, get past Cloudflare, and know what the site allows.

| # | Feature | Why Expected | Complexity | Client/Hosted | Primary Framework Served | Notes |
|---|---------|--------------|------------|---------------|--------------------------|-------|
| TS-1 | **Ed25519 keypair generation + secure storage helpers** | Web Bot Auth requires asymmetric keys; HMAC explicitly prohibited by spec. Without keypair UX, nothing else works. Spec mandates `keyid` = base64url JWK SHA-256 Thumbprint per RFC 7638. | LOW | Client | All | Use PyNaCl (Python) and `@noble/ed25519` (TS). Provide `agentid keygen` CLI + `from agentid import generate_keypair`. Hard documentation about not committing keys; refuse to log them. |
| TS-2 | **RFC 9421 HTTP Message Signatures signer** with Web Bot Auth profile | Core of the spec. Must produce `Signature`, `Signature-Input`, `Signature-Agent` headers correctly, with `tag="web-bot-auth"` and the signed components `@authority` (or `@target-uri`) plus `signature-agent`. Cloudflare validates these literally — quoting, ordering, Structured Field syntax all matter. | MEDIUM | Client | All | Reuse `pyauth/http-message-signatures` (Python) but wrap it with the Web Bot Auth defaults (algorithm Ed25519, tag, expiry ≤ 24h, components). For TS reuse Cloudflare's `web-bot-auth` package or rebuild on `@noble/ed25519` + custom Structured Fields encoder. |
| TS-3 | **`requests` + `httpx` + `aiohttp` auth adapters (Python)** | These are 99% of the Python HTTP universe used by AI/agent code. `httpx.Auth` and `requests.auth.AuthBase` are the canonical extension points. `aiohttp` needs a `ClientSession` middleware/trace_config. | LOW-MEDIUM | Client | OpenAI Agents SDK, Skyvern (httpx), custom Playwright+LLM | Three thin adapter classes wrapping TS-2. Each must be drop-in: `httpx.Client(auth=AgentIdentityAuth(...))`. |
| TS-4 | **`fetch` interceptor + `undici` dispatcher (TypeScript/Node)** | TypeScript ecosystem (Stagehand, Browser Use TS, OpenAI JS SDK) uses native `fetch` (Node 22+) backed by `undici`. Need a single `wrappedFetch` and a `Dispatcher` for `undici.request`. | MEDIUM | Client | Stagehand, Browser Use (TS port), Browserbase callers | Browser-context (Playwright `set_extra_http_headers`) does NOT support per-request signatures (signature changes per `created` timestamp + body), so this must be true HTTP layer interception, not browser headers. |
| TS-5 | **Playwright integration helper (Python + TS)** | Browser Use, Stagehand, Skyvern all run on Playwright. The right hook is `page.route("**/*", handler)` — not `set_extra_http_headers` (static; signature is per-request). For requests originated *inside* the browser (XHR/fetch from the page), interception is the only valid path. | MEDIUM | Client | Browser Use, Stagehand, Skyvern | Document the Playwright-vs-HTTP-client split: signing the *navigation* request is what unblocks Cloudflare's bot challenge; in-page XHR is secondary. |
| TS-6 | **`/.well-known/http-message-signatures-directory` JWKS server (FastAPI/Express)** | Cloudflare *requires* the directory to be reachable over HTTPS, served with content type `application/http-message-signatures-directory+json`, and to itself be signed (the directory response carries `Signature` + `Signature-Input`). Without this, no verification is possible. | MEDIUM | Client (self-host) OR Hosted (agentpassport.dev) | All | Provide a one-file FastAPI router and an Express middleware. Also provide a Cloudflare Workers / Vercel Edge variant for users without a backend. |
| TS-7 | **`Signature-Agent` URI generation + multi-key lifecycle (active/rotation grace)** | Cloudflare verifies `Signature-Agent` literally. JWK directory needs `nbf`/`exp` per key. Need to support rotation: ship new key, keep old key valid for grace period, then retire. | MEDIUM | Client + Hosted | All | Default rotation cadence: 90 days, 14-day overlap. Don't enforce — recommend. |
| TS-8 | **`robots.txt` parser with RFC 9309 compliance + AI user-agent matching** | This is the foundational policy signal. Must support `User-Agent` matching for `GPTBot`, `ClaudeBot`, `PerplexityBot`, `Google-Extended`, `CCBot`, `Bytespider`, plus generic `*`. Use Scrapy's `protego` (RFC 9309 compliant) or `robotspy`. | LOW | Client | All | Caching with TTL respect (`Cache-Control` from origin). |
| TS-9 | **`ai.txt` v1.1.1 parser** | Fast-emerging behavioural-control standard (March 2026 spec). Section-header format `[identity]`, `[permissions]`, `[restrictions]`, `[attribution]`, `[contact]`, `[content-types]`. Distinct from robots.txt (access) and llms.txt (attention). | LOW | Client | All | Custom parser; spec is small. Return structured object with each section. |
| TS-10 | **`llms.txt` parser** | 844k sites, low ROI but extremely cheap to support and users will ask. H1 + blockquote + H2-with-link-list markdown structure. | LOW | Client | All | Use `markdown-it` (TS) or `mistune` (Python). Treat absence as silent OK. |
| TS-11 | **Unified `inspect(url)` async function** returning a structured `SitePolicy` object | One function that fetches all policy signals in parallel and returns one normalised object. This is the core value of the policy half: agents call this once before a task, get a verdict (`allowed`, `restricted`, `forbidden`) and structured details. | MEDIUM | Client | All | Returns: `{robots, ai_txt, llms_txt, mcp, agent_card, web_bot_auth_required, rate_hints, fetched_at, ttl}`. Concurrency via `asyncio.gather` / `Promise.all`. ETag/Cache-Control respected. |
| TS-12 | **Hosted directory: register / lookup / verify (FastAPI + Postgres)** | Two-sided market: agent operators need somewhere to publish; verifiers (Cloudflare, custom origins) need somewhere to look up. The hosted directory IS the public good. Must accept the Signature Agent Card format from draft-meunier-webbotauth-registry-01 (all fields optional, ≥1 required), serve at a stable URL, and resign daily. | MEDIUM | Hosted | All | Schema: `client_name`, `client_uri`, `logo_uri`, `contacts`, `expected-user-agent`, `rfc9309-product-token`, `rfc9309-compliance`, `trigger`, `purpose`, `targeted-content`, `rate-control`, `rate-expectation`, `known-urls`, `keys` (JWKS). Public read; OAuth/API-key write. |
| TS-13 | **Documentation site** with quickstart, "why this exists" narrative, and 3 framework integration recipes | OSS distribution is doc-driven. Browser Use, Laminar, Stagehand all won via "default in the README of the partner project". Quickstart must be 60 seconds to working signed request. | MEDIUM | Hosted (static) | All | Astro or VitePress; deploy on Cloudflare Pages or GitHub Pages. |
| TS-14 | **Cloudflare Verified Bot / Signed Agent submission flow documentation + helper script** | Cloudflare's submission is a manual form, but the *prerequisite* (directory live, headers correct, `crawltest.com/cdn-cgi/web-bot-auth` test passes) is automatable. Without successful verification, the SDK doesn't deliver its headline value. | LOW | Client (CLI) | All | `agentid verify --domain mybot.example.com` runs Cloudflare's test endpoint and prints pass/fail per criterion. |
| TS-15 | **CLI: `agentid` (Python) and `npx agentid` (TS)** | Standard for OSS infra tools. Must cover: `keygen`, `serve` (run a directory locally), `inspect <url>` (run policy fetcher), `verify <domain>` (Cloudflare crawltest), `register --directory <url>` (push to hosted directory). | LOW-MEDIUM | Client | All | Click (Python), Commander (TS). |

### Differentiators (Competitive Advantage)

These features turn "another OSS package" into "the obvious default for the agent-friendly web."

| # | Feature | Value Proposition | Complexity | Client/Hosted | Primary Framework Served | Notes |
|---|---------|-------------------|------------|---------------|--------------------------|-------|
| D-1 | **Identity + policy in one import** (`from agentid import sign, inspect`) | Nobody has bundled these. Web Bot Auth answers "who am I?", policy inspector answers "what am I allowed to do here?" The combination IS the project's positioning per PROJECT.md core value. | LOW (composition) | Client | All | One package, two entry points. |
| D-2 | **3-line install on every major framework** with copy-paste recipes verified end-to-end | Distribution proxy: if the README of Browser Use / Stagehand examples directory says "install agentid", every new user discovers you. Laminar's path. | MEDIUM (continuous) | Client | Browser Use, Stagehand, Playwright+LLM, OpenAI Agents SDK | Submit PRs to `examples/` of each. Maintain integration tests pinned to each framework version. |
| D-3 | **One-shot policy verdict with explanation** (`policy.verdict` returns `allowed | restricted | forbidden` with `reasons: [...]`) | Saves the user from interpreting raw `robots.txt` grammar, ai.txt sections, MCP availability, and signature requirement signals. The verdict + reasons object is what an agent's planner actually wants. | MEDIUM | Client | All (especially planner-style agents like OpenAI Agents SDK) | Rule engine: missing/forbidding `robots.txt` → forbidden; `ai.txt` `[restrictions]` `No-Inference` → restricted; Web Bot Auth required and not present → restricted (with mitigation hint). |
| D-4 | **Auto-detection: "this site requires Web Bot Auth"** | Cloudflare's `Server: cloudflare` + 403 + Turnstile interstitial fingerprint, plus the upcoming `Accept-Signature` response header convention, lets `inspect()` proactively tell the user "sign your requests or you'll be blocked here." Pre-flight insight is a compelling differentiator. | MEDIUM | Client | All | Heuristic library, exposed as `policy.signing_recommended` boolean + `policy.signing_required` boolean. |
| D-5 | **Free hosted directory at `agentpassport.dev`** with HTTPS, JWKS resigning, public lookup, `whois`-style web view | Lowers the barrier for individual developers who don't run their own backend. Drives network effects: more agents in the directory → more verifier integrations cite it → more agents use it. | MEDIUM | Hosted | All | Apache 2.0 reference. Publish a JSON dump weekly. |
| D-6 | **`@signed` decorator** for Python (and TS template-tag equivalent) | The "viral OSS API" identified in PROJECT.md — `@signed def fetch_thing(url): ...`. Memorable, copy-pasteable, Tweet-able. | LOW | Client | All | Wraps any function returning an `httpx`/`requests` call. |
| D-7 | **MCP-aware policy inspector** (parses `.well-known/mcp` and `.well-known/mcp/server-card.json` per SEP-1960 and SEP-1649/2127) | If a site exposes an MCP server, an agent should *prefer the MCP route* over scraping. Inspector returns `mcp_endpoints`, `tools_summary`, `auth_requirements`. Distinguishes us from a pure Web Bot Auth play. | MEDIUM | Client | OpenAI Agents SDK, Browser Use users running MCP-aware planners | SEPs are not merged but are widely implemented; treat as best-effort with version field. |
| D-8 | **A2A AgentCard discovery** (`/.well-known/agent-card.json`) | A2A v0.3 has ~150 enterprise deployments. If the target site is itself an agent (Salesforce, ServiceNow, etc.), our inspector returns its capabilities, skills, supported_interfaces, default_input_modes — saving tokens vs scraping. | LOW | Client | OpenAI Agents SDK, custom multi-agent flows | Spec field list is well-defined; map to our normalised object. |
| D-9 | **Receipts: signed evidence of pre-flight check** (saves a JSON receipt of `inspect(url)` result with timestamp + hash, optionally counter-signed by hosted directory) | Auditability for agents-in-production: "before I scraped, the site policy permitted it." Useful for legal cover and observability tooling integration (Laminar, AgentOps consume the receipt). | MEDIUM | Client + Hosted (counter-signing optional) | All | Write to local SQLite by default; optional cloud sync. |
| D-10 | **Pre-flight in <100ms p50 with intelligent caching** | Agents do thousands of requests per task. Per-domain cache with `Cache-Control` / `ETag` respect, in-process LRU + optional Redis. | LOW | Client | All | TTL defaults: robots.txt 24h, ai.txt 1h, llms.txt 24h, MCP 1h, signatures directory respects own `exp`. |
| D-11 | **TypeScript and Python feature parity from day 1** (not "TS later") | Most competing identity tools are single-language. Browser Use (Python) and Stagehand (TS) cover both halves of the agent-framework world; you can't ship one without the other. | HIGH (continuous) | Client | All | Mono-repo with shared test fixtures; TS port can be partially agent-generated per PROJECT.md constraint, but contracts (header bytes, signature inputs) must match exactly. |
| D-12 | **Reference bot listed in Cloudflare Verified Bots / Signed Agents directory** | Demonstrates the SDK end-to-end works. Free credibility. The CLI can ship a "demo bot" that runs through the full flow live as a test. | LOW | Client | — | Runs as a one-off submission. |
| D-13 | **OpenTelemetry hook for every signed request and inspect() call** | Plays nicely with Laminar, AgentOps, OpenLLMetry. Doesn't compete with observability — *feeds* it. Extends distribution by becoming a default-instrumented component in those stacks. | LOW | Client | All | Standard OTEL Python + JS exports; no custom collector needed. |

### Anti-Features (Commonly Requested, Often Problematic)

These will be requested by users and should be explicitly refused (with the alternative documented).

| # | Feature | Why Requested | Why Problematic | Alternative |
|---|---------|---------------|-----------------|-------------|
| A-1 | **Stealth / fingerprint spoofing / undetected-chromedriver style features** | "I want to bypass Cloudflare without registering my agent." | Directly contradicts the project thesis (PROJECT.md: "идентичность — это про честность, не про anti-detection"). Ethical and legal risk; would taint the project's standing with Cloudflare/AWS/Akamai partnerships. Hyperbrowser/undetected-chromedriver already serve this market — they own it. | Document: "If you want to be invisible to bot detection, this is not the tool. Use [stealth library X], understand the legal context, and accept that signed agents and stealth agents are mutually exclusive identities." |
| A-2 | **CAPTCHA solver / 2Captcha integration** | Logical follow-on from "we get past Cloudflare". | We get past Cloudflare *by signing identity*, not by solving CAPTCHAs. Adding solvers re-merges with the stealth path. Also: CAPTCHA solving is a regulated commercial service; we don't want to be a billing intermediary. | Document the difference: signed agents bypass *interstitial bot challenges* (Cloudflare Turnstile pre-check), they don't solve *legitimate human-required CAPTCHAs* (e.g., explicit user-verification flows). For the latter, refer to commercial services. |
| A-3 | **Vision-based browser automation** | Adjacent to "agent identity" in the user's mind: "if I have identity, also automate browsing". | Out of scope per PROJECT.md (explicit). Browser Use, Stagehand, Skyvern own this. Building it would be a 12–24-month catch-up against funded incumbents. | Provide thin integration recipes for those tools; do not duplicate. |
| A-4 | **Observability / replay / session recording** | Agents fail; users want to know why. | Out of scope per PROJECT.md (explicit) — Laminar (S24, $3M), AgentOps, Browserbase, AWS AgentCore session replay all own this. Requires continuous infra work that breaks the "must survive 6+ months without maintainer" constraint. | OpenTelemetry hook (D-13) lets every observability stack ingest our spans natively. |
| A-5 | **Site-side verification SDK / origin server middleware** | Symmetric mirror of the agent-side SDK; sites want to verify incoming signed agents. | Two-sided market problem: chicken-and-egg adoption is brutal, requires sales to website owners, slow feedback loop. PROJECT.md explicitly defers to v2. Cloudflare, Akamai, DataDome already serve this need on the high end. | Document third-party integration paths: install Cloudflare Bots, deploy Akamai EdgeWorker, etc. Keep ourselves in the agent-side niche. |
| A-6 | **Site-side MCP-converter (auto-emit MCP server from existing site)** | The "make my site agent-friendly" pitch. | Out of scope per PROJECT.md (explicit). FastMCP, Stainless, Speakeasy Gram, Klavis, Composio already attack this. Requires sales to non-developer site owners — distribution is hard. | Inspect-side support (D-7) is sufficient: when a site has MCP, we surface it. |
| A-7 | **gRPC / WebSocket signing** | Comes up for streaming/real-time use cases. | Out of scope per PROJECT.md (explicit). Web Bot Auth is HTTP-only. Spec doesn't cover non-HTTP. Tiny audience, would balloon code surface. | "If you need this, file a discussion. We'll evaluate when there are 10+ confirmed users." |
| A-8 | **Web UI / dashboard for the directory in v1** | Standard SaaS expectation. | Out of scope per PROJECT.md (explicit). JSON API + CLI + a static `whois`-style web page are sufficient. UI is multiplicative complexity (auth, sessions, forms, design). | After army; if traction warrants. |
| A-9 | **Paid tier in v1** (paywall on signing, hosted directory for $X/mo) | "How will you make money?" | Per PROJECT.md, monetisation is post-army. Adoption beats revenue at this stage; Apache 2.0 + free hosted directory maximises stars/distribution. RU-jurisdiction billing constraints (no Stripe Atlas, no Mercury) make payment infrastructure fragile. | Document the post-v1 monetisation thinking publicly (transparent: directory tiers later; SDK always free). |
| A-10 | **Built-in proxy rotation / IP rotation** | Adjacent ask: "if I sign my requests, also let me rotate IPs." | Combines a positive identity (signed) with a negative identity (rotating IPs) — incoherent. Existing solution: Bright Data, Smartproxy, Kernel residential proxies. | Document: signed agents should have stable IPs (or Cloudflare-trusted IP ranges). Refer out for proxy needs. |
| A-11 | **Custom signature algorithm support beyond Ed25519 + ECDSA P-256** | Spec allows other algorithms (RSASSA-PSS in test vectors). | Cloudflare currently emphasises Ed25519. RSA keys are 6× larger and 30× slower to verify. Supporting more algorithms expands attack surface and test matrix without serving real users. | Ed25519 default + ECDSA P-256 for ecosystems that mandate it (some IoT/HSM constraints). Decline RSA unless a paying enterprise asks. |
| A-12 | **Automated policy enforcement / agent quarantine on failure** | "If `inspect()` returns `forbidden`, raise an exception and stop my agent." | Policy interpretation is a user decision, not an SDK decision. We surface the verdict; *they* enforce. Embedding enforcement creates liability and removes user control. | Provide `policy.raise_if_forbidden()` as opt-in helper. Default behaviour is informational only. |
| A-13 | **Encrypted private key storage / KMS integration in v1** | Security-conscious users will ask. | Real KMS integration (AWS KMS, GCP KMS, HashiCorp Vault) is per-platform plumbing that explodes the support matrix. Solo maintainer can't keep five KMS adapters working through army absence. | v1: `agentid keygen` writes to file with `0600` perms + clear docs ("don't commit, use your platform's secret manager"). v2: pluggable key resolver interface, KMS adapters as separate packages. |
| A-14 | **Built-in browser context / Playwright launch wrapper** | "Just give me one function that opens a browser, signs everything, and inspects." | Bundles two complex systems (browser automation + identity) into one opinionated wrapper. Reduces the SDK's drop-in compatibility. Browser Use is already this wrapper. | Provide separate `agentid` package + integration recipes; don't ship a browser-launcher. |
| A-15 | **Real-time directory mirroring / CDN replication of agentpassport.dev** | "What if your hosted directory goes down?" | Premature optimisation; resilience for v1 is "Railway/Fly.io managed Postgres + cached JWKS". Web Bot Auth allows multiple directories per agent; users with HA needs can self-host. | Document: directory format is open; users can mirror via cron or self-host via TS-6. |

## Feature Dependencies

```
TS-1 (keygen) ──────────────────┐
                                 │
                                 ▼
TS-2 (RFC 9421 signer) ──────► TS-3 (Python adapters)
                            │
                            ├─► TS-4 (TS adapters)
                            │
                            └─► TS-5 (Playwright helper)


TS-1 + TS-2 ──► TS-6 (JWKS directory server) ──► TS-7 (rotation lifecycle)
                                              │
                                              └─► TS-12 (hosted directory)


TS-8 (robots.txt) ──┐
TS-9 (ai.txt) ──────┤
TS-10 (llms.txt) ───┼─► TS-11 (inspect()) ──► D-3 (verdict engine)
D-7 (MCP discovery) │                       │
D-8 (A2A discovery) ┘                       └─► D-4 (signing-required detector)


TS-3/TS-4 + TS-11 ──► D-1 (unified import) ──► D-6 (@signed decorator)


TS-12 (hosted directory) ──► D-5 (free public directory)
                          └─► D-9 (counter-signed receipts)


TS-13 (docs) + D-2 (framework recipes) + D-12 (reference bot) ──► distribution
```

### Dependency Notes

- **TS-2 is the cryptographic root.** Wrong here = everything downstream (Python adapters, TS adapters, Playwright helper, directory server) breaks. Get the bytes-on-the-wire identical to Cloudflare's reference implementation in week 1; lock with golden-file tests against `crawltest.com/cdn-cgi/web-bot-auth`.
- **TS-6 (directory server) is a hard dependency for any verifier interaction.** A signed request without a fetchable, correctly-served directory is rejected. Both client-self-host and hosted-directory paths must work end-to-end before any framework integration is meaningful.
- **TS-11 (inspect) is the policy half's keystone.** All individual policy parsers (TS-8, TS-9, TS-10, D-7, D-8) are commodities; the value is the unified, parallel-fetched, normalised object.
- **D-2 (framework recipes) gates distribution.** Browser Use and Stagehand are the dominant agent frameworks; without verified, working integrations in their `examples/`, the project cannot reach its target users.
- **D-3 (verdict engine) and D-4 (signing-required detector) compose policy + identity** — they are how the project's PROJECT.md core value ("get identity AND know your rights — before the first request") manifests in the API.
- **TS-12 conflicts in scope with A-5.** Hosted directory is for *agent operators publishing identity*, not for *site owners verifying incoming agents*. Mixing these in v1 would explode complexity.

## MVP Definition

### Launch With (v1)

Six-week target. Ruthless prioritisation: ship the smallest set that delivers PROJECT.md's core value ("identity + policy in one line") to *one* framework end-to-end.

- [x] **TS-1** Keygen (Python + TS)
- [x] **TS-2** RFC 9421 signer with Web Bot Auth profile (Python + TS — TS port via agents per PROJECT.md)
- [x] **TS-3** Python `httpx` + `requests` auth adapters (`aiohttp` if time permits)
- [x] **TS-4** TS `fetch` interceptor (undici dispatcher if time permits)
- [x] **TS-5** Playwright integration helper (Python first, TS via shared docs)
- [x] **TS-6** JWKS directory server (FastAPI + Express)
- [x] **TS-7** Multi-key lifecycle (basic: support old + new key during overlap)
- [x] **TS-8** robots.txt parser (use `protego`)
- [x] **TS-9** ai.txt parser
- [x] **TS-10** llms.txt parser (basic: H1 + sections)
- [x] **TS-11** `inspect(url)` returning `SitePolicy` object
- [x] **TS-12** Hosted directory at `agentpassport.dev` (register, lookup, public read)
- [x] **TS-13** Docs site (Astro/VitePress, GitHub Pages or Cloudflare Pages)
- [x] **TS-14** Cloudflare verification helper (CLI: `agentid verify --domain`)
- [x] **TS-15** CLI: keygen, serve, inspect, verify, register
- [x] **D-1** Unified import (`from agentid import sign, inspect`)
- [x] **D-2** Working examples for **Browser Use**, **Playwright + OpenAI Agents SDK**, **Stagehand** (3 framework integrations is the project's stated minimum)
- [x] **D-3** Verdict engine (`policy.verdict`)
- [x] **D-6** `@signed` decorator
- [x] **D-12** Reference bot listed in Cloudflare directory (proves end-to-end)

### Add After Validation (v1.x — post-launch, pre-army if time)

- [ ] **D-4** Signing-required auto-detection (heuristics for Cloudflare 403 + Turnstile fingerprint) — *trigger: confirmed first 3 users hit a non-signed Cloudflare block*
- [ ] **D-7** MCP discovery (.well-known/mcp + server-card) — *trigger: SEP-1960 or SEP-1649 merged into MCP spec, OR 3 production users ask*
- [ ] **D-8** A2A AgentCard discovery — *trigger: enterprise user asks; until then YAGNI*
- [ ] **D-10** Caching layer with Redis backend — *trigger: hosted directory hits >1000 lookups/day*
- [ ] **D-13** OpenTelemetry hook — *trigger: Laminar or AgentOps user asks*
- [ ] **`aiohttp` adapter** — *trigger: 5+ users ask*
- [ ] **TS undici dispatcher** — *trigger: Stagehand or Browser Use TS users specifically*

### Future Consideration (v2+ — explicitly post-army, if project has traction)

- [ ] **D-5 enhancements**: directory weekly JSON dump, CDN mirroring, web search UI — *defer until directory has >100 entries*
- [ ] **D-9** Counter-signed receipts — *defer until policy compliance becomes a business requirement for users*
- [ ] **D-11** TS feature parity automation (CI tests across Python + TS) — *defer until both reach >2k stars*
- [ ] **Hosted paid tier** — *post-army; depends on jurisdiction situation per PROJECT.md*
- [ ] **Site-side verification SDK** — *deferred to v2 per PROJECT.md*
- [ ] **KMS adapters (AWS, GCP, Vault)** — *trigger: paying enterprise customer*
- [ ] **WebMCP integration** — *trigger: WebMCP exits Chrome flag, Firefox/Safari sign on*

## Feature Prioritization Matrix

P1 = must have for launch. P2 = should have within 60 days post-launch. P3 = future.

| # | Feature | User Value | Implementation Cost | Priority |
|---|---------|------------|---------------------|----------|
| TS-1 | Keygen + storage helpers | HIGH | LOW | **P1** |
| TS-2 | RFC 9421 signer w/ WBA profile | HIGH | MEDIUM | **P1** |
| TS-3 | Python `httpx`/`requests` adapters | HIGH | LOW-MEDIUM | **P1** |
| TS-4 | TS `fetch` interceptor | HIGH | MEDIUM | **P1** |
| TS-5 | Playwright integration helper | HIGH | MEDIUM | **P1** |
| TS-6 | JWKS directory server | HIGH | MEDIUM | **P1** |
| TS-7 | Multi-key lifecycle | MEDIUM | MEDIUM | **P1** (basic), P2 (full rotation) |
| TS-8 | robots.txt parser | HIGH | LOW | **P1** |
| TS-9 | ai.txt parser | MEDIUM | LOW | **P1** |
| TS-10 | llms.txt parser | LOW | LOW | **P1** (cheap to include) |
| TS-11 | Unified `inspect()` | HIGH | MEDIUM | **P1** |
| TS-12 | Hosted directory | HIGH | MEDIUM | **P1** |
| TS-13 | Docs site | HIGH | MEDIUM | **P1** |
| TS-14 | Cloudflare verify helper | HIGH | LOW | **P1** |
| TS-15 | CLI | MEDIUM | LOW-MEDIUM | **P1** |
| D-1 | Unified import | HIGH | LOW | **P1** |
| D-2 | 3 framework recipes | HIGH | MEDIUM | **P1** |
| D-3 | Verdict engine | HIGH | MEDIUM | **P1** |
| D-4 | Signing-required auto-detection | HIGH | MEDIUM | **P2** |
| D-5 | Free hosted directory (TS-12 with public lookup UX) | HIGH | MEDIUM | **P1** |
| D-6 | `@signed` decorator | MEDIUM (high virality) | LOW | **P1** |
| D-7 | MCP discovery | MEDIUM | MEDIUM | **P2** |
| D-8 | A2A AgentCard discovery | LOW (enterprise-only) | LOW | **P2** |
| D-9 | Receipts | MEDIUM | MEDIUM | **P3** |
| D-10 | Caching layer | MEDIUM | LOW | **P2** |
| D-11 | TS feature parity automation | LOW | HIGH | **P3** |
| D-12 | Reference bot in Cloudflare directory | HIGH (credibility) | LOW | **P1** |
| D-13 | OpenTelemetry hook | MEDIUM | LOW | **P2** |

## Competitor Feature Analysis

| Feature | Cloudflare `web-bot-auth` (TS+Rust) | AWS AgentCore Browser | `agentpassport.com` / `agentidentity-auth` | `pyauth/requests-http-signature` | **Our approach** |
|---------|-------------------------------------|------------------------|------------------------------------------|---------------------------------|-----------------|
| Ed25519 keygen | Yes (Rust) | Hidden (service-managed) | Yes | No (BYOK) | **Yes, both langs, plus storage UX + CLI** |
| RFC 9421 signing | Yes | Yes (transparent) | Custom JWT format, not WBA | Yes (pure RFC, no WBA profile) | **Yes, with WBA defaults baked in** |
| `Signature-Agent` header | Yes | Yes | N/A (different model) | No | **Yes** |
| JWKS directory hosting | Workers example | Service-hosted | N/A | No | **Yes (FastAPI + Express + Workers)** |
| Drop-in Python framework adapter | No | N/A (AWS-specific) | Different model (JWT, not WBA) | `requests` only, no WBA semantics | **httpx + requests + aiohttp + Playwright** |
| Drop-in TS framework adapter | Browser-extension example only | N/A | Limited | N/A | **fetch + undici + Playwright** |
| Policy inspector (robots/ai/llms) | No | No | No | No | **Yes — unique combination** |
| MCP discovery | No | No | No | No | **Yes (P2)** |
| Hosted public directory | Cloudflare Radar (their list) | AWS-internal | Vercel demo | N/A | **Yes — independent, OSS, neutral** |
| Cloudflare verify integration helper | Implicit (you use crawltest yourself) | Implicit | No | No | **Yes (`agentid verify`)** |
| Per-language reference bot | Yes (Cloudflare's own) | Yes (AWS's own) | Demo only | No | **Yes — registered as our own demo bot** |

**Positioning summary:** Cloudflare's `web-bot-auth` is a *reference implementation by the verifier* — not optimised for agent-framework drop-in. AWS AgentCore is *vendor-locked* — only works inside Bedrock AgentCore Browser. `agentpassport.com` and `agentidentity-auth` are *adjacent identity systems with different threat models* (JWT-based, not Web Bot Auth). `pyauth/requests-http-signature` is *RFC-correct but Web Bot Auth-unaware*. **Nobody ships the agent-side, framework-aware, identity + policy combination.** That gap is where this project lives.

## Sources

### IETF & Standards (HIGH confidence)
- [draft-meunier-web-bot-auth-architecture-05 (March 2026)](https://datatracker.ietf.org/doc/html/draft-meunier-web-bot-auth-architecture)
- [draft-meunier-http-message-signatures-directory-05](https://datatracker.ietf.org/doc/html/draft-meunier-http-message-signatures-directory-05)
- [draft-meunier-webbotauth-registry-01 (Signature Agent Card)](https://www.ietf.org/archive/id/draft-meunier-webbotauth-registry-01.html)
- [RFC 9421: HTTP Message Signatures (Feb 2024)](https://www.rfc-editor.org/rfc/rfc9421)
- [RFC 9309: Robots Exclusion Protocol](https://datatracker.ietf.org/doc/html/rfc9309)

### Cloudflare (HIGH confidence)
- [Web Bot Auth · Cloudflare bot solutions docs](https://developers.cloudflare.com/bots/reference/bot-verification/web-bot-auth/)
- [Signed agents · Cloudflare bot solutions docs](https://developers.cloudflare.com/bots/concepts/bot/signed-agents/)
- [Signed agents policy · Cloudflare](https://developers.cloudflare.com/bots/concepts/bot/signed-agents/policy/)
- [Beyond IP lists: a registry format for bots and agents (Cloudflare blog)](https://blog.cloudflare.com/agent-registry/)
- [The age of agents: cryptographically recognizing agent traffic](https://blog.cloudflare.com/signed-agents/)
- [Forget IPs: using cryptography to verify bot and agent traffic](https://blog.cloudflare.com/web-bot-auth/)
- [Message Signatures are now part of our Verified Bots Program](https://blog.cloudflare.com/verified-bots-with-cryptography/)
- [GitHub: cloudflare/web-bot-auth (Rust + TS reference)](https://github.com/cloudflare/web-bot-auth)

### AWS (HIGH confidence)
- [Reducing CAPTCHAs with Web Bot Auth — Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-web-bot-auth.html)
- [AWS announcement: AgentCore Browser Web Bot Auth Preview (Oct 2025)](https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-bedrock-agentcore-browser-web-bot-auth-preview/)
- [Reduce CAPTCHAs for AI agents browsing the web with Web Bot Auth (AWS blog)](https://aws.amazon.com/blogs/machine-learning/reduce-captchas-for-ai-agents-browsing-the-web-with-web-bot-auth-preview-in-amazon-bedrock-agentcore-browser/)

### Verifier ecosystem (MEDIUM-HIGH confidence)
- [DataDome: Signed, Sealed, and Delivered — authenticating AI agents](https://datadome.co/threat-research/the-case-for-authenticating-ai-agents/)
- [Akamai: Redefine Trust with Web Bot Authentication](https://www.akamai.com/blog/security/redefine-trust-web-bot-authentication)
- [HUMAN AgenticTrust (referenced via OpenAI ChatGPT agent allowlisting docs)](https://help.openai.com/en/articles/11845367-chatgpt-agent-allowlisting)
- [Visa Trusted Agent Protocol specifications](https://developer.visa.com/capabilities/trusted-agent-protocol/trusted-agent-protocol-specifications)
- [Visa: Securing agentic commerce with Cloudflare](https://blog.cloudflare.com/secure-agentic-commerce/)
- [GitHub: visa/trusted-agent-protocol](https://github.com/visa/trusted-agent-protocol)

### Policy signal landscape (HIGH for spec, MEDIUM for adoption claims)
- [llms.txt official spec](https://llmstxt.org/)
- [ai.txt Specification v1.1.1 (Jan/March 2026)](https://www.ai-visibility.org.uk/specifications/ai-txt/)
- [SEP-1649: MCP Server Cards via .well-known](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1649)
- [SEP-1960: .well-known/mcp Discovery Endpoint](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1960)
- [SEP-2127: PR for MCP Server Cards](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2127)
- [A2A Protocol Specification (latest)](https://a2a-protocol.org/latest/specification/)
- [A2A AgentCard concept](https://agent2agent.info/docs/concepts/agentcard/)

### Existing libraries (HIGH confidence — directly reviewed)
- [pyauth/http-message-signatures (Python RFC 9421)](https://github.com/pyauth/http-message-signatures)
- [pyauth/requests-http-signature (Python `requests` auth plugin)](https://github.com/pyauth/requests-http-signature)
- [HTTPX custom auth class docs](https://www.python-httpx.org/advanced/authentication/)
- [Scrapy `protego` (RFC 9309 robots parser)](https://github.com/scrapy/protego)
- [robotspy (RFC 9309 robots parser)](https://github.com/andreburgaud/robotspy)
- [Playwright `set_extra_http_headers` (Python)](https://playwright.dev/python/docs/api/class-browsercontext)

### Adjacent / inspirational (MEDIUM confidence on details)
- [AgentPassport (open source agent identity, JWT-based)](https://agentspassports.com/)
- [Stagehand Playwright integration](https://docs.stagehand.dev/v3/integrations/playwright)
- [OpenAI Agents SDK Python docs](https://openai.github.io/openai-agents-python/)
- [OpenAI Python httpx custom client docs](https://deepwiki.com/openai/openai-python/7.4-custom-http-clients-and-proxies)

---
*Feature research for: Agent Identity & Policy Toolkit*
*Researched: 2026-05-03*
