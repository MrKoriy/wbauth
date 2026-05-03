# Phase 2: Python Adapters & Policy Inspector - Context

**Gathered:** 2026-05-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 delivers two halves of the project's "identity + policy in one import" core value end-to-end in Python: (a) HTTP-client adapters that make the Phase 1 `sign()` function drop-in usable from `httpx`, `requests`, and Playwright; (b) the pre-flight policy inspector — `await inspect(url) -> SitePolicy` with parallel-fetched robots.txt / ai.txt / llms.txt / `.well-known/http-message-signatures-directory`, deterministic verdict engine, and per-host LRU cache; plus the user-facing CLI commands `wbauth inspect <url>` and `wbauth verify --domain <domain>` (the existing `wbauth keygen` from Phase 1 is also in scope for CLI consistency hardening).

Covers v1 requirements: ADAPT-01, ADAPT-02, ADAPT-03, ADAPT-06, ADAPT-07, POLICY-01, POLICY-02, POLICY-03, POLICY-04, POLICY-05, POLICY-06, POLICY-07, POLICY-08, CLI-01, CLI-02, CLI-03, CLI-06.

</domain>

<decisions>
## Implementation Decisions

### Carrying Forward from Phase 1 (Locked)

These decisions from Phase 1 apply to Phase 2 without re-discussion:

- **L-01: Package name `wbauth`.** All adapters under `wbauth.adapters.*`; policy under `wbauth.policy.*`; CLI binary `wbauth`.
- **L-02: Python signer is the source of truth.** All adapters delegate to `wbauth.sign(NormalizedRequest, Identity) -> SignatureHeaders` (the pure function shipped in Phase 1). No re-implementing crypto.
- **L-03: Identity construction is `Identity.load_or_generate(path, signature_agent_url=...)`.** Adapters accept an `Identity` object — not raw keys, not paths. Users construct Identity once and pass it.
- **L-04: Cloudflare research verifier (`https://http-message-signatures-example.research.cloudflare.com/`) is the live conformance oracle for `wbauth verify`.** crawltest.com is the closed verified-bot gate (Phase 3 territory once we register in Cloudflare's directory).
- **L-05: macOS uv post-sync workaround is required for local development.** `bash scripts/post-sync.sh` after `uv sync`. CI runs on Ubuntu and is not affected.

### Phase 2 Implementation Decisions

#### Adapter Architecture
- **D-12: Three adapters in v1 — httpx, requests, Playwright.** Each ≤50 LOC of glue per ADAPT-07. `aiohttp` and other clients deferred to v1.x (REQUIREMENTS.md trigger: 5+ users ask). Coverage of these three reaches the dominant Python agent-framework user base (Browser Use, Skyvern, OpenAI Agents SDK).
- **D-13: Skip Browser Use spike — Playwright API confidence is HIGH.** Research confirmed `page.route("**/*", handler)` is the canonical Playwright interception API and Browser Use exposes the underlying Playwright Page object. Real verification happens in Phase 4 via `examples/browser_use_demo.py` end-to-end. If Phase 4 surfaces an actual integration gap, document and patch in Phase 4 — do not pre-spike speculatively.
- **D-14: Adapter file naming.** `wbauth/adapters/httpx_auth.py`, `wbauth/adapters/requests_adapter.py`, `wbauth/adapters/playwright.py`. Each module exports exactly one public symbol (`WebBotAuth` for httpx, `WebBotAuthAdapter` for requests, `attach_signing` for playwright). All re-exported from `wbauth.adapters` for `from wbauth.adapters import WebBotAuth, attach_signing` ergonomics.
- **D-15: Adapters are stateless.** Each adapter holds a reference to a long-lived `Identity` and constructs `NormalizedRequest` per outgoing request, calls `wbauth.sign()`, attaches headers. No caching of signatures (each request gets a fresh signature with current timestamp + nonce).

#### Policy Inspector
- **D-16: Async-only API.** Public surface: `await wbauth.inspect(url) -> SitePolicy`. No `inspect_sync()` wrapper — sync users do `asyncio.run(inspect(url))`. Reason: under the hood `inspect()` does parallel `asyncio.gather` of 4 endpoints; exposing async natively is the honest API. Exposing both creates "which is canonical?" ambiguity and doubles the test surface.
- **D-17: SitePolicy is a frozen dataclass.** Fields: `url`, `robots: RobotsResult | None`, `ai_txt: AiTxtResult | None`, `llms_txt: LlmsTxtResult | None`, `signing_directory: SigningDirectoryResult | None`, `verdict: Literal["allowed","restricted","forbidden"]`, `reasons: list[str]`, `partial: bool`, `errors: dict[str, Exception]`, `fetched_at: datetime`. `partial=True` if any endpoint failed. `errors` keyed by endpoint name.
- **D-18: Strict verdict philosophy.** `forbidden` only when a deterministic block is asserted (robots.txt `Disallow` for our path with our user-agent OR robots.txt unparseable). `restricted` when policy signals caution (ai.txt restrictions present, signing-required without identity, llms.txt suggests human-only). `allowed` when no signals against and at least robots.txt was fetched cleanly. **No identity-related signals → `allowed` defaults to `restricted` if any policy ambiguity exists.** Errs on the side of caution — matches the project's honest-identity philosophy.
- **D-19: Robots parser strictness.** Use `protego` per RESEARCH.md. HTML 200 response on `/robots.txt` (content-type `text/html` or starts with `<`) raises `RobotsParseError` rather than silently returning "allowed". `404` is treated as "no robots.txt → no robots-based restriction" (allowed-by-default per RFC 9309). `403` / `5xx` raise — uncertain about access policy.
- **D-20: User-Agent for robots.txt evaluation.** Default agent UA: `wbauth/0.1 (+https://github.com/...)` — Phase 5 fills in the GitHub URL once D-08 (org choice) resolves. For now, use the package version. Robots `User-Agent: *` matches us; specific bot UA matchers would need configuration (deferred to v1.x — `inspect(url, user_agent="...")` keyword arg planned but not exposed in v1).
- **D-21: ai.txt v1.1.1 + llms.txt are advisory.** Parsed and surfaced, but `llms_txt.enforcement = "voluntary"` literal in the result. ai.txt restrictions feed verdict (D-18) but never `forbidden`. llms.txt feeds verdict only as `restricted` if it explicitly says "no automated access" or similar.

#### Caching
- **D-22: Per-host LRU cache, in-process.** `cachetools.TTLCache` (or stdlib equivalent — choose at implementation time). Defaults per RESEARCH.md: robots.txt 24h, ai.txt 1h, llms.txt 24h, signing-directory 5 min. Honor origin `Cache-Control: max-age=N` and `ETag` if present (override default TTL). Cache keyed by `(host, endpoint_name)`. No external dependency (no Redis, no disk).
- **D-23: Cache is per-process and resets on restart.** No persistence. Acceptable for the SDK use case (agents typically run as long-lived processes; restarts are rare and re-fetching is cheap).

#### CLI Surface
- **D-24: `wbauth inspect <url>` output format.** Default: human-readable summary on stdout — verdict line + 3-5 key reasons + truncated raw policy details. `--json` flag: full `SitePolicy` serialized as JSON to stdout. Exit code `0` for `allowed`, `1` for `restricted`, `2` for `forbidden`, `3` for fetch error / partial. Errors to stderr.
- **D-25: `wbauth verify --domain <domain>` runs the live Cloudflare research verifier.** Generates a fresh Identity (or loads default key from `~/.config/wbauth/key.pem`), signs a probe request, POSTs to the verifier endpoint, prints pass/fail per criterion (canonicalization, header presence, expiry window, signed components). Exit `0` for full pass, `1` for partial pass with warnings, `2` for verifier rejection. JSON output via `--json`.
- **D-26: CLI commands are sync entry points.** `inspect` and `verify` internally call `asyncio.run()` to invoke async machinery. Users at the shell don't see asyncio.

#### Testing
- **D-27: Unit tests for adapters use httpx's `MockTransport` + requests' `responses` library + Playwright's `page.route()` in test mode.** No live HTTP traffic in unit tests (CI-flake risk). Live integration tests for `wbauth verify` against Cloudflare research verifier reuse the Phase 1 daily cron pattern.
- **D-28: Policy inspector tests use a small fixture corpus.** Hand-crafted robots.txt / ai.txt / llms.txt files in `python/tests/fixtures/policy/` covering: typical allow, typical disallow, malformed, HTML-200-on-robots, ai.txt with restrictions, llms.txt minimal. No live HTTP fetches in unit tests.
- **D-29: Phase 1 test vectors are reused as adapter conformance.** Adapter tests assert that headers produced via `httpx.Client(auth=WebBotAuth(...))` match the byte-equal expected headers from `spec/test-vectors/01-basic-get/expected.json` (with appropriate fixture for created/nonce). Same for requests adapter.

### Claude's Discretion (areas not requiring user sign-off)

- D-30: Internal module organization beyond what's named in D-14/D-17. E.g., should `verdict.py` live under `wbauth/policy/` or directly under `wbauth/`? Planner picks the clean layout.
- D-31: Exception class hierarchy beyond `RobotsParseError` (D-19). `wbauth.policy.errors` module with whatever taxonomy the implementation needs.
- D-32: Test assertion style and fixture loaders. pytest idiom of choice.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project & Requirements
- `.planning/PROJECT.md` — Core value, constraints
- `.planning/REQUIREMENTS.md` — Phase 2 v1 requirements (ADAPT-*, POLICY-*, CLI-*)
- `.planning/ROADMAP.md` — Phase 2 boundaries, success criteria

### Prior Phase
- `.planning/phases/01-foundation-cryptographic-root/01-CONTEXT.md` — D-01..D-11 (zero-billing, wbauth name, npm workspaces, Identity API)
- `.planning/phases/01-foundation-cryptographic-root/01-VERIFICATION.md` — Phase 1 audit (9/9 PASS) with sample sign() output and CLI behavior
- `.planning/phases/01-foundation-cryptographic-root/01-03-SUMMARY.md` — exact sign() output schema for Vector 01 (the deterministic baseline adapters must produce)
- `.planning/phases/01-foundation-cryptographic-root/01-04-SUMMARY.md` — test vector format, Cloudflare verifier endpoint correction (`http-message-signatures-example.research.cloudflare.com`)

### Existing Code (read these before extending)
- `python/src/wbauth/__init__.py` — current public re-exports
- `python/src/wbauth/identity.py` — Identity, KeyPair, redaction, RFC 7638 thumbprint
- `python/src/wbauth/signer.py` — pure sign() function with Web Bot Auth defaults
- `python/src/wbauth/normalized_request.py` — request normalization for the signer
- `python/src/wbauth/cli.py` — current CLI (only `keygen` subcommand; needs extension to `inspect` and `verify`)
- `python/tests/test_identity.py`, `python/tests/test_signer.py`, `python/tests/test_cli.py` — testing patterns

### Project-Level Research (still applicable)
- `.planning/research/SUMMARY.md` §3 Architecture Approach — pure-function signer, identity-as-long-lived-object
- `.planning/research/STACK.md` — `httpx` 0.28.x, `protego` for robots.txt, `cachetools` if needed
- `.planning/research/FEATURES.md` §Pre-flight Policy Inspector — TS-8 through TS-11 spec details
- `.planning/research/PITFALLS.md` Pitfalls 7 (HTML-200-on-robots), 8 (llms.txt overpromise), 9 (signing-required heuristic)

### External Specs (read directly when implementing)
- IETF RFC 9309 — Robots Exclusion Protocol (parser conformance)
- ai.txt v1.1.1 spec — section format, allowed values for [permissions], [restrictions]
- llms.txt informal spec (llmstxt.org) — H1 + blockquote + H2 + link list structure
- IETF draft-meunier-http-message-signatures-directory-05 — `.well-known/http-message-signatures-directory` discovery

### Library Docs (verify versions current at implementation time via Context7)
- `httpx` Auth subclass pattern (Authentication docs)
- `requests` transport adapter / auth pattern
- `playwright` page.route() (Network docs)
- `protego` README + RFC 9309 conformance notes
- `cachetools` TTLCache (or stdlib alternatives)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 1)
- `wbauth.sign(normalized_request, identity) -> SignatureHeaders` — pure, deterministic, byte-equal to test vectors. All adapters wrap this.
- `wbauth.NormalizedRequest` dataclass — `(method, url, headers, body_digest)` fields ready for the signer.
- `wbauth.Identity` long-lived object with `.signature_agent_url` accessor and `.kid` property — adapter inits don't need to know cryptography internals.
- `wbauth._smoke.cloudflare_debug` module — already POSTs to research verifier and parses response. `wbauth verify` CLI subcommand can wrap this as a one-shot check.
- pytest fixtures pattern in `conftest.py` — load test vectors as parametrized cases; same pattern works for policy fixtures.
- `scripts/post-sync.sh` — required after `uv sync` on macOS.

### Established Patterns
- TDD cycle (RED → GREEN → REFACTOR) with one commit per phase. Plan 2 tasks should follow this for adapters and inspector.
- Type hints + `@dataclass(frozen=True)` for value objects (Identity, KeyPair already use this — SitePolicy follows).
- Public surface re-exported from `wbauth/__init__.py`. Adapters add their public symbols there too.
- CI: `.github/workflows/python.yml` runs pytest on every push; `cloudflare-debug.yml` runs daily cron — extend to cover `wbauth verify` smoke if practical.

### Integration Points
- `wbauth.adapters.WebBotAuth` integrates with arbitrary `httpx.Client(auth=...)` instances downstream (Phase 4 examples consume).
- `wbauth.inspect()` is the public entry point Phase 4 demos call before scraping.
- `wbauth.cli` extends with `inspect` and `verify` subcommands — Phase 5 docs reference these in quickstart.

### What's NOT Yet in Code
- `python/src/wbauth/adapters/` directory (to be created)
- `python/src/wbauth/policy/` directory (to be created — will house `inspector.py`, `parsers/`, `verdict.py`, `cache.py`, `policy.py`)
- httpx/requests/playwright/protego/cachetools dependencies in `python/pyproject.toml` (need to add as runtime deps)

</code_context>

<specifics>
## Specific Ideas

- **`wbauth inspect example.com` UX vibe target:** like `curl -v` for agent policy. One verdict word, then 5 reasons that point to the actual signal. Power users add `--json` for piping. This is the "lighthouse for agents" experience the project promised.
- **Cloudflare research verifier endpoint correction (Phase 1 finding):** all references to `crawltest.com/cdn-cgi/web-bot-auth` in any plan or code MUST use `https://http-message-signatures-example.research.cloudflare.com/` instead. crawltest is for Phase 3 (after directory registration).
- **Adapter ergonomics target:** the README quickstart in Phase 5 will show `httpx.Client(auth=WebBotAuth(identity)).get("https://api.example.com/data")`. That single line must work end-to-end after Phase 2.

</specifics>

<deferred>
## Deferred Ideas

- **`aiohttp` adapter** — REQUIREMENTS.md tag `ADAPT-AIOHTTP-01`, trigger: 5+ users ask. Phase 2 ships httpx + requests + playwright only.
- **`undici` Dispatcher (TypeScript)** — REQUIREMENTS.md tag `ADAPT-UNDICI-01`, Phase 4 / v1.x.
- **`inspect(url, user_agent="...")` keyword for non-default UA matching in robots.txt** — Phase 2 always uses `wbauth/0.1`. Configurable UA deferred to v1.x.
- **MCP discovery in inspector (`.well-known/mcp` + server-card)** — REQUIREMENTS.md `D-MCP-01`, v2 trigger: SEPs merged OR 3 production users ask.
- **A2A AgentCard discovery (`/.well-known/agent-card.json`)** — REQUIREMENTS.md `D-A2A-01`, v2.
- **Receipts (signed evidence of pre-flight check)** — REQUIREMENTS.md `D-RECEIPT-01`, v2.
- **OpenTelemetry hook** — REQUIREMENTS.md `D-OTEL-01`, v1.x trigger: Laminar/AgentOps user asks.
- **Disk-backed cache for `inspect()`** — Phase 2 is in-process only. Multi-process deployments wait for v1.x.
- **Configurable verdict policy** — Phase 2 ships strict verdict (D-18). User-tunable rule weights deferred to v2 if there's demand.

</deferred>

---

*Phase: 2-Python Adapters & Policy Inspector*
*Context gathered: 2026-05-04*
