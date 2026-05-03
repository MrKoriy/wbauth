# Project Research Summary

**Project:** Agent Identity & Policy Toolkit (agentpassport.dev)
**Domain:** OSS SDK + hosted directory for AI agent identity (IETF Web Bot Auth / RFC 9421) and pre-flight site-policy inspection
**Researched:** 2026-05-03
**Confidence:** HIGH for protocol/stack/architecture; MEDIUM for hosting (Russia-card availability unconfirmed until tested); MEDIUM for Browser Use/Stagehand integration specifics

---

## Executive Summary

This project occupies a real and currently unowned gap: there is no drop-in, agent-framework-aware SDK that implements IETF Web Bot Auth (RFC 9421 + Ed25519) for the agent side. Cloudflare and AWS have built the verifier side; no one has built the agent side for Browser Use, Stagehand, Playwright+LLM, or OpenAI Agents SDK. The policy inspector half (robots.txt + ai.txt + llms.txt + MCP/.well-known discovery in one `inspect(url)` call) compounds the uniqueness: no tool bundles identity and pre-flight policy together. The research across all four files converges on the same conclusion: the wedge is real, the spec is stable enough to build against, and the moment to ship is now before a VC-backed team copies it.

The recommended build approach is a boring-stack Python-first monorepo: `http-message-signatures` (pyauth) for RFC 9421 signing, `cryptography` (PyCA) for Ed25519, `httpx` for the primary adapter, FastAPI + SQLite-on-volume (or managed Postgres) for the directory backend, and Astro Starlight on GitHub Pages for docs. TypeScript SDK wraps Cloudflare's `web-bot-auth` npm package. Every choice is filtered through a single constraint: must survive 6+ months unmaintained. This rules out anything requiring secret rotation, manual intervention, or active billing management.

The dominant risk is not technical — the signing protocol is well-specified and Cloudflare publishes a test endpoint. The dominant risk is operational: Russia-card hosting must be confirmed on day 1 before writing any code; Cloudflare's verified-bot submission takes weeks and must be completed before army leave; dependency rot during a 6-month unmaintained window is the most likely cause of silent breakage post-army. The mitigation strategy is locked major-version pins, Dependabot configured before leaving, PyPI/npm OIDC trusted publishers (no token to rotate), and a pre-army hardening phase that is treated as a first-class deliverable.

---

## Key Findings

### Recommended Stack

The stack is deliberately minimal. Two thin SDKs (Python primary, TypeScript via agents) wrap existing battle-tested RFC 9421 implementations rather than rolling custom crypto. The directory backend is a ~150-line FastAPI service on SQLite-on-volume (upgradeable to managed Postgres when needed). Docs are static Astro Starlight on GitHub Pages — zero CMS, zero CDN bill, zero thing to renew.

**Core technologies:**
- `http-message-signatures` 2.0.1 (pyauth): canonical Python RFC 9421 implementation — don't reinvent, this is the signing primitive
- `cryptography` 46.x (PyCA): Ed25519 keygen and JWK export — transitive dep of everything, no extra install footprint
- `httpx` 0.28.x: primary Python HTTP client with first-class `Auth` subclass pattern for signing integration
- `web-bot-auth` npm (Cloudflare): the TypeScript reference implementation — wrapping this is safer than a parallel implementation
- FastAPI 0.118+ / SQLite + WAL: directory backend — async-first, TestClient for CI, SQLite eliminates managed-service risk during army leave
- Fly.io (primary) / Railway (fallback) / Cloudflare Workers+D1 (zero-billing fallback): directory hosting — subject to Russia-card availability test on day 1
- Astro Starlight + GitHub Pages: docs — most army-leave-proof hosting in the stack; builds on push, old site keeps serving if Astro breaks
- `uv` + `ruff` + `pyright` / `pnpm` + `biome` + `vitest`: tooling — one-tool philosophy, lockfile-driven, deterministic CI

**Critical version requirements:**
- Python floor: 3.11 (security fixes through Oct 2027; `http-message-signatures` requires >=3.10)
- Node floor: 20 LTS (needed for native `crypto.subtle.sign` Ed25519 in WebCrypto; `web-bot-auth` requirement)
- Pydantic: v2 strictly — FastAPI >=0.100 requires it; v1 is EOL

**Do not use:** MkDocs Material (maintenance mode Nov 2025, Insiders deleted May 2026), Stripe (OFAC/RU), Vercel (RU card failures), Supabase/Firebase/PlanetScale (free-tier policy changes that brick apps during absence), any managed service requiring periodic reauth or secret rotation.

### Expected Features

All four research files agree on the same MVP scope. The table-stakes set is large because each element is a hard dependency for the ones that follow.

**Must have (table stakes — P1, locked v1 scope):**
- TS-1/TS-2: Ed25519 keygen + RFC 9421 signer with Web Bot Auth profile (Cloudflare-safe defaults baked in; this is the cryptographic root — wrong here = everything breaks)
- TS-3/TS-4: Python `httpx`/`requests` auth adapters and TypeScript `fetch` interceptor (99% of the HTTP universe used by agent frameworks)
- TS-5: Playwright `page.route()` integration helper (the right hook; `set_extra_http_headers` is wrong because signatures are per-request, not static)
- TS-6/TS-7: Self-hostable JWKS directory server (FastAPI router + Express middleware) with multi-key rotation lifecycle
- TS-8/TS-9/TS-10/TS-11: robots.txt + ai.txt + llms.txt parsers unified into `inspect(url)` returning a `SitePolicy` object
- TS-12/D-5: Hosted directory at agentpassport.dev (register, lookup, public JWKS serving)
- TS-14/TS-15: CLI (`agentid keygen`, `inspect`, `verify`, `register`) and Cloudflare verification helper
- D-1/D-6: Unified import (`from agentpassport import sign, inspect`) and `@signed` decorator
- D-2: Working integration examples for Browser Use, Stagehand, and Playwright+OpenAI Agents SDK
- D-3: Verdict engine (`policy.verdict` returns `allowed|restricted|forbidden` with reasons)
- D-12: Reference bot listed in Cloudflare's Signed Agents directory (credibility proof)

**Should have (competitive differentiators — P2, add post-launch pre-army if time permits):**
- D-4: Auto-detection of "this site requires Web Bot Auth" (Cloudflare 403 + Turnstile fingerprint heuristic)
- D-7: MCP discovery (`.well-known/mcp` + server-card) — trigger: SEP-1960/1649 merged OR 3 production users ask
- D-13: OpenTelemetry hook — trigger: Laminar or AgentOps user asks
- `aiohttp` adapter — trigger: 5+ users ask

**Defer to v2+ (explicitly post-army):**
- Site-side verification SDK
- Web UI / dashboard for the directory
- KMS adapters (AWS KMS, GCP KMS, Vault)
- Paid tier (post-army, post-relocation; no Stripe in v1)
- Counter-signed policy receipts

**Hard anti-features to refuse when requested:**
- Stealth/fingerprint-spoofing — contradicts the identity thesis and risks Cloudflare partnership
- CAPTCHA solvers — wrong abstraction; Web Bot Auth bypasses bot challenges by identity, not by solving
- IP/proxy rotation — combining positive identity with rotating IPs is incoherent

### Architecture Approach

The architecture is three artifacts sharing one concept: two thin SDKs running in the user's process, and one small stateless web service. The SDK never requires the hosted directory to sign requests — an agent can publish JWKS at any HTTPS URL (GitHub Pages works). The directory is a convenience and network-effect engine, not a critical dependency.

**The canonical build sequence (all four files converge on this):**
1. `spec/test-vectors/` first — canonical JSON sign/verify vectors as the cross-language oracle
2. Python signer (pure function, no I/O) + verifier loopback → Cloudflare debug endpoint on day 3
3. Python HTTP-client adapters (httpx primary, requests secondary) → Browser Use demo
4. Policy inspector (parallel fetch, independent failure, unified `Policy` dataclass)
5. Directory backend (FastAPI + SQLite/Postgres) → full E2E registration and verification
6. TypeScript SDK (test vectors guarantee byte-equality with Python) → Stagehand demo
7. Docs site + distribution PRs

**Major components and responsibilities:**
1. SDK / Identity: Ed25519 keypair lifecycle; JWKS export; kid = base64url JWK SHA-256 thumbprint per RFC 7638
2. SDK / Signer: Pure function `sign(NormalizedRequest, Identity) -> SignatureHeaders`; no I/O; Cloudflare-safe profile as default
3. SDK / Adapter layer: Thin glue per HTTP client (~30-50 LOC each); `httpx.Auth`, `requests` transport adapter, fetch wrapper, Playwright `page.route()` handler
4. SDK / Policy Inspector: `asyncio.gather` fan-out; 3-second per-endpoint timeout; `return_exceptions=True`; unified `Policy` dataclass with `partial` flag; per-host LRU cache
5. Directory / Read API: CDN-cached JWKS serving; static JSON snapshot for disaster recovery (GitHub Pages mirror)
6. Directory / Write API: Proof-of-key-ownership challenge/response (no email, no OAuth)
7. Directory / Storage: Single Postgres/SQLite table; immutable URLs per key thumbprint

**Key patterns:**
- Signer is a pure function; adapters are thin glue (30-50 LOC per client)
- Identity is a long-lived object constructed once at process start, not a per-call decorator argument
- Inspector: parallel fetch, independent failure, one output with explicit `None` for missing endpoints
- Directory: read-through CDN cache; static JSON snapshot as disaster recovery
- No auto-rotate of keys (manual rotation with explicit overlap window)

### Critical Pitfalls

1. **Signature-Agent header malformed or absent from Signature-Input** — Cloudflare rejects silently; three failure modes: missing double-quotes (Structured Field requirement), `http://` instead of `https://`, header sent but not in signed component list. Prevention: single `set_signature_agent()` helper that validates all three. Test against Cloudflare's debug endpoint in week 1 CI.

2. **Wrong derived components in the signature** — Cloudflare does not implement all RFC 9421 derived components (`@query-param`, `@status` rejected). Ship Cloudflare-safe profile as default. Proxy/TLS-termination issues cause `@scheme=http` even on HTTPS traffic. Ship `inspect_signature_base(request)` debug function.

3. **Dependency rot during 6-month army leave** — `cryptography` CVE yanked; `httpx` major bump; `pydantic` v3 transition. Prevention: pin upper bounds aggressively, commit uv lockfile, monthly scheduled CI, Dependabot, `v1.x-frozen` branch with 12-month compatibility promise.

4. **Cloudflare verified-bot submission never completed before army leave** — Manual review takes weeks. If not approved before leaving, the headline value claim is unproven for 6+ months. Prevention: treat submission as a Phase 4/5 hard deliverable. Initiate on day 1 of Phase 4.

5. **Private Ed25519 key accidentally logged or committed** — `__repr__` of key objects; test fixtures with real keys; `0o644` file permissions. Prevention: `__repr__` returning REDACTED is non-negotiable in v1. `os.chmod(path, 0o600)` on write; refuse to load files wider than `0o600`. IETF test vectors use publicly-known keys.

6. **Russia-card hosting lockout** — Fly.io and Railway are Stripe-processed; Hetzner rejects Russian-postal-address customers. Prevention: test the actual card on Fly.io signup on day 1 before writing any code. Cloudflare Workers + D1 is the zero-billing fallback.

7. **robots.txt parser returning wrong policy** — `urllib.robotparser` edge-case bugs; SPA catch-alls serving HTML 200 for `/robots.txt`. Prevention: use `protego`; validate content-type before parsing; HTML response → explicit parse error rather than "allowed."

8. **Python/TypeScript SDK API drift** — TS SDK delegated to coding agents without mechanical parity check. Prevention: `spec/test-vectors/` JSON files are the cross-language oracle; both SDKs run against them in CI; conformance-drift GitHub Action opens an issue automatically.

---

## Implications for Roadmap

The critical path is non-negotiable: **get one signed request through Cloudflare's verifier before anything else.** The architecture, features, stack, and pitfalls all converge on the same six-phase sequence.

### Phase 0: Hosting Confirmation + Project Setup (Day 1, ~2 hours)

**Rationale:** Highest-uncertainty blocker. If Fly.io or Railway reject the Russian payment card, the directory backend needs a different host (Cloudflare Workers + D1 forces a TypeScript rewrite of the directory). Discovering this on week 4 is fatal.

**Delivers:**
- Hosting confirmed working (card tested on Fly.io signup; fallback evaluated if rejected)
- Domain registrar confirmed, auto-renewal enabled for >18 months
- Monorepo structure initialized: `spec/`, `python/`, `typescript/`, `directory/`, `docs/`
- First 3 sign/verify test vectors in `spec/test-vectors/`
- GitHub Actions skeleton: `python.yml`, `typescript.yml`, `cross-language.yml`

**Avoids:** Pitfalls 13 (payment lockout), 15 (DoS/cost overruns), hosting failure discovered late.

**Research flag:** None — pure execution.

---

### Phase 1: Python Signer + Cloudflare Conformance Gate (Week 1-2)

**Rationale:** Cryptographic root. Wrong here = every downstream feature is broken. Cloudflare debug endpoint must be hit by day 3.

**Delivers:**
- `agentpassport/identity.py`: Ed25519 keygen, load, persist (mode 0600), JWKS export, `__repr__` REDACTED
- `agentpassport/signer.py`: pure function `sign(NormalizedRequest, Identity) -> SignatureHeaders`; Cloudflare-safe default profile; expires = created+60s
- `agentpassport/verifier.py`: verify path for self-loopback and directory registration
- `spec/test-vectors/`: 5+ vectors with byte-equal CI assertions
- Cloudflare debug endpoint: CI smoke test + weekly scheduled run

**Locked decisions:**
- `signature-agent` header: Structured Field string (double-quoted) enforced by helper
- Component list: Cloudflare-safe by default; extended components are documented opt-in with warning
- Key file: written with `os.chmod(path, 0o600)`; loading refuses files wider than `0o600`

**Avoids:** Pitfalls 1 (malformed Signature-Agent), 2 (wrong components), 3 (clock skew), 4 (key logging), 5 (key path conflicts).

**Research flag:** None — Cloudflare debug endpoint is the oracle; `http-message-signatures` 2.0.1 is the implementation.

---

### Phase 2: Python HTTP-Client Adapters + First Framework Demo (Week 2-3)

**Rationale:** Signer correctness means nothing until drop-in usable in real agent framework HTTP clients.

**Delivers:**
- `adapters/httpx_auth.py`: `WebBotAuth(identity)` — 30-50 LOC wrapping signer
- `adapters/requests_adapter.py`: `requests` transport adapter
- `adapters/playwright.py`: `page.route("**/*", handler)` helper (NOT `set_extra_http_headers`)
- `examples/browser_use_demo.py`: agent fails without SDK → 3 lines → passes
- CLI skeleton: `agentid keygen`, `agentid verify --domain`

**Avoids:** Pitfall 7 (no Cloudflare verification); adapter correctness validated against phase-1 test vectors.

**Research flag:** Browser Use Playwright `Page` object accessibility for `page.route()` — MEDIUM confidence. Run a 1-hour spike on day 1 of this phase before committing to adapter design.

---

### Phase 3: Pre-flight Policy Inspector (Week 3-4)

**Rationale:** Second half of the core value. Independent of signing; can ship even if some parsers are incomplete.

**Delivers:**
- `policy/fetcher.py`: `asyncio.gather` fan-out, 3-second timeout per endpoint, `return_exceptions=True`
- `policy/parsers/robots.py`: `protego` (NOT `urllib.robotparser`); HTML-response detection → parse error
- `policy/parsers/ai_txt.py`: ai.txt v1.1.1 custom parser
- `policy/parsers/llms_txt.py`: labeled with `enforcement: "voluntary"` — not sold as access control
- `policy/cache.py`: per-host LRU (robots.txt 24h, ai.txt 1h, llms.txt 24h)
- `policy/policy.py`: frozen `Policy` dataclass with `partial`, `errors`, `can_fetch()`, `is_ai_allowed()`
- D-3: verdict engine (`policy.verdict` = `allowed|restricted|forbidden` with reasons)
- Test corpus: httpbin.org, example.com, SPA-catch-all, 403-on-robots, no-robots

**Avoids:** Pitfall 8 (robots.txt wrong policy), Pitfall 9 (llms.txt overpromise).

**Research flag:** MCP discovery (SEP-1649/1960) deferred to v1.x until SEPs merge. Build parser framework to accept it; do not block Phase 3 on MCP spec stability.

---

### Phase 4: Directory Backend + Cloudflare Submission (Week 4-5)

**Rationale:** Directory is required for third-party verification (Cloudflare, Akamai). Cloudflare submission is the longest external dependency — must be initiated on day 1 of this phase, not at the end.

**Delivers:**
- FastAPI app: challenge/response registration, agent lookup, `/.well-known/http-message-signatures-directory/{id}`
- Proof-of-key-ownership: signed challenge; no email, no OAuth
- Snapshot job → `/static/all.json` → GitHub Pages nightly mirror (disaster recovery)
- Cloudflare CDN in front of read endpoints; `Cache-Control: immutable` on `/keys/<thumbprint>`
- Per-IP rate limiting on registration (10/day); spend caps at $20/month
- Reserved-name blocklist: google, openai, anthropic, cloudflare, microsoft, meta, apple, amazon
- Deployed and E2E tested: register → sign → Cloudflare debug confirms verification passes
- Cloudflare signed-agent submission initiated (day 1 of phase, not day last)

**Avoids:** Pitfalls 7 (submission never done), 15 (DoS/cost), 16 (impersonation abuse).

**Research flag:** Cloudflare submission timeline is opaque. Start immediately; do not wait for phase completion.

---

### Phase 5: TypeScript SDK (Week 5, parallel-able with Phase 4)

**Rationale:** Mandatory for Stagehand/Browser Use TS ecosystem. Test-vector contract from Phase 1 makes safe agent delegation possible.

**Delivers:**
- `typescript/src/identity.ts`, `signer.ts`, `verifier.ts`: wraps `web-bot-auth` npm; test vectors guarantee byte-equality with Python
- `typescript/src/adapters/fetch.ts`: `createSignedFetch(identity)` wrapper
- `typescript/src/adapters/playwright.ts`: `applyTo(page)` helper
- Vitest tests consuming same `spec/test-vectors/` JSON files
- `examples/stagehand_demo.ts`
- Public API: camelCase (idiomatic TS); JSON wire format: snake_case (follows IETF draft)

**Avoids:** Pitfall 10 (Python/TS drift); test vector gate is the prevention mechanism.

**Research flag:** `web-bot-auth` npm vs. `http-message-sig` (same Cloudflare monorepo) — spike to verify which fits the wrapper design.

---

### Phase 6: Pre-Army Hardening + Launch (Week 6)

**Rationale:** For a project going unmaintained for 6+ months, this is a first-class engineering deliverable, not marketing. The project must answer "is this abandoned?" with documentation and automated systems, not with activity.

**Delivers:**
- Docs: Astro Starlight on GitHub Pages — quickstart (60s to working signed request), API reference, 3 framework recipes
- README: GIF at top; code before prose; native-English speaker review; 30-second time-to-understanding test passed
- Distribution PRs submitted to Browser Use, Stagehand, mcp-agent `examples/`
- Dependabot enabled (not Renovate — simpler, fewer PRs during absence)
- Monthly scheduled CI job ("still installs cleanly" canary)
- PyPI Trusted Publishers (OIDC); npm provenance publishing from GitHub Actions
- `v1.x-frozen` branch with 12-month compatibility promise
- `MAINTAINER_AWAY.md` at repo root with expected return date
- Daily conformance canary: GitHub Action → Cloudflare debug → opens issue + Discord alert on failure
- 2FA backup codes printed and stored with trusted person
- Domain auto-renewal confirmed >18 months; spend caps on all infra

**Avoids:** Pitfalls 11 (dependency rot), 12 (Cloudflare changes mid-leave), 14 (PyPI publishing identity), 17-19 (documentation quality and abandonment perception).

**Research flag:** None — checklist execution.

---

### Phase Ordering Rationale

Three hard constraints determine the order:

1. **Cryptographic correctness gates everything.** Signer must be byte-correct against Cloudflare's verifier before any adapter or integration is built on top. Cloudflare debug endpoint on day 3 is not optional.

2. **Directory has no value without a working SDK.** Building directory first creates pressure to couple them. SDK must work with any HTTPS-served JWKS (GitHub Pages works); directory is convenience, not infrastructure.

3. **Cloudflare verified-agent submission is the external bottleneck.** Must be initiated in Phase 4 given opaque timeline (weeks to months). Starting late = arriving at army leave without the headline value claim proven.

TypeScript SDK (Phase 5) is parallel-able with Phase 4 because the test-vector contract from Phase 1 makes safe agent delegation possible. This is the project's primary time-leverage point for the 6-week window.

### Research Flags by Phase

**Skip research (standard patterns):**
- Phase 0: Pure execution
- Phase 1: Cloudflare debug endpoint is the oracle; IETF test vectors are the spec
- Phase 3: `protego` for robots.txt is a clear choice; ai.txt spec is a small custom parser
- Phase 6: Checklist execution; no technical unknowns

**Needs a spike before committing (run in first 1-2 days of each phase):**
- Phase 2: Browser Use Playwright `Page` accessibility for `page.route()` — MEDIUM confidence
- Phase 5: `web-bot-auth` npm vs. `http-message-sig` API surface fit

**Has an external dependency requiring early start:**
- Phase 4: Cloudflare signed-agent submission — initiate on day 1, not at phase end

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core libraries verified against official docs and Context7. Hosting Russia-card availability is the only MEDIUM/LOW area — must be tested on day 1. |
| Features | HIGH | IETF and Cloudflare sources are explicit and current. "No drop-in agent-side SDK exists" claim is verifiable and confirmed. Feature scope well-bounded by PROJECT.md constraints. |
| Architecture | HIGH | RFC 9421 and Web Bot Auth draft specs are precise enough that the architecture is largely determined by the protocol. Monorepo/test-vector/pure-signer patterns are well-precedented (Stripe, AWS SDKs). |
| Pitfalls | HIGH for protocol-specific and Russia/OFAC pitfalls (primary sources); MEDIUM for OSS distribution failure modes (correlational evidence). |

**Overall confidence: HIGH**

Technical execution risk is low — the protocol is well-specified, the libraries exist, and Cloudflare's debug endpoint is a reliable conformance gate. Operational risk is moderate — Russia-card hosting and the Cloudflare submission timeline are the two areas requiring early action to avoid late-stage surprises.

### Gaps to Address

- **Hosting reality (must resolve day 1):** Fly.io and Railway Russia-card status confirmed only via actual signup test. Do not plan around either until confirmed. Have Cloudflare Workers + D1 fallback architecture thought through (forces TypeScript directory rewrite).

- **Browser Use Playwright page access (spike in Phase 2 day 1):** STACK.md rates `page.route()` interception as MEDIUM confidence for Browser Use specifically. 1-hour spike resolves before committing to adapter design.

- **Cloudflare signed-agent submission timeline (start Phase 4 day 1):** Duration is opaque. Only mitigation is starting early. If not approved before army leave, document the live demo bot status honestly.

- **ai.txt adoption and verdict accuracy:** ai.txt v1.1.1 (March 2026) has unclear adoption. Verdict engine should weight robots.txt as the authoritative access-control signal; ai.txt as supplementary.

- **`@signed` decorator API surface:** ARCHITECTURE.md notes that `@signed` as a function decorator is the wrong pattern — signing must happen at the HTTP-client boundary. Public API should be a client-construction helper or client decorator. Lock before first release — renaming breaks users.

---

## Sources

### Primary (HIGH confidence)
- [RFC 9421: HTTP Message Signatures](https://datatracker.ietf.org/doc/rfc9421/) — canonical signing spec
- [draft-meunier-web-bot-auth-architecture-05](https://datatracker.ietf.org/doc/html/draft-meunier-web-bot-auth-architecture) — Web Bot Auth profile
- [draft-meunier-http-message-signatures-directory-05](https://datatracker.ietf.org/doc/html/draft-meunier-http-message-signatures-directory-05) — JWKS directory format
- [Cloudflare Web Bot Auth docs](https://developers.cloudflare.com/bots/reference/bot-verification/web-bot-auth/) — verifier requirements, debug endpoint, submission flow
- [GitHub: cloudflare/web-bot-auth](https://github.com/cloudflare/web-bot-auth) — TS + Rust reference implementation
- [pyauth/http-message-signatures v2.0.1](https://github.com/pyauth/http-message-signatures) — canonical Python RFC 9421 impl
- [AWS Bedrock AgentCore Web Bot Auth](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-web-bot-auth.html) — second reference verifier implementation
- [FastAPI docs](https://fastapi.tiangolo.com/) — version, async patterns, TestClient
- [HTTPX Authentication docs](https://www.python-httpx.org/advanced/authentication/) — custom Auth subclass pattern
- [Astro Starlight docs](https://starlight.astro.build/) — docs framework
- [RFC 9309: Robots Exclusion Protocol](https://datatracker.ietf.org/doc/html/rfc9309) — robots.txt spec
- [ai.txt Specification v1.1.1](https://www.ai-visibility.org.uk/specifications/ai-txt/) — ai.txt spec
- [Playwright Network docs](https://playwright.dev/docs/network) — `page.route()` API

### Secondary (MEDIUM confidence)
- [Hetzner payment FAQ](https://docs.hetzner.com/accounts-panel/accounts/payment-faq/) — RU-postal-address restriction confirmed
- [Stytch Web Bot Auth implementation guide](https://stytch.com/blog/how-to-implement-web-bot-auth-signing/) — practical JS walkthrough
- [OFAC "Prohibition on Certain IT Services" determination (2024-09-12)](https://ofac.treasury.gov/) — v1 no-billing requirement
- [Scrapy protego](https://github.com/scrapy/protego) — RFC 9309 compliant robots.txt parser
- [SEP-1649](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1649) / [SEP-1960](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1960) — MCP `.well-known` discovery (unmerged, best-effort)
- [A2A Protocol Specification v0.3](https://a2a-protocol.org/latest/specification/) — agent-card discovery

### Tertiary (LOW confidence — needs validation during execution)
- Fly.io / Railway Russia-card acceptance: community reports vary; must verify via actual test
- Browser Use Playwright `Page` object accessibility for `page.route()`: confirmed for Playwright, not confirmed for Browser Use's specific browser instance in all versions

---

*Research completed: 2026-05-03*
*Ready for roadmap: yes*
