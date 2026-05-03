# Phase 2: Python Adapters & Policy Inspector - Research

**Researched:** 2026-05-03
**Domain:** Python HTTP-client adapters (`httpx`, `requests`, Playwright) wrapping the Phase-1 `wbauth.sign()` pure function + asyncio policy inspector (`robots.txt`, `ai.txt`, `llms.txt`, `.well-known/http-message-signatures-directory`) with strict verdict engine, in-process LRU cache, and `wbauth inspect` / `wbauth verify` CLI subcommands
**Confidence:** HIGH for httpx/requests/Playwright/protego/cachetools API surfaces (verified via Context7 + PyPI registry + WebFetch on official docs/datatracker), HIGH for `.well-known/http-message-signatures-directory` schema (verified against draft-meunier-...-05 directly), HIGH for ai.txt v1.1.1 grammar (verified against ai-visibility.org.uk spec), MEDIUM for llms.txt verdict semantics (informal spec — what to enforce is design-time judgment), HIGH for cachetools+TTL but MEDIUM for Cache-Control/ETag override (no off-the-shelf integration — small custom shim required)

## Summary

Phase 2 splits cleanly into two halves that share zero runtime state:

**Half A — Three HTTP-client adapters (~50 LOC each).** The Phase-1 `wbauth.sign()` function is pure: input `(NormalizedRequest, Identity, *, created, expires_after_seconds, nonce, label) -> SignatureHeaders` and a header-mutation side effect. Each adapter (1) translates the client's native request object into a `NormalizedRequest`, (2) calls `sign()`, and (3) attaches the three resulting headers (`Signature`, `Signature-Input`, `Signature-Agent`) to the outgoing request. The shapes are: an `httpx.Auth` subclass with both `sync_auth_flow` and `async_auth_flow` (single signing path, both yield the modified request once and exit); a `requests.auth.AuthBase` subclass implementing `__call__(prepared_request) -> prepared_request`; and a Playwright `page.route("**/*", handler)` registration helper that intercepts every request, signs it, and calls `route.continue_(headers=...)`. All three are stateless and hold only a reference to a long-lived `Identity`.

**Half B — Pre-flight policy inspector.** `await wbauth.inspect(url) -> SitePolicy` does a `host`-only fan-out: fire four `asyncio.gather(..., return_exceptions=True)` tasks against `https://{host}/robots.txt`, `/ai.txt`, `/llms.txt`, `/.well-known/http-message-signatures-directory`, each individually wrapped in `asyncio.wait_for(..., timeout=3.0)`. Parse each with the dedicated parser (Protego for robots.txt; custom-but-tiny parsers for the other three since the specs are small). Feed the four parsed results into a deterministic verdict engine that returns one of `"allowed" | "restricted" | "forbidden"` plus a `reasons: list[str]`. Cache by `(host, endpoint_name)` in `cachetools.TTLCache` with per-endpoint default TTLs, overridable by origin `Cache-Control: max-age=N`. CLI: `wbauth inspect <url>` calls `asyncio.run(inspect(url))` and prints either human summary or `--json`; `wbauth verify --domain <domain>` re-uses the existing `wbauth._smoke.cloudflare_debug` round-trip (Phase-1 carryover) but parameterized on a user-supplied domain.

**Primary recommendation:** Use `httpx.AsyncClient` as the HTTP fetcher inside `inspect()` (already a transitive dep, already used in `_smoke/cloudflare_debug.py`). Use `protego>=0.6.0` for robots.txt. Use `cachetools>=7.0` for the `(host, endpoint) -> parsed-result` cache, with a thin custom adapter that consults origin `Cache-Control` headers when storing. Hand-roll the three small parsers (`ai_txt_parser`, `llms_txt_parser`, `signing_directory_parser` — none warrant a library dep). Keep adapters under `wbauth/adapters/` with one public symbol per file, and policy code under `wbauth/policy/` with a flat layout (`inspector.py`, `verdict.py`, `cache.py`, `parsers/{robots,ai_txt,llms_txt,signing_directory}.py`, `policy.py`, `errors.py`).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

These decisions from Phase 1 apply to Phase 2 without re-discussion:

- **L-01: Package name `wbauth`.** All adapters under `wbauth.adapters.*`; policy under `wbauth.policy.*`; CLI binary `wbauth`.
- **L-02: Python signer is the source of truth.** All adapters delegate to `wbauth.sign(NormalizedRequest, Identity) -> SignatureHeaders` (the pure function shipped in Phase 1). No re-implementing crypto.
- **L-03: Identity construction is `Identity.load_or_generate(path, signature_agent_url=...)`.** Adapters accept an `Identity` object — not raw keys, not paths. Users construct Identity once and pass it.
- **L-04: Cloudflare research verifier (`https://http-message-signatures-example.research.cloudflare.com/`) is the live conformance oracle for `wbauth verify`.** crawltest.com is the closed verified-bot gate (Phase 3 territory once we register in Cloudflare's directory).
- **L-05: macOS uv post-sync workaround is required for local development.** `bash scripts/post-sync.sh` after `uv sync`. CI runs on Ubuntu and is not affected.

#### Adapter Architecture
- **D-12: Three adapters in v1 — httpx, requests, Playwright.** Each ≤50 LOC of glue per ADAPT-07. `aiohttp` and other clients deferred to v1.x.
- **D-13: Skip Browser Use spike — Playwright API confidence is HIGH.** `page.route("**/*", handler)` is the canonical Playwright interception API and Browser Use exposes the underlying Playwright Page object. Real verification happens in Phase 4.
- **D-14: Adapter file naming.** `wbauth/adapters/httpx_auth.py`, `wbauth/adapters/requests_adapter.py`, `wbauth/adapters/playwright.py`. Each module exports exactly one public symbol (`WebBotAuth` for httpx, `WebBotAuthAdapter` for requests, `attach_signing` for playwright). All re-exported from `wbauth.adapters` for `from wbauth.adapters import WebBotAuth, attach_signing` ergonomics.
- **D-15: Adapters are stateless.** Each adapter holds a reference to a long-lived `Identity` and constructs `NormalizedRequest` per outgoing request, calls `wbauth.sign()`, attaches headers. No caching of signatures.

#### Policy Inspector
- **D-16: Async-only API.** Public surface: `await wbauth.inspect(url) -> SitePolicy`. No `inspect_sync()` wrapper.
- **D-17: SitePolicy is a frozen dataclass.** Fields: `url`, `robots: RobotsResult | None`, `ai_txt: AiTxtResult | None`, `llms_txt: LlmsTxtResult | None`, `signing_directory: SigningDirectoryResult | None`, `verdict: Literal["allowed","restricted","forbidden"]`, `reasons: list[str]`, `partial: bool`, `errors: dict[str, Exception]`, `fetched_at: datetime`. `partial=True` if any endpoint failed. `errors` keyed by endpoint name.
- **D-18: Strict verdict philosophy.** `forbidden` only when a deterministic block is asserted (robots.txt `Disallow` for our path with our user-agent OR robots.txt unparseable). `restricted` when policy signals caution. `allowed` when no signals against and at least robots.txt was fetched cleanly. Errs on the side of caution.
- **D-19: Robots parser strictness.** Use `protego` per RESEARCH.md. HTML 200 response on `/robots.txt` raises `RobotsParseError` rather than silently returning "allowed". `404` → no robots-based restriction (allowed-by-default per RFC 9309). `403`/`5xx` raise.
- **D-20: User-Agent for robots.txt evaluation.** Default agent UA: `wbauth/0.1 (+https://github.com/...)` — Phase 5 fills in the GitHub URL once D-08 (org choice) resolves.
- **D-21: ai.txt v1.1.1 + llms.txt are advisory.** Parsed and surfaced, but `llms_txt.enforcement = "voluntary"` literal in the result. ai.txt restrictions feed verdict but never `forbidden`.

#### Caching
- **D-22: Per-host LRU cache, in-process.** `cachetools.TTLCache` (or stdlib equivalent). Defaults: robots.txt 24h, ai.txt 1h, llms.txt 24h, signing-directory 5 min. Honor origin `Cache-Control: max-age=N` and `ETag` if present (override default TTL). Cache keyed by `(host, endpoint_name)`. No external dependency.
- **D-23: Cache is per-process and resets on restart.** No persistence.

#### CLI Surface
- **D-24: `wbauth inspect <url>` output format.** Default: human-readable summary on stdout — verdict line + 3-5 key reasons + truncated raw policy details. `--json` flag: full `SitePolicy` serialized as JSON to stdout. Exit code `0` for `allowed`, `1` for `restricted`, `2` for `forbidden`, `3` for fetch error / partial. Errors to stderr.
- **D-25: `wbauth verify --domain <domain>` runs the live Cloudflare research verifier.** Generates a fresh Identity (or loads default key), signs a probe request, POSTs to verifier, prints pass/fail. Exit `0` for full pass, `1` for partial pass with warnings, `2` for verifier rejection. JSON output via `--json`.
- **D-26: CLI commands are sync entry points.** `inspect` and `verify` internally call `asyncio.run()`.

#### Testing
- **D-27: Unit tests for adapters use httpx's `MockTransport` + requests' `responses` library + Playwright's `page.route()` in test mode.** No live HTTP traffic in unit tests.
- **D-28: Policy inspector tests use a small fixture corpus** in `python/tests/fixtures/policy/`.
- **D-29: Phase 1 test vectors are reused as adapter conformance.** Adapter tests assert that headers produced via `httpx.Client(auth=WebBotAuth(...))` match the byte-equal expected headers from `spec/test-vectors/01-basic-get/expected.json` (with appropriate fixture for created/nonce). Same for requests adapter.

### Claude's Discretion

- **D-30: Internal module organization beyond what's named in D-14/D-17.** E.g., should `verdict.py` live under `wbauth/policy/` or directly under `wbauth/`? Planner picks the clean layout.
- **D-31: Exception class hierarchy beyond `RobotsParseError` (D-19).** `wbauth.policy.errors` module with whatever taxonomy the implementation needs.
- **D-32: Test assertion style and fixture loaders.** pytest idiom of choice.

### Deferred Ideas (OUT OF SCOPE)

- **`aiohttp` adapter** — `ADAPT-AIOHTTP-01`, trigger: 5+ users ask.
- **`undici` Dispatcher (TypeScript)** — `ADAPT-UNDICI-01`, Phase 4 / v1.x.
- **`inspect(url, user_agent="...")` keyword for non-default UA matching in robots.txt** — Phase 2 always uses `wbauth/0.1`.
- **MCP discovery in inspector (`.well-known/mcp` + server-card)** — `D-MCP-01`, v2 trigger: SEPs merged OR 3 production users ask.
- **A2A AgentCard discovery** — `D-A2A-01`, v2.
- **Receipts** — `D-RECEIPT-01`, v2.
- **OpenTelemetry hook** — `D-OTEL-01`, v1.x trigger: Laminar/AgentOps user asks.
- **Disk-backed cache for `inspect()`** — Phase 2 is in-process only.
- **Configurable verdict policy** — Phase 2 ships strict verdict (D-18). User-tunable rule weights deferred to v2.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ADAPT-01 | Python `httpx` adapter — `WebBotAuth(identity)` subclass of `httpx.Auth`; drop-in via `httpx.Client(auth=WebBotAuth(identity))` | §1 — `auth_flow` generator pattern, `requires_request_body = True`, `sync_auth_flow` + `async_auth_flow` shape verified via Context7/encode/httpx |
| ADAPT-02 | Python `requests` adapter — usable via `auth=` parameter | §2 — `requests.auth.AuthBase.__call__(prepared_request)` pattern verified via Context7/psf/requests; `PreparedRequest` exposes `.method`, `.url`, `.headers`, `.body` ready for `NormalizedRequest` |
| ADAPT-03 | Python Playwright integration helper — `attach_signing(page, identity)` registers `page.route("**/*", handler)` that signs outgoing requests | §3 — `page.route(url_pattern, handler)`, `route.continue_(headers={...})`, async vs sync routes; iframe coverage notes |
| ADAPT-06 | All adapters validated against shared `spec/test-vectors/` to guarantee byte-equality across languages and clients | §1, §2 — `httpx.MockTransport` + per-adapter conformance tests against existing `01-basic-get/expected.json` |
| ADAPT-07 | Each adapter file is ≤50 LOC of glue; complexity lives in the pure signer | §1–§3 each show the canonical implementation in <50 LOC |
| POLICY-01 | SDK exposes async `inspect(url) -> SitePolicy` that fans out parallel fetches | §4 — `asyncio.gather` + `wait_for` per-task pattern |
| POLICY-02 | Per-endpoint timeout 3s; partial failures isolated (`return_exceptions=True`); `SitePolicy` exposes `partial: bool` and `errors: dict[str, Exception]` | §4 — concrete pattern for per-task `wait_for(timeout=3.0)` wrapped inside `gather(..., return_exceptions=True)` |
| POLICY-03 | robots.txt parsed via `protego` (RFC 9309 compliant); HTML 200 responses on `/robots.txt` raise explicit parse error | §5.1 — Protego API + content-type / first-byte HTML detection shim |
| POLICY-04 | ai.txt v1.1.1 parser returns structured object with `[identity]`, `[permissions]`, `[restrictions]`, `[attribution]`, `[contact]`, `[content-types]` sections | §5.2 — full grammar + parser sketch verified against ai-visibility.org.uk |
| POLICY-05 | llms.txt parser returns structured object; labeled with `enforcement: "voluntary"` so it is not sold as access control | §5.3 — H1 + blockquote + H2 + link-list grammar verified against llmstxt.org |
| POLICY-06 | SDK exposes `policy.verdict` returning `"allowed" | "restricted" | "forbidden"` with `reasons: list[str]` | §6 — concrete rule table mapping each input signal to its verdict contribution |
| POLICY-07 | Per-host LRU cache respects origin `Cache-Control`/`ETag` (defaults: robots.txt 24h, ai.txt 1h, llms.txt 24h); cache is in-process, no external dependency | §7 — `cachetools.TTLCache` + custom Cache-Control parser shim |
| POLICY-08 | `inspect(url)` works without any hosted directory or external service of ours; SDK has zero hard cloud dependencies | §4 — fetch loop targets only the user-supplied origin; no wbauth.dev calls |
| CLI-01 | `wbauth keygen` already shipped (Phase 1). Phase 2 hardens for CLI consistency | §8 — keep existing impl; only doc/exit-code reconciliation |
| CLI-02 | `wbauth inspect <url>` runs the policy inspector and prints structured `SitePolicy` (`--json` machine-readable; human-readable summary by default with verdict + reasons) | §8 — argparse subcommand + `asyncio.run(inspect(url))` + dataclass serializer |
| CLI-03 | `wbauth verify --domain <domain>` runs Cloudflare's debug verifier against the user's identity | §8 — wraps existing `wbauth._smoke.cloudflare_debug.run()` parameterized on `--domain` |
| CLI-06 | All CLI commands return non-zero exit codes on failure and emit machine-readable errors to stderr | §8 — exit code matrix per D-24/D-25; stderr discipline |
</phase_requirements>

## Architectural Responsibility Map

Phase 2 sits entirely in the **client SDK tier** (the `wbauth` Python package consumed by AI agents). No backend / API tier work, no CDN work, no DB work. The only "external" surface is HTTP fetches from the inspector to user-supplied origins (no wbauth-controlled service called).

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `WebBotAuth` httpx Auth subclass | Client SDK (Python lib) | — | Pure adapter — no I/O of its own; library code consumed inside the user's process |
| `WebBotAuthAdapter` requests AuthBase | Client SDK (Python lib) | — | Same as httpx; pure adapter |
| `attach_signing(page, identity)` Playwright helper | Client SDK (Python lib) | Browser process (intercepts in-browser requests) | Helper registers a route handler inside the user's Playwright Page; the actual interception runs in the Playwright driver process |
| `await inspect(url) -> SitePolicy` | Client SDK (Python lib) | External origin servers (read-only HTTP GETs) | All fetches target the user-supplied origin's well-known endpoints; no wbauth-side service involved |
| Per-host LRU cache (`cachetools.TTLCache`) | Client SDK in-process memory | — | Per CLI/agent process; resets on restart per D-23 |
| `wbauth inspect`, `wbauth verify` CLI | Client SDK CLI entry points | External origin servers (verify hits Cloudflare research verifier) | Sync entry points wrap async machinery via `asyncio.run()` |
| Verdict engine | Pure-function (in-process) | — | Deterministic mapping from `(robots, ai_txt, llms_txt, signing_directory)` to verdict; no I/O |

**Misassignment risks to watch for during planning:**

- Do NOT push any adapter logic into the signer (`wbauth/signer.py`) — adapters wrap `sign()`, they do not extend it.
- Do NOT fetch policy endpoints inside any adapter — adapters sign requests; `inspect()` is a separate public entry point the user calls explicitly. (One could imagine "auto-inspect-on-first-request" — explicitly out of scope per D-15: adapters are stateless.)
- Do NOT introduce any wbauth-controlled HTTP service in Phase 2 — POLICY-08 mandates zero hard cloud dependencies. The directory backend is Phase 3.

## Standard Stack

### Core (new in Phase 2)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `requests` | `>=2.32,<3` (latest 2.33.1, 2026-03-30) [VERIFIED: pypi.org/project/requests/] | Adapter target for `WebBotAuthAdapter` (legacy clients) | Industry default sync HTTP lib; `AuthBase` is the canonical extension point [CITED: psf/requests/docs/user/authentication.md via Context7] |
| `playwright` | `>=1.59,<2` (latest 1.59.0, 2026-04-29) [VERIFIED: pypi.org/project/playwright/] | Adapter target for `attach_signing(page, identity)` | Industry default browser automation lib used by Browser Use, Stagehand, Skyvern [CITED: STACK.md] |
| `protego` | `>=0.6.0` (latest 0.6.0, 2026-01-29, requires Python ≥3.10) [VERIFIED: pypi.org/pypi/protego/json] | RFC 9309 robots.txt parser | Maintained by Scrapy team; the de-facto modern Python robots parser; explicitly recommended over stdlib `urllib.robotparser` per PITFALLS.md Pitfall 8 [CITED: github.com/scrapy/protego] |
| `cachetools` | `>=7.0,<8` (latest 7.1.1, 2026-05-03, Python ≥3.10) [VERIFIED: pypi.org/project/cachetools/] | In-process per-host TTL cache for inspector | Mature, dep-free, exactly the right primitive for `(key)->value+ttl`; project already uses 4.2.2 transitively, will pin upper bound [VERIFIED: cachetools.readthedocs.io] |

### Already in pyproject.toml (carry-forward, no change needed)

| Library | Pinned Range | Purpose in Phase 2 |
|---------|--------------|---------------------|
| `httpx` | `>=0.28,<0.30` | (a) Adapter target for `WebBotAuth`; (b) HTTP fetcher inside `inspect()` for the four well-known endpoints (`AsyncClient`); (c) already used in `_smoke/cloudflare_debug.py` |
| `cryptography` | `>=47,<48` | Transitive — needed by signer; no direct Phase 2 use |
| `http-message-signatures` | `>=2.0.1,<3` | Transitive — needed by signer; no direct Phase 2 use |

### Dev-only (new for Phase 2 testing)

| Library | Purpose | When to use |
|---------|---------|-------------|
| `pytest-httpx` | Mock httpx async/sync responses in unit tests; assert exact headers emitted | All inspector tests (mocks the four well-known fetches); httpx adapter tests (assert signed headers without a real server) — Critical for deterministic CI per STACK.md |
| `responses` (or `requests-mock`) | Mock requests sync responses in unit tests | Requests adapter tests — assert signed headers without a real server. `responses` is the canonical choice (used by Stripe, Salesforce, etc.); `requests-mock` is the alternative. Pick one — `responses` recommended (more idiomatic) |
| `pytest-anyio` (already declared via `anyio>=4` in dev group) | Async test runner | All inspector + httpx-async tests; FastAPI's recommended pattern per STACK.md |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `protego` for robots.txt | `urllib.robotparser` (stdlib) | Stdlib parser has documented edge-case bugs (PITFALLS Pitfall 8); does not implement Google's modern conventions. **REJECTED.** [CITED: PITFALLS.md] |
| `protego` for robots.txt | `reppy` | Wraps Google's C++ parser via Python bindings — heavier install footprint (C extension), less pure-Python-friendly for army-leave window. `protego` is pure Python with no compiled deps. **REJECTED.** |
| `cachetools.TTLCache` for cache | `functools.lru_cache` (stdlib) | No per-entry TTL; can't honor origin Cache-Control. **REJECTED.** |
| `cachetools.TTLCache` for cache | Hand-roll a dict + `time.monotonic()` reaper | ~30 LOC, zero dep — viable but reinvents what cachetools does cleanly. Discretionary; recommended to use cachetools for the explicit `TTLCache(maxsize=, ttl=)` shape but a hand-rolled `OrderedDict` LRU+TTL is acceptable if planner prefers zero new runtime deps. |
| `cachetools.TTLCache` for cache | `async-cache` / `async-lru-cache` | Async-aware decorator pattern; nice for `@cached` async funcs but overkill — we want explicit `cache.get((host, endpoint))` calls keyed on `(host, endpoint)`, not coroutine memoization. **NOT NEEDED.** |
| Hand-rolled ai.txt parser | Existing PyPI package | No mature ai.txt parsing library exists as of 2026-05-03 (spec is March 2026). Hand-roll is the only option; spec is small (~5 sections, key:value or bullet-list per section). |
| Hand-rolled llms.txt parser | `markdown-it-py` | Full markdown parser is overkill for the 4-element grammar (H1 / blockquote / H2 / link-list). Hand-roll a 30-line parser per llmstxt.org spec; faster, no dep. STACK.md mentions `mistune` but for our 4-element shape that's also overkill. |
| Hand-rolled signing-directory parser | `python-jose` | We don't need JWK validation, just `keys` array unwrapping + content-type check. Hand-roll: parse JSON, assert content-type matches `application/http-message-signatures-directory+json` (or warn), return as-is. |
| `responses` for requests mocking | `requests-mock` | Both are mature; `responses` is more idiomatic (decorator-based) and used at higher-profile shops. Either works. |

**Installation:**
```bash
cd python && uv add 'requests>=2.32,<3' 'playwright>=1.59,<2' 'protego>=0.6,<1' 'cachetools>=7,<8'
uv add --dev pytest-httpx responses
# After uv sync on macOS:
bash scripts/post-sync.sh
```

**Version verification** (run before committing pyproject.toml updates):
```bash
uv run python -c "import httpx, requests, playwright, protego, cachetools; print(httpx.__version__, requests.__version__, playwright.__version__, protego.__version__, cachetools.__version__)"
```

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│  USER-SPACE AGENT CODE (Browser Use, Stagehand, custom OpenAI Agents)   │
│                                                                         │
│  identity = Identity.load_or_generate(path, signature_agent_url=...)    │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  USE PATH A — Sign outgoing HTTP                                │    │
│  │                                                                 │    │
│  │  httpx.Client(auth=WebBotAuth(identity)).get(url)               │    │
│  │       │                                                         │    │
│  │       ▼  (httpx calls Auth.auth_flow per request)               │    │
│  │  WebBotAuth.{sync,async}_auth_flow(request)                     │    │
│  │       │                                                         │    │
│  │       ▼ build NormalizedRequest from httpx.Request              │    │
│  │  wbauth.sign(NormalizedRequest, identity) ──► mutates headers   │    │
│  │       │                                                         │    │
│  │       ▼ yield request (now carries Sig*, Sig-Input, Sig-Agent)  │    │
│  │  httpx sends signed request to origin ──► WAF accepts           │    │
│  │                                                                 │    │
│  │  (analogous flows for requests AuthBase + Playwright route)     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  USE PATH B — Pre-flight policy                                 │    │
│  │                                                                 │    │
│  │  policy = await wbauth.inspect(url)                             │    │
│  │       │                                                         │    │
│  │       ▼  (cache lookup per (host, endpoint))                    │    │
│  │  cache hit? ──yes──► return cached SitePolicy                   │    │
│  │       │ no                                                      │    │
│  │       ▼                                                         │    │
│  │  asyncio.gather(                                                │    │
│  │     wait_for(fetch /robots.txt, 3.0),                           │    │
│  │     wait_for(fetch /ai.txt, 3.0),                               │    │
│  │     wait_for(fetch /llms.txt, 3.0),                             │    │
│  │     wait_for(fetch /.well-known/...directory, 3.0),             │    │
│  │     return_exceptions=True                                      │    │
│  │  )                                                              │    │
│  │       │                                                         │    │
│  │       ▼  one parser per endpoint                                │    │
│  │  protego.Protego.parse(robots) ──► RobotsResult                 │    │
│  │  parse_ai_txt(text)            ──► AiTxtResult                  │    │
│  │  parse_llms_txt(text)          ──► LlmsTxtResult                │    │
│  │  parse_signing_directory(json) ──► SigningDirectoryResult       │    │
│  │       │                                                         │    │
│  │       ▼  deterministic verdict engine                           │    │
│  │  compute_verdict(...) ──► (verdict, reasons[])                  │    │
│  │       │                                                         │    │
│  │       ▼  store in cache with min(default_ttl, origin_max_age)   │    │
│  │  SitePolicy(robots=..., ai_txt=..., ..., verdict=..., reasons=)│    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  USE PATH C — Shell                                             │    │
│  │                                                                 │    │
│  │  $ wbauth inspect https://example.com [--json]                  │    │
│  │  $ wbauth verify --domain example.com [--json]                  │    │
│  │  $ wbauth keygen --output ~/.config/wbauth/key.pem  (Phase 1)   │    │
│  │       │                                                         │    │
│  │       ▼  (sync entry points wrap async via asyncio.run)         │    │
│  │  argparse subcommand → asyncio.run(inspect(url) | verify(...))  │    │
│  │       │                                                         │    │
│  │       ▼  exit code per D-24/D-25                                │    │
│  │  process exit                                                   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
python/src/wbauth/
├── __init__.py            # public re-exports: + WebBotAuth, WebBotAuthAdapter,
│                          #   attach_signing, inspect, SitePolicy
├── identity.py            # (Phase 1, unchanged)
├── signer.py              # (Phase 1, unchanged)
├── normalized_request.py  # (Phase 1, unchanged)
├── _redaction.py          # (Phase 1, unchanged)
├── cli.py                 # (Phase 1) extend with `inspect` + `verify` subcommands
├── _smoke/                # (Phase 1) cloudflare_debug.py reused by `verify` subcmd
│
├── adapters/                       # NEW
│   ├── __init__.py                 # re-exports WebBotAuth, WebBotAuthAdapter, attach_signing
│   ├── httpx_auth.py               # ≤50 LOC — httpx.Auth subclass
│   ├── requests_adapter.py         # ≤50 LOC — requests.auth.AuthBase subclass
│   └── playwright.py               # ≤50 LOC — attach_signing(page, identity) helper
│
└── policy/                         # NEW
    ├── __init__.py                 # re-exports inspect, SitePolicy
    ├── inspector.py                # async def inspect(url) — orchestrates fetch+parse+verdict+cache
    ├── policy.py                   # SitePolicy + Robots/AiTxt/LlmsTxt/SigningDirectory result dataclasses
    ├── verdict.py                  # pure compute_verdict(...) -> (str, list[str])
    ├── cache.py                    # PolicyCache wrapper around cachetools.TTLCache
    ├── errors.py                   # RobotsParseError, FetchError, VerdictError taxonomy
    └── parsers/
        ├── __init__.py
        ├── robots.py               # protego wrapper + HTML-200 detection shim
        ├── ai_txt.py               # ai.txt v1.1.1 section parser
        ├── llms_txt.py             # llms.txt H1+blockquote+H2+link-list parser
        └── signing_directory.py    # JWKS unmarshal + content-type check

python/tests/
├── conftest.py                                  # (Phase 1) extend if shared adapter fixtures emerge
├── test_adapters_httpx.py                       # NEW — assert byte-equal vs spec/test-vectors/01-basic-get
├── test_adapters_requests.py                    # NEW — assert byte-equal vs spec/test-vectors/01-basic-get
├── test_adapters_playwright.py                  # NEW — Playwright-test-mode route fixture
├── test_policy_inspector.py                     # NEW — uses pytest-httpx to mock 4 endpoints
├── test_policy_verdict.py                       # NEW — pure-function tests on verdict matrix
├── test_policy_cache.py                         # NEW — TTL expiry + Cache-Control honoring
├── test_policy_parsers_robots.py                # NEW — uses fixture corpus
├── test_policy_parsers_ai_txt.py                # NEW — uses fixture corpus
├── test_policy_parsers_llms_txt.py              # NEW — uses fixture corpus
├── test_policy_parsers_signing_directory.py     # NEW — uses fixture corpus
├── test_cli_inspect.py                          # NEW — subprocess `wbauth inspect`
├── test_cli_verify.py                           # NEW — subprocess `wbauth verify` (mock or live)
└── fixtures/policy/                             # NEW — see §9 for corpus contents
    ├── robots/{allow,disallow,html_200,malformed,403,404}.txt
    ├── ai_txt/{minimal,with_restrictions,malformed}.txt
    ├── llms_txt/{minimal,full,empty}.txt
    └── signing_directory/{present,absent,malformed}.json
```

### Pattern 1: httpx.Auth subclass with sync + async + body-required

```python
# Source: github.com/encode/httpx/blob/master/docs/advanced/authentication.md (via Context7 /encode/httpx)
import httpx


class WebBotAuth(httpx.Auth):
    """Drop-in httpx Auth that signs every request via wbauth.sign()."""

    # Tell httpx to fully read the request body before calling auth_flow
    # so we can compute content-digest + sign over a stable bytes blob.
    # Required because POST/PUT/PATCH covered components include content-digest.
    requires_request_body = True

    def __init__(self, identity):
        self._identity = identity

    def sync_auth_flow(self, request):
        self._sign(request)
        yield request

    async def async_auth_flow(self, request):
        # No I/O happens during signing, so the async path is identical.
        # httpx requires both methods to support both client classes.
        self._sign(request)
        yield request

    def _sign(self, request):
        from wbauth import sign, NormalizedRequest
        normalized = NormalizedRequest(
            method=request.method,
            url=str(request.url),
            headers=dict(request.headers),
            body=request.content if request.content else None,
        )
        sig = sign(normalized, self._identity)
        # sign() mutated `normalized.headers`; reflect the three new headers
        # back onto the actual httpx request.
        request.headers["Signature"] = sig.signature
        request.headers["Signature-Input"] = sig.signature_input
        request.headers["Signature-Agent"] = sig.signature_agent
```

**Key gotchas confirmed from Context7 docs:**
- `requires_request_body = True` — REQUIRED. Without this, `request.content` may be a streaming iterator at the time `auth_flow` runs, and content-digest computation will fail or be non-deterministic for POST/PUT/PATCH bodies.
- `auth_flow(request)` is a generator. For per-request signing (no challenge/response), yield exactly once and exit. The generator pattern is what enables 401-retry flows; we don't use that here.
- Implementing both `sync_auth_flow` AND `async_auth_flow` lets the same `WebBotAuth(...)` instance be passed to BOTH `httpx.Client(auth=...)` AND `httpx.AsyncClient(auth=...)`. **VERIFIED via Context7**: "Custom authentication classes are designed to not perform any I/O, so that they may be used with both sync and async client instances." Since `wbauth.sign()` is pure CPU (Ed25519 sign + structured-field encoding), the same code path works in both.
- `httpx.Auth` does NOT have `requires_response_body` — that flag does not exist for the inbound-only signing pattern. (Some docs mention `requires_response_body` but it's only relevant for digest-style flows that read the previous response.)

### Pattern 2: requests.auth.AuthBase subclass

```python
# Source: github.com/psf/requests/blob/main/docs/user/authentication.md (via Context7 /psf/requests)
from requests.auth import AuthBase


class WebBotAuthAdapter(AuthBase):
    """Drop-in requests Auth that signs every request via wbauth.sign().

    Use:
        session = requests.Session()
        session.get(url, auth=WebBotAuthAdapter(identity))
    """

    def __init__(self, identity):
        self._identity = identity

    def __call__(self, prepared_request):
        # PreparedRequest exposes:
        #   .method (str)            — already uppercased by requests
        #   .url (str)               — fully rendered (params + path)
        #   .headers (CaseInsensitiveDict) — mutable
        #   .body (bytes | str | None) — already encoded
        from wbauth import sign, NormalizedRequest
        body = prepared_request.body
        if isinstance(body, str):
            body = body.encode("utf-8")
        normalized = NormalizedRequest(
            method=prepared_request.method,
            url=prepared_request.url,
            headers=dict(prepared_request.headers),
            body=body,
        )
        sig = sign(normalized, self._identity)
        prepared_request.headers["Signature"] = sig.signature
        prepared_request.headers["Signature-Input"] = sig.signature_input
        prepared_request.headers["Signature-Agent"] = sig.signature_agent
        return prepared_request
```

**Key gotchas confirmed from Context7 docs:**
- `AuthBase.__call__` receives a `requests.PreparedRequest` — by the time it's called, requests has ALREADY rendered the URL (params merged), encoded the body, and built the headers dict. So all three fields needed by the canonical signing base (method, URL, body) are available — no other hook needed.
- `__call__` MUST return the (possibly modified) request. Returning `None` swallows the request.
- `AuthBase` is the right hook (NOT a transport adapter — `requests.adapters.HTTPAdapter` is for transport-layer concerns like SSL/proxies, not for auth).
- `requests` is sync-only; there is no async `auth_flow`. Users on async stacks should use httpx instead — this adapter is a legacy compatibility path per STACK.md.

### Pattern 3: Playwright `page.route("**/*", handler)` integration

```python
# Source: github.com/microsoft/playwright-python (via Context7 /microsoft/playwright-python)
# AND playwright.dev/docs/network for the route.continue_(headers=) signature

# Async (recommended — Playwright-Python is async-first; Browser Use uses async)
from playwright.async_api import Page, Route, Request


async def _async_handler(route: Route, request: Request, identity) -> None:
    from wbauth import sign, NormalizedRequest
    normalized = NormalizedRequest(
        method=request.method,
        url=request.url,
        headers=await request.all_headers(),
        # post_data_buffer is bytes | None; method-aware (None for GET)
        body=request.post_data_buffer,
    )
    sig = sign(normalized, identity)
    headers = dict(await request.all_headers())
    headers["Signature"] = sig.signature
    headers["Signature-Input"] = sig.signature_input
    headers["Signature-Agent"] = sig.signature_agent
    await route.continue_(headers=headers)


async def attach_signing(page: Page, identity) -> None:
    """Register a route handler on `page` that signs every outgoing request.

    Idempotent: calling twice on the same page registers two handlers — only
    the first wins. Caller is responsible for calling once per page.
    """
    async def handler(route, request):
        await _async_handler(route, request, identity)
    await page.route("**/*", handler)
```

**Key gotchas confirmed from Context7 + WebSearch:**
- `page.route(url_pattern, handler)` matches all outgoing HTTP requests originated by the page (navigation, XHR, fetch, image loads, etc.) BEFORE they leave the browser. Pattern `"**/*"` = match everything. [VERIFIED: playwright.dev/docs/network]
- `route.continue_(headers={...})` is the right method to forward with modified headers. `route.fulfill(...)` would mock a response; `route.abort()` would block. [VERIFIED: Context7 /microsoft/playwright-python]
- The handler signature is `async def handler(route)` OR `async def handler(route, request)` — both are accepted; the second form is cleaner because it gives direct access to the `Request` object (otherwise: `route.request`).
- **iframe coverage:** `page.route()` covers requests originated by all sub-frames within the page by default — including iframes. Service workers are a separate concern: if the target site uses Service Workers, set `serviceWorkers="block"` on the BrowserContext to ensure interception sees the requests. [VERIFIED: WebSearch on playwright iframe interception]
- **Async-only here:** the sync API (`playwright.sync_api`) also has `page.route()` but Browser Use, Stagehand, Skyvern all use async. Ship async-only for v1; if a sync user appears, the wrapper is 5 LOC.
- **What about responses?** Nothing to do — verifier responses come back through the normal HTTP path; the response carries no signature requirement on us.
- **Iframes / sub-frames:** `page.route("**/*", handler)` is registered at the Page level and DOES cover iframe-originated requests in the same browser context (verified via WebSearch — `request.frame()` and `request.frame().parentFrame()` are accessible on the intercepted Request, confirming the request path reaches the handler).

### Pattern 4: Async parallel fetch with per-task timeout + isolation

```python
# Source: docs.python.org/3/library/asyncio-task.html (asyncio.gather, asyncio.wait_for)
# AND superfastpython.com/asyncio-gather-exception/
import asyncio
import httpx


PER_ENDPOINT_TIMEOUT = 3.0  # POLICY-02


async def _fetch_one(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """One bounded fetch. Caller wraps in wait_for + gather(return_exceptions=True)."""
    return await client.get(
        url,
        follow_redirects=True,
        headers={"User-Agent": "wbauth/0.1"},  # D-20
    )


async def _fetch_all(host: str) -> dict[str, httpx.Response | Exception]:
    endpoints = {
        "robots": f"https://{host}/robots.txt",
        "ai_txt": f"https://{host}/ai.txt",
        "llms_txt": f"https://{host}/llms.txt",
        "signing_directory": f"https://{host}/.well-known/http-message-signatures-directory",
    }
    async with httpx.AsyncClient(timeout=PER_ENDPOINT_TIMEOUT) as client:
        # Per-endpoint timeout via wait_for; gather collects all (or per-endpoint exception)
        coros = [
            asyncio.wait_for(_fetch_one(client, url), timeout=PER_ENDPOINT_TIMEOUT)
            for url in endpoints.values()
        ]
        results = await asyncio.gather(*coros, return_exceptions=True)
        return dict(zip(endpoints.keys(), results, strict=True))
```

Then in the inspector:

```python
fetched = await _fetch_all(host)
errors = {k: v for k, v in fetched.items() if isinstance(v, Exception)}
partial = bool(errors)
# ... feed each non-exception value to its parser
```

**Key gotchas confirmed:**
- `asyncio.wait_for(coro, timeout)` cancels the inner coroutine on timeout — proper resource cleanup. Wrapping each task individually means a slow `/llms.txt` doesn't block fast `/robots.txt`. [VERIFIED: docs.python.org/3/library/asyncio-task]
- `asyncio.gather(..., return_exceptions=True)` collects per-task exceptions into the result list rather than propagating the first one. Combined with per-task `wait_for`, each endpoint can fail independently → `partial=True` in `SitePolicy`, others still populate. [VERIFIED: superfastpython.com]
- Setting `timeout=` on `httpx.AsyncClient(timeout=...)` is a connection-level timeout; the `wait_for` is the per-call wall-clock cap — they layer correctly (httpx handles the `httpx.TimeoutException`, `wait_for` handles overall).
- `httpx.AsyncClient` MUST be `async with`-ed so the connection pool is closed cleanly; doing it inside `_fetch_all` ensures cleanup even on exceptions.

### Anti-Patterns to Avoid

- **Caching signed headers per-URL.** Each request needs a fresh `created` timestamp + `nonce`; reusing them creates replay-attack vectors and trips Cloudflare's clock-skew check (Pitfall 3 from PITFALLS.md). Adapters MUST be stateless beyond the `Identity` reference (D-15). VERIFIED: Phase 1 signer generates a new nonce + `datetime.now(UTC)` per call.
- **Calling `inspect()` from inside an adapter (e.g., "auto-policy-check before signing").** Two unrelated subsystems; merging them entangles tests, doubles latency on every request, and removes user agency. `inspect()` is opt-in by the agent author.
- **Falling back to `urllib.robotparser` "for simplicity".** Has documented edge-case bugs and silently returns `True` on HTML-200 responses (Pitfall 8). Use `protego` only.
- **Returning `verdict="allowed"` when robots.txt failed to fetch.** D-18: when robots.txt fetch fails (5xx, timeout, HTML-200), the verdict MUST escalate to `restricted` or `forbidden`, not silently allow.
- **Adding any wbauth.dev / agentpassport.dev call inside `inspect()`.** POLICY-08: zero hard cloud dependencies. The inspector talks ONLY to user-supplied origins.
- **Using `from playwright.sync_api import sync_playwright` in the helper.** Browser Use and Stagehand both use the async API; async-only is the right v1 surface. A sync wrapper can be added later in 5 LOC if a user materializes.
- **Logging the raw `request` or `prepared_request` object inside any adapter.** Per PITFALLS.md Pitfall 4, never log full request objects (key bytes can leak via `__repr__`). Use the existing `redacted_repr` discipline established in Phase 1.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| RFC 9421 signing | A second signer for adapters | Phase-1 `wbauth.sign()` | L-02: signer is the source of truth. Adapters wrap, not extend. |
| RFC 9309 robots.txt parsing | Custom regex parser | `protego>=0.6` | Modern conventions (longest-match, `Allow:` overriding `Disallow:`, percent-decoding) have edge cases that fail silently. PITFALLS Pitfall 8. |
| HTTP request canonicalization | Per-adapter normalization helpers | The `NormalizedRequest` dataclass + Phase-1 `_components_for()` | Keep canonicalization in one place (signer's responsibility) so byte-equal vector tests stay sound. |
| Per-host HTTP cache with TTL | `OrderedDict` + manual reaper | `cachetools.TTLCache` | Mature, dep-free, exactly the right shape. (Hand-roll is acceptable per "Alternatives Considered" — but recommended path is cachetools.) |
| Async parallel fetch with per-task timeout | Manual `asyncio.create_task` + sentinel logic | `asyncio.gather(*[wait_for(c, t) for c in coros], return_exceptions=True)` | One-line stdlib idiom; cancellation semantics are well-tested. |
| HTTP fetcher inside inspector | `urllib.request` + threadpool | `httpx.AsyncClient` | Already a dep; native async; same client used in Phase-1 smoke test (consistent connection-pool semantics). |
| JSON parsing for signing directory | Custom JWK validator | `json.loads()` + key shape check | We don't VERIFY signatures inside the inspector — we just record presence + content-type for the verdict engine. JWK schema validation is the verifier's job (Phase 3). |
| Mocking httpx in tests | Local `MonkeyPatch` of `httpx.AsyncClient` | `pytest-httpx` | Idiomatic; matches the assertions style used elsewhere in the project's STACK.md. |
| Mocking requests in tests | Local `monkeypatch.setattr(requests, "get", ...)` | `responses` library | Decorator-based, idiomatic, used by Stripe/Salesforce. |
| Markdown parsing for llms.txt | Full markdown parser (`markdown-it-py`, `mistune`) | Hand-roll a 30-line line-walker | The grammar is 4 elements (H1 / blockquote / H2 / link-list-item). Bringing in a markdown lib for that is overkill and adds maintenance surface. |

**Key insight:** Phase 2 introduces ZERO new cryptographic code. All security-sensitive code (key handling, signing, REDACTED repr) was settled in Phase 1. Phase 2 is a pure orchestration + parsing + glue layer. The risk profile is correctness (does the verdict engine return the right answer for X policy combo?) not security (can the signature be forged?).

## Common Pitfalls

### Pitfall 1: HTML-200 response on /robots.txt silently parsed as "no rules → allow"

**What goes wrong:** Many sites (especially SPAs with catch-all routes) return a 200 OK HTML page for `GET /robots.txt`. A naive parser sees "200, content non-empty, no `Disallow:` directives parsed" and returns `allow_all = True`. We then advise the agent that scraping is fine, but the site never published a real policy.

**Why it happens:** `protego.Protego.parse(some_html_string)` does NOT raise — it parses the HTML as text, finds no recognizable directives, and returns a Protego instance whose `can_fetch(url, ua)` returns `True` for everything. PITFALLS.md Pitfall 8 documents this exact failure mode.

**How to avoid:**
- Before calling `Protego.parse()`, sniff the response: `Content-Type` header should start with `text/plain` (RFC 9309 mandates), or — if origins lie about content-type — the first non-whitespace byte should NOT be `<`.
- If sniffer fails, raise `RobotsParseError("HTML 200 returned for robots.txt — assume disallowed")` per D-19. The verdict engine maps this to `forbidden`.
- Add a fixture in `tests/fixtures/policy/robots/html_200.txt` containing a real SPA HTML body and assert `RobotsParseError` is raised.

**Warning signs:**
- Inspector test against `httpbin.org/html` returns `verdict="allowed"`.
- No first-byte check in `parsers/robots.py`.

### Pitfall 2: User-Agent string in robots.txt evaluation doesn't match

**What goes wrong:** Inspector reports robots.txt `Allow: /api/`, but the live request gets blocked. Cause: the `User-Agent` we sent during the policy fetch (`wbauth/0.1`) matched `User-Agent: *` rules, but the actual scraping request will be sent with a different UA (e.g., `Browser Use 0.5.0`) that matches a SPECIFIC rule with `Disallow: /api/`.

**Why it happens:** robots.txt evaluation is UA-dependent. `protego.can_fetch(url, user_agent="X")` returns different results for different UA strings.

**How to avoid:**
- D-20 locks the v1 UA at `wbauth/0.1`. Document explicitly that the inspector evaluates against this UA, NOT the agent-framework's UA.
- Add `inspect(url, *, user_agent="wbauth/0.1")` keyword in the API signature even though we won't expose it in v1; this leaves a clean upgrade path.
- In the verdict reasons list, ALWAYS include `"evaluated against User-Agent='wbauth/0.1'"` so users can see the assumption explicitly.

### Pitfall 3: `signing_directory` present + signing-required heuristic confusion

**What goes wrong:** The `.well-known/http-message-signatures-directory` is OPTIONAL per draft-meunier-...-05. Its presence does NOT directly mean "signing is required" — it means "if you want to sign, here are the keys we accept". Some sites publish the directory but still allow unsigned access. The inspector must NOT escalate to `restricted` purely on directory presence.

**Why it happens:** Misreading the spec — the directory is the verifier's published key list, not a "signed-only" gate. The actual "signing required" signal in 2026 is implicit (Cloudflare 403 + Turnstile interstitial, or an upcoming `Accept-Signature` response header).

**How to avoid:**
- Verdict engine: directory presence ALONE → `verdict="allowed"` (not `restricted`). We surface presence in `signing_directory: SigningDirectoryResult | None` so users know they CAN sign, but we don't require it.
- Reason contribution when present: `"signing-directory published: signing supported (optional)"`.
- Reason contribution when absent: nothing (don't escalate).
- D-21 already classifies signing-required (when ai.txt or other signal is "signing required") as `restricted`, NOT `forbidden`.

**Warning signs:**
- Verdict matrix test "directory present + robots allow + ai.txt minimal" returns `restricted`. Should return `allowed`.

### Pitfall 4: `asyncio.gather` swallows the first exception

**What goes wrong:** If we call `asyncio.gather(coro1, coro2, ...)` WITHOUT `return_exceptions=True` and one fetch fails, gather raises immediately and we lose the results from coros that already completed.

**Why it happens:** Default `gather` semantics. PITFALLS.md doesn't cover this; it's an asyncio-101 trap.

**How to avoid:**
- ALWAYS pass `return_exceptions=True` per the §4 pattern. Verified via WebSearch — this is the canonical idiom.
- Test: assert that an inspector against a host where `/ai.txt` returns 500 still returns a `SitePolicy` with `robots`, `llms_txt`, and `signing_directory` populated, only `errors["ai_txt"]` set.

### Pitfall 5: Cache-Control parsing edge cases

**What goes wrong:** Origin returns `Cache-Control: no-store, no-cache, max-age=0`. Naive parser sees `max-age=0` and stores with TTL=0 — the cache is useless on every call, hammering the origin.

**Why it happens:** `Cache-Control` is a multi-token header. Any of `no-store`, `no-cache`, `private` should be honored as "do not cache".

**How to avoid:**
- Cache-Control parser must check for `no-store` / `no-cache` / `private` BEFORE parsing `max-age`. If any is present, do not cache (skip the `cache.set` call).
- If `max-age=N` is present and N > 0, use `min(N, default_ttl_for_endpoint)` as the entry TTL.
- If no `max-age`, use the default TTL.
- ETag honoring is OPTIONAL in v1 (POLICY-07 says "respects" but not "MUST do conditional requests"). Recommended scope: store the ETag in the cache entry and on cache miss-due-to-TTL-expiry, send `If-None-Match`; if origin returns 304, refresh the TTL without re-parsing.

### Pitfall 6: Playwright route handler not registered before navigation

**What goes wrong:** User does `page.goto(url)` then `attach_signing(page, identity)` — the navigation request was already sent unsigned, hits the bot challenge, fails.

**Why it happens:** `page.route()` must be registered BEFORE the navigation that should be intercepted.

**How to avoid:**
- README quickstart MUST show `await attach_signing(page, identity); await page.goto(url)` in that order.
- Add a docstring warning to `attach_signing()`: "Call BEFORE the first `page.goto()` / `page.click()` that should produce signed requests."
- Cannot detect this at runtime (no hook into "page is fresh"); document discipline is the only mitigation.

### Pitfall 7: `httpx.AsyncClient` not closed in inspector → connection-pool warning

**What goes wrong:** Inspector creates `httpx.AsyncClient()` without `async with`; on test teardown pytest emits `ResourceWarning: unclosed connection`.

**Why it happens:** httpx requires explicit close OR `async with`-ing the client.

**How to avoid:**
- ALWAYS `async with httpx.AsyncClient(...) as client:` inside `_fetch_all` per the §4 pattern.
- Add a pytest filterwarnings config to convert ResourceWarning into errors during test runs to catch regressions.

## Runtime State Inventory

> Phase 2 introduces NO long-lived runtime state beyond a per-process in-memory cache. No databases, no external services, no OS-level registrations. This section is included for completeness; all categories are explicitly empty or trivial.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — verified by `grep -r "sqlite\|redis\|postgres" python/src/` returns 0 hits in Phase 1 code, and Phase 2 introduces no persistence | None |
| Live service config | None — POLICY-08 forbids any wbauth-controlled service | None |
| OS-registered state | None — adapters and inspector run in-process; no daemons, no scheduled jobs | None |
| Secrets/env vars | The Phase-1 `~/.config/wbauth/key.pem` keyfile is consumed by `wbauth verify` to load the default Identity. No new secret introduced. | Document in CLI help that `wbauth verify` reads `~/.config/wbauth/key.pem` by default; allow override via `--identity` arg |
| Build artifacts | After adding `requests`, `playwright`, `protego`, `cachetools` deps, `uv sync` will produce new `.dist-info/` entries under `.venv/`. macOS post-sync.sh handles the UF_HIDDEN flag automatically (already extended in Phase 1 to recursive un-hide). | None — existing `scripts/post-sync.sh` covers this |
| In-process cache | `cachetools.TTLCache` instance lives in the inspector module. Per-process; resets on restart. | D-23 documents this; no migration needed |

## Code Examples

### Verified pattern: ai.txt v1.1.1 parser

```python
# Source: ai-visibility.org.uk/specifications/ai-txt/ (verified via WebFetch)
# Spec confirmed: identity uses key:value, permissions/restrictions use bullet lists,
# comments start with `#`, file is UTF-8, content-type is text/plain; charset=utf-8
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AiTxtResult:
    identity: dict[str, str]                  # {"name": "...", "url": "..."}
    permissions: list[str]                    # ["Summarise publicly available content", ...]
    restrictions: list[str]                   # ["Do not generate fake quotes", ...]
    attribution: list[str] = field(default_factory=list)
    contact: dict[str, str] = field(default_factory=dict)
    content_types: dict[str, list[str]] = field(default_factory=dict)
    raw: str = ""


_SECTION_RE = "[identity]"  # canonical section header: bracketed lowercase


def parse_ai_txt(text: str) -> AiTxtResult:
    """Parse ai.txt v1.1.1.

    Grammar:
      - Section headers are `[name]` (lowercase, bracketed) on their own line.
      - Comments start with `#`.
      - Inside [identity] / [contact]: `key: value` pairs, one per line.
      - Inside [permissions] / [restrictions] / [attribution]: bullet items
        starting with `- `.
      - Inside [content-types]: nested bullet lists per spec (treat as dict).
      - Blank lines separate sections.
    """
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].lower()
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)

    def _kv(lines):
        out = {}
        for ln in lines:
            if ":" in ln:
                k, v = ln.split(":", 1)
                out[k.strip().lower()] = v.strip()
        return out

    def _bullets(lines):
        return [ln[2:].strip() for ln in lines if ln.startswith("- ")]

    return AiTxtResult(
        identity=_kv(sections.get("identity", [])),
        permissions=_bullets(sections.get("permissions", [])),
        restrictions=_bullets(sections.get("restrictions", [])),
        attribution=_bullets(sections.get("attribution", [])),
        contact=_kv(sections.get("contact", [])),
        content_types={},  # full nested-list parser is post-v1 if needed
        raw=text,
    )
```

### Verified pattern: llms.txt parser

```python
# Source: llmstxt.org (verified via WebSearch)
# Spec confirmed: H1 (required) + blockquote (recommended) + H2 sections with
# markdown link-lists. "Optional" H2 means skippable for shorter context.
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LlmsTxtLink:
    title: str
    url: str
    notes: str = ""


@dataclass(frozen=True)
class LlmsTxtSection:
    name: str
    links: list[LlmsTxtLink]


@dataclass(frozen=True)
class LlmsTxtResult:
    title: str                                # H1, required
    description: str                          # blockquote, optional
    sections: list[LlmsTxtSection]            # H2-named link lists
    raw: str = ""
    enforcement: str = "voluntary"            # D-21: literal "voluntary" sentinel


_LINK_RE = re.compile(r"-\s*\[([^\]]+)\]\(([^)]+)\)(?::\s*(.*))?$")


def parse_llms_txt(text: str) -> LlmsTxtResult:
    title = ""
    description = ""
    sections: list[LlmsTxtSection] = []
    current = None
    in_blockquote = False
    for line in text.splitlines():
        if not title and line.startswith("# "):
            title = line[2:].strip()
            continue
        if not description and line.startswith(">"):
            description = line.lstrip("> ").strip()
            in_blockquote = True
            continue
        if line.startswith("## "):
            in_blockquote = False
            current = LlmsTxtSection(name=line[3:].strip(), links=[])
            sections.append(current)
            continue
        m = _LINK_RE.match(line.strip())
        if m and current is not None:
            current.links.append(LlmsTxtLink(
                title=m.group(1), url=m.group(2),
                notes=(m.group(3) or "").strip(),
            ))
    return LlmsTxtResult(
        title=title, description=description, sections=sections, raw=text,
    )
```

### Verified pattern: protego wrapper with HTML-200 detection

```python
# Source: github.com/scrapy/protego (verified via WebFetch)
# Spec: Protego.parse(text), can_fetch(url, user_agent), sitemaps property
from dataclasses import dataclass
from protego import Protego


@dataclass(frozen=True)
class RobotsResult:
    can_fetch_url: bool                # for our user-agent + the requested URL
    sitemaps: list[str]
    raw: str
    user_agent_evaluated: str          # always "wbauth/0.1" in v1


class RobotsParseError(Exception):
    """Raised when /robots.txt response is non-parseable (HTML 200, malformed,
    403/5xx). The verdict engine maps this to verdict="forbidden" per D-19."""


def parse_robots(text: str, content_type: str | None, target_url: str,
                 user_agent: str = "wbauth/0.1") -> RobotsResult:
    # Pitfall 1: detect HTML-200 silently parsed as "no rules → allow".
    sniff = text.lstrip()[:1]
    if sniff == "<" or (content_type and "html" in content_type.lower()):
        raise RobotsParseError(
            "robots.txt response looks like HTML — origin likely returned a "
            "catch-all SPA page; cannot evaluate; assuming disallowed"
        )
    rp = Protego.parse(text)
    return RobotsResult(
        can_fetch_url=rp.can_fetch(target_url, user_agent),
        sitemaps=list(rp.sitemaps),
        raw=text,
        user_agent_evaluated=user_agent,
    )
```

### Verified pattern: cachetools TTLCache with Cache-Control honoring

```python
# Source: cachetools.readthedocs.io (verified via WebSearch + WebFetch on PyPI)
# Source: tools.ietf.org/html/rfc7234 §5.2.2.8 (Cache-Control: max-age)
import re
from cachetools import TTLCache
from dataclasses import dataclass


# Per-endpoint default TTLs from D-22.
DEFAULT_TTLS = {
    "robots": 24 * 3600,
    "ai_txt": 1 * 3600,
    "llms_txt": 24 * 3600,
    "signing_directory": 5 * 60,
}
MAX_ENTRIES = 1024  # ~1 KB per parsed result; ~1 MB total for the whole cache


@dataclass
class CacheEntry:
    value: object
    etag: str | None = None


_MAX_AGE_RE = re.compile(r"max-age\s*=\s*(\d+)", re.IGNORECASE)


def _parse_cache_control(header: str | None) -> tuple[bool, int | None]:
    """Returns (cacheable, max_age_seconds_or_none)."""
    if not header:
        return True, None
    h = header.lower()
    if "no-store" in h or "no-cache" in h or "private" in h:
        return False, None
    m = _MAX_AGE_RE.search(h)
    if m:
        return True, int(m.group(1))
    return True, None


class PolicyCache:
    """Per-(host, endpoint) cache with origin Cache-Control honoring.

    Note: cachetools.TTLCache uses ONE TTL per cache instance, not per entry.
    To support per-entry TTL we use a separate TTLCache per endpoint type;
    each endpoint type has its own TTL bucket sized by DEFAULT_TTLS[endpoint].
    """
    def __init__(self):
        self._buckets = {
            ep: TTLCache(maxsize=MAX_ENTRIES, ttl=DEFAULT_TTLS[ep])
            for ep in DEFAULT_TTLS
        }

    def get(self, host: str, endpoint: str) -> CacheEntry | None:
        return self._buckets[endpoint].get(host)

    def set(self, host: str, endpoint: str, value: object,
            cache_control: str | None = None, etag: str | None = None) -> None:
        cacheable, max_age = _parse_cache_control(cache_control)
        if not cacheable:
            return
        # If origin sets max-age <= default, respect it; otherwise cap at default.
        # cachetools per-bucket TTL means we can't actually shorten one entry;
        # for v1 we accept this approximation: we DON'T cache when max_age=0,
        # we DO cache (at default TTL) otherwise. Sub-default TTL is a v1.x add.
        if max_age == 0:
            return
        self._buckets[endpoint][host] = CacheEntry(value=value, etag=etag)
```

**Note on the per-entry-TTL approximation:** `cachetools.TTLCache` does not support per-entry TTL. A truly faithful implementation of "honor origin `max-age=N` even when N < default TTL" requires either (a) one cache instance per (host, endpoint) — wasteful, or (b) a hand-rolled `OrderedDict` + per-entry expiry timestamp. For v1 we accept the approximation: if `max-age=0` or `no-store`, we don't cache; otherwise we cache for the default TTL. If a user reports an issue with overly long caching, switch to (b) in v1.x.

### Verified pattern: signing-directory parser (no validation)

```python
# Source: draft-meunier-http-message-signatures-directory-05 (verified via WebFetch)
# Spec: content-type "application/http-message-signatures-directory+json", JWKS shape
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class SigningDirectoryResult:
    present: bool
    keys: list[dict]                          # raw JWK objects, NOT validated
    content_type_correct: bool                # was Content-Type the spec value?
    raw: str


SPEC_CONTENT_TYPE = "application/http-message-signatures-directory+json"


def parse_signing_directory(text: str, content_type: str | None) -> SigningDirectoryResult:
    """Lightweight parse — surface presence + key count, do NOT cryptographically
    validate any signatures (verifier's job, not inspector's)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        # Treat malformed JSON as "absent" rather than raising — the verdict
        # engine doesn't care WHY it couldn't parse, just that it can't.
        return SigningDirectoryResult(
            present=False, keys=[], content_type_correct=False, raw=text,
        )
    keys = data.get("keys", [])
    return SigningDirectoryResult(
        present=bool(keys),
        keys=list(keys),
        content_type_correct=(content_type or "").startswith(SPEC_CONTENT_TYPE),
        raw=text,
    )
```

### Verified pattern: CLI subcommand wiring (extends Phase-1 cli.py)

```python
# Source: existing python/src/wbauth/cli.py (Phase 1) + Python argparse docs
# Pattern: sync entry point → asyncio.run(async_machinery)
import argparse
import asyncio
import json
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wbauth", description="...")
    sub = parser.add_subparsers(dest="cmd", required=True)
    # ... existing keygen subparser ...

    # NEW: inspect
    insp = sub.add_parser("inspect", help="Run pre-flight policy inspector against URL")
    insp.add_argument("url", help="Target URL (e.g., https://example.com)")
    insp.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    # NEW: verify
    ver = sub.add_parser("verify", help="Run Cloudflare research-verifier check")
    ver.add_argument("--domain", required=True, help="Domain to verify (e.g., example.com)")
    ver.add_argument("--identity", default=None,
                     help="Path to identity key (default: ~/.config/wbauth/key.pem)")
    ver.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.cmd == "inspect":
            from wbauth.policy import inspect, SitePolicy
            result: SitePolicy = asyncio.run(inspect(args.url))
            if args.json:
                print(json.dumps(_serialize_policy(result), default=str))
            else:
                _print_human_summary(result)
            # D-24 exit codes
            return {"allowed": 0, "restricted": 1, "forbidden": 2}.get(
                result.verdict, 3 if result.partial else 0
            )

        if args.cmd == "verify":
            from wbauth._smoke.cloudflare_debug import run_against_domain
            result = asyncio.run(run_against_domain(
                domain=args.domain, identity_path=args.identity,
            ))
            if args.json:
                print(json.dumps(result))
            return result["exit_code"]  # 0 / 1 / 2 per D-25

        # ... existing keygen handling ...
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130  # canonical SIGINT exit code
```

**Key gotchas confirmed:**
- `asyncio.run()` (Python 3.11+) handles `KeyboardInterrupt` cleanly — by default, the SIGINT process will terminate the asyncio program by calling `cancel()` on the main task. [VERIFIED: docs.python.org/3/library/asyncio-runner via WebSearch]
- Wrapping the dispatch in a `try/except KeyboardInterrupt` and returning 130 (canonical SIGINT exit code) is the clean pattern.
- Do NOT use `anyio.run` — we don't need its trio compatibility; asyncio.run is one less dep.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `urllib.robotparser` (stdlib) for robots.txt | `protego>=0.6` | Google's modernized robots.txt spec (2019); RFC 9309 (2022) | Stdlib parser does not implement modern conventions correctly; PITFALLS Pitfall 8 |
| `requests` only | `httpx` primary, `requests` adapter for legacy | httpx 0.20+ async support (2021); industry shift to async-first | We ship `requests` adapter (ADAPT-02) but document it as legacy; httpx is primary |
| Sync-only Playwright API | `playwright.async_api` is preferred | Browser Use, Stagehand, Skyvern all async | Ship async-only `attach_signing()` for v1 |
| `functools.lru_cache` for caching | `cachetools.TTLCache` for time-bounded caching | TTL needs introduced by HTTP origin Cache-Control honoring | Stdlib lacks TTL; `cachetools` is the boring, mature pick |
| `asyncio.gather(*coros)` | `asyncio.gather(*[wait_for(c, t) for c in coros], return_exceptions=True)` | Per-task timeouts + isolation needed for parallel fetch | Single-line idiom; no library needed |

**Deprecated / outdated:**
- `urllib.robotparser` for robots.txt parsing — silently returns `True` on HTML-200; do not use.
- `aiohttp` for inspector HTTP calls — perfectly viable but introduces a dep we don't need; httpx already in tree.
- `pydantic` for SitePolicy — overkill for a frozen dataclass with no validation requirements; STACK.md mentions pydantic but for this Phase, plain `@dataclass(frozen=True)` is the right pick (no Pydantic dep added in pyproject.toml).

## Validation Architecture

> Skipped per `workflow.nyquist_validation: false` in `.planning/config.json`.

## Security Domain

`security_enforcement: true` in config, `security_asvs_level: 1`. Phase 2 introduces NO new cryptographic code (signer is unchanged from Phase 1) but DOES introduce new I/O paths (HTTP fetches inside the inspector, request interception in adapters).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | N/A — we ARE the agent's identity layer; ASVS V2 is for human-user auth |
| V3 Session Management | no | No sessions in Phase 2 (per-request signing, no cookies) |
| V4 Access Control | no | No access control in Phase 2 (we're a client SDK, not a server) |
| V5 Input Validation | yes | All four parsers (robots, ai_txt, llms_txt, signing_directory) accept user-supplied origin content. Use defensive parsing (size limits, timeouts, no eval/exec). |
| V6 Cryptography | yes (carry-forward) | All crypto code is Phase-1 — `wbauth.sign()` uses `http-message-signatures` 2.0.1 + PyCA `cryptography` 47.x. Phase 2 adds zero new crypto. **NEVER hand-roll.** |
| V7 Error Handling | yes | Errors must NOT leak key material. Per Pitfall 4 in PITFALLS.md, never log full request/auth objects; use `redacted_repr()` (Phase 1 helper) for any error messages mentioning Identity. |
| V12 File Handling | partial | Adapters touch the keyfile only via Phase-1 `Identity.load_or_generate()`. Inspector touches no files. CLI `verify` reads `~/.config/wbauth/key.pem` via the same Phase-1 helper. |
| V13 API & Web Service | yes | Inspector makes outbound HTTP calls; httpx defaults are safe (TLS verification on, redirects bounded, timeouts enforced). |

### Known Threat Patterns for {Python client SDK + outbound HTTP fetcher}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malicious robots.txt with parser DoS (1 GB body, deep nesting) | DoS | Cap response body size to e.g. 1 MB per fetch (`httpx.AsyncClient(limits=...)` or read-with-limit pattern); `wait_for(timeout=3.0)` bounds time |
| Malicious ai.txt with billion-laughs-style attack | DoS | Hand-rolled parser is line-based, no recursion; bounded by line count (cap at e.g. 10k lines) |
| Server-Side Request Forgery via inspector (user passes `inspect("http://localhost:8000/admin")`) | Tampering | Inspector accepts any URL the user passes — same as `requests.get(url)`. We treat the user as trusted (this is library code, not a server). Document explicitly: "do not pass untrusted URLs to inspect()". An optional `httpx-secure` integration (mentioned in Context7 search) can be added in v1.x. |
| Logging of `Identity` object leaks key bytes | Info Disclosure | Phase-1 `redacted_repr()` already covers this. Adapter code MUST NEVER log raw `request` or `prepared_request` objects (could contain headers from prior signed requests including the Signature value, which is not secret but still noise). |
| Replay attack on signed requests | Spoofing/Tampering | Phase-1 signer already uses fresh `secrets.token_urlsafe(16)` nonce + `datetime.now(UTC)` per call; expires=created+60s. Phase 2 adapters MUST NOT cache `SignatureHeaders`. (D-15 enforces this.) |
| Cache poisoning via crafted Cache-Control header | Tampering | Cache-Control parser is regex-based, no eval; parsed integer max-age is bounded check (`if max_age == 0: skip`). No code execution path. |
| Cross-frame leak in Playwright route handler | Info Disclosure | `attach_signing(page, identity)` registers a handler at the Page level — by design covers iframes. Document: "all in-page sub-frames see the signed identity; do NOT attach if the page embeds untrusted iframes you don't want to identify on." |

### Project Constraints (from CLAUDE.md)

- **Tech stack constraint:** Python is the native-quality language; new code stays in Python. (No Phase 2 work in TypeScript — that's Phase 4.)
- **Hosting constraint:** No payment/billing surfaces touched in Phase 2 (all client-side code).
- **Maintenance constraint:** "Минимум moving parts in production" — Phase 2 adds 4 runtime deps (`requests`, `playwright`, `protego`, `cachetools`) and 2 dev deps (`pytest-httpx`, `responses`). Each is mature, low-bus-factor, and version-pinned.
- **Security constraint:** Никаких логов с private keys. Phase 2 adapter code MUST NEVER log a full `Identity` or `request` object — use `redacted_repr()` (Phase-1 helper).
- **Ethics constraint:** "Идентичность — это про честность, не про anti-detection." Adapters announce identity via `Signature-Agent` per spec; no stealth.
- **Workflow constraint (CLAUDE.md GSD section):** All file changes must go through a GSD command. Phase 2 plans + tasks must be created via `/gsd-plan-phase` per workflow enforcement.

## Test Fixture Corpus

Concrete file contents for `python/tests/fixtures/policy/`. Each fixture exercises a verdict-engine branch.

### `robots/allow.txt` — typical permissive
```
User-agent: *
Allow: /
Sitemap: https://example.com/sitemap.xml
```
Expectation: `RobotsResult(can_fetch_url=True, sitemaps=["https://example.com/sitemap.xml"], ...)`

### `robots/disallow.txt` — typical restrictive
```
User-agent: *
Disallow: /api/
Disallow: /admin/

User-agent: GPTBot
Disallow: /
```
Expectation against URL `https://example.com/api/users`, UA `wbauth/0.1`: `can_fetch_url=False`. Verdict: `forbidden`.

### `robots/html_200.txt` — SPA catch-all (Pitfall 1)
```
<!DOCTYPE html>
<html><head><title>example.com</title></head>
<body><h1>404 — page not found</h1></body></html>
```
Expectation: `parse_robots()` raises `RobotsParseError`. Inspector verdict: `forbidden`.

### `robots/malformed.txt` — random non-robots content
```
this is not a robots.txt file
just some prose with no directives
```
Expectation: `Protego.parse(...)` returns rules with no `Disallow:`; `can_fetch_url=True`. **No HTML detection trigger** — content type is text/plain, first byte is not `<`. Verdict: `allowed` (or `restricted` if other signals push it). Document this corner: "no detected directives = no robots restriction" matches RFC 9309.

### `robots/empty.txt` — empty body (some 404 fallthroughs render this way)
```

```
Expectation: `can_fetch_url=True`. RFC 9309: empty robots.txt = no restrictions.

### `ai_txt/minimal.txt`
```
[identity]
name: Example Inc
url: https://example.com

[permissions]
- Summarise publicly available content
- Cite with attribution

[restrictions]
- Do not generate fake quotes
- Do not impersonate the brand
```
Expectation: `AiTxtResult(identity={"name": "Example Inc", "url": "https://example.com"}, permissions=[...], restrictions=[...])`. Verdict contribution: `restricted` if any restriction present.

### `ai_txt/with_restrictions.txt` — heavy restrictions
```
[identity]
name: Restrictive Site

[restrictions]
- No AI training without explicit permission
- No inference of new content from this site
- No commercial use of summaries
```
Expectation: Verdict: `restricted`, reasons include "ai.txt restrictions present (3)".

### `ai_txt/malformed.txt` — random comment-only
```
# this is just a comment
# nothing else here
```
Expectation: `AiTxtResult(identity={}, permissions=[], restrictions=[], ...)`. Verdict contribution: nothing (no signals).

### `llms_txt/minimal.txt`
```
# Example Project
> A demo of llms.txt for our docs

## Docs
- [Quickstart](https://example.com/quickstart): get started in 5 minutes
- [API reference](https://example.com/api)
```
Expectation: `LlmsTxtResult(title="Example Project", description="A demo...", sections=[Section(name="Docs", links=[...2 links...])], enforcement="voluntary")`. Verdict contribution: nothing (informational).

### `llms_txt/full.txt` — multi-section
```
# Big Docs Site
> Comprehensive documentation for our platform

## Getting Started
- [Install](https://example.com/install)
- [First request](https://example.com/first): hello world

## Reference
- [API](https://example.com/api): full API surface
- [CLI](https://example.com/cli)

## Optional
- [Advanced patterns](https://example.com/advanced)
```
Expectation: 3 sections including "Optional"; the "Optional" section is preserved as a section but flagged via name.

### `llms_txt/empty.txt`
```

```
Expectation: `LlmsTxtResult(title="", description="", sections=[], enforcement="voluntary")`. Verdict contribution: nothing.

### `signing_directory/present.json`
```json
{
  "keys": [
    {
      "kty": "OKP",
      "crv": "Ed25519",
      "kid": "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U",
      "x": "JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bs",
      "use": "sig"
    }
  ]
}
```
Expectation: `SigningDirectoryResult(present=True, keys=[{...}], content_type_correct=True, raw=...)`. Verdict contribution per Pitfall 3: `"signing-directory published: signing supported (optional)"` — does NOT escalate to `restricted`.

### `signing_directory/absent.json` — represented by HTTP 404 in the fetcher
(No file content; the fetcher gets a 404, populates `errors["signing_directory"] = HTTPStatusError(...)`, and the parser is not called.)

### `signing_directory/malformed.json`
```
not json
```
Expectation: `SigningDirectoryResult(present=False, keys=[], content_type_correct=False, raw="not json")`. No exception (malformed → treat as absent per §parser).

## Verdict Engine Rule Table

Concrete rules mapping each input signal to its verdict contribution per D-18 (strict philosophy: errs on the side of caution).

| Input Signal | Verdict Contribution | Reasons String Added |
|--------------|---------------------|----------------------|
| `RobotsResult.can_fetch_url == True` | allow-leaning | `"robots.txt allows our user-agent for this path"` |
| `RobotsResult.can_fetch_url == False` | **forbidden** (terminal) | `"robots.txt disallows our user-agent for this path: <matched_rule>"` |
| `errors["robots"]` is `RobotsParseError` (HTML-200) | **forbidden** (terminal) | `"robots.txt unparseable (HTML response); assuming disallowed per strict policy"` |
| `errors["robots"]` is `httpx.TimeoutException` | **restricted** | `"robots.txt fetch timed out (3s); cannot evaluate"` |
| `errors["robots"]` is `httpx.HTTPStatusError(403/5xx)` | **restricted** | `"robots.txt fetch returned <status>; cannot evaluate"` |
| `errors["robots"]` is `httpx.HTTPStatusError(404)` | allow-leaning | `"robots.txt absent (404); no robots-based restriction per RFC 9309"` |
| `AiTxtResult.restrictions` non-empty | **restricted** | `"ai.txt restrictions present: <first restriction>... (<N> total)"` |
| `AiTxtResult.restrictions` empty + permissions present | allow-leaning | `"ai.txt permissions present, no restrictions"` |
| `errors["ai_txt"]` is `httpx.HTTPStatusError(404)` | neutral | (no reason added — ai.txt absence is normal) |
| `errors["ai_txt"]` other | neutral | (recorded in `errors`, no verdict change) |
| `LlmsTxtResult` present | neutral | `"llms.txt present (informational, enforcement=voluntary)"` |
| `LlmsTxtResult` description contains substring matching `r"\b(no\s+(automated|ai|bot)\s+access\|do\s+not\s+(scrape\|crawl))"` (case-insensitive) | **restricted** | `"llms.txt description suggests no automated access: <matched phrase>"` |
| `errors["llms_txt"]` any | neutral | (recorded in `errors`, no verdict change) |
| `SigningDirectoryResult.present == True` | allow-leaning + advisory | `"signing-directory published: signing supported (optional)"` |
| `SigningDirectoryResult.present == False` (404) | neutral | (no reason — signing not advertised by origin) |
| `errors["signing_directory"]` other | neutral | (recorded in `errors`, no verdict change) |

**Composition:**

1. If ANY rule contributes **forbidden**, final verdict = `"forbidden"` (terminal, short-circuit).
2. Else, if ANY rule contributes **restricted**, final verdict = `"restricted"`.
3. Else, if at least `robots` was fetched cleanly (or 404'd) AND no signals against, final verdict = `"allowed"`.
4. Else (no clean signals at all — all four endpoints errored non-terminally), final verdict = `"restricted"` with reason `"insufficient policy signal"`.

**Tie-break clarification re D-18 "any policy ambiguity":** the strict reading per CONTEXT.md D-18 is "no identity-related signals → `allowed` defaults to `restricted` if any policy ambiguity exists". The verdict engine implements this as: if `partial=True` (any endpoint errored non-terminally) AND verdict would otherwise be `allowed`, downgrade to `restricted` with reason `"partial policy fetch (errored: <list>); strict policy downgrades to restricted"`.

## CLI Architecture

### `wbauth inspect <url>`

```
$ wbauth inspect https://example.com
Verdict: restricted
URL:     https://example.com
Reasons:
  - robots.txt allows our user-agent for this path
  - ai.txt restrictions present: No AI training without permission... (3 total)
  - llms.txt present (informational, enforcement=voluntary)
  - signing-directory published: signing supported (optional)
Partial: false
Errors:  none
Fetched: 2026-05-03T15:30:42Z

(For full SitePolicy JSON, re-run with --json)
```

```
$ wbauth inspect https://example.com --json
{"url": "https://example.com", "verdict": "restricted", ..., "reasons": [...], ...}
```

Exit codes (D-24):
- `0` — `verdict="allowed"`
- `1` — `verdict="restricted"`
- `2` — `verdict="forbidden"`
- `3` — fetch error / `partial=True` AND verdict couldn't be computed
- `130` — Ctrl-C (canonical SIGINT)

### `wbauth verify --domain <domain>`

```
$ wbauth verify --domain example.com
Identity: ~/.config/wbauth/key.pem (kid=poqkLGiymh...)
Target:   https://http-message-signatures-example.research.cloudflare.com/
Probe:    GET /
Result:   PASS
  Status:           200
  Banner:           "You successfully authenticated as owning the test public key"
  Signed components: @authority, signature-agent
  Expiry window:    60s
  Canonicalization: OK
```

```
$ wbauth verify --domain example.com --json
{"result": "pass", "kid": "...", "status": 200, "banner": "...", ...}
```

Exit codes (D-25):
- `0` — full pass (banner matched success)
- `1` — partial pass with warnings (e.g., wrong identity loaded but spec compliant)
- `2` — verifier rejected (failure banner present, or non-200 status)
- `130` — Ctrl-C

**Note on `--domain` semantics:** the user's `--domain` argument is the domain whose policy/identity is being tested, but the actual HTTP target is the Cloudflare research verifier (per L-04). For Phase 2 the `--domain` is informational only (printed in output); Phase 3 will wire it to a domain-specific verifier path once the directory backend ships. Document this transparently in `--help`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | All Phase 2 code | ✓ | 3.13.2 (system); pinned via `.python-version` | — |
| uv | Build/dep mgmt | ✓ | 0.11.7 | — |
| pytest | All tests | (via dev deps after `uv sync`) | >=8 (declared) | — |
| `httpx` | Adapter + inspector | ✓ | 0.28.1 (already pinned) | — |
| `requests` | Adapter | (need to add) | latest 2.33.1 (verify with `uv add`) | — |
| `playwright` | Adapter | (need to add) | latest 1.59.0 | — |
| `protego` | Robots parser | (need to add) | latest 0.6.0 | — |
| `cachetools` | Inspector cache | (transitive 4.2.2; need explicit pin) | latest 7.1.1 | — |
| `pytest-httpx` | Test dep | (need to add) | latest | — |
| `responses` | Test dep | (need to add) | latest | — |
| Network access to `http-message-signatures-example.research.cloudflare.com` | `wbauth verify` live test | (CI runs daily cron — verified in Phase 1) | — | If down: skip the live test, document as known issue |
| Network access to user-supplied origin | `wbauth inspect` | runtime concern, not build-time | — | Per-endpoint timeout + `errors` dict surfaces unreachables |

**Missing dependencies with no fallback:** None blocking. All four runtime adds (`requests`, `playwright`, `protego`, `cachetools`) are mature PyPI packages.

**Missing dependencies with fallback:** None — all are required for the listed requirement IDs. Skipping any means the corresponding ADAPT-* or POLICY-* requirement cannot be satisfied.

**Note on Playwright install:** `pip install playwright` only installs the Python bindings. Browsers are installed separately via `playwright install`. For Phase 2, we DO NOT need browsers installed in CI — the Playwright adapter unit tests use Playwright's `page.route()` test mode WITHOUT launching a real browser (mock route + assert handler called). The `playwright install` step is documented in the README quickstart for users who run the demo, NOT in CI. This keeps the CI install fast and avoids macOS quirks with Playwright's bundled browsers.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `httpx.AsyncClient(timeout=3.0)` interacts cleanly with `asyncio.wait_for(timeout=3.0)` (both bounded; `wait_for` wraps the whole coro including connection-pool wait) | §4 Pattern | If httpx's internal timeout pre-empts wait_for's, we may get `httpx.TimeoutException` instead of `asyncio.TimeoutError` — verdict-mapping table needs both. Easy patch in test. |
| A2 | Browser Use's `agent.browser_session.get_current_page()` returns a `playwright.async_api.Page` (or equivalent) that `page.route()` works on | §3 Pattern | If Browser Use wraps the Page in a custom proxy that intercepts `page.route()`, we may need a Browser-Use-specific shim. **Verification deferred to Phase 4 demo per D-13.** |
| A3 | Playwright `page.route()` covers iframe-originated requests by default (no Service Worker special handling needed for the test corpus) | §3 Pattern + Pitfall 3 | If a test site uses Service Workers, route may miss requests. Mitigation documented in CONTEXT (set `serviceWorkers="block"` on context). Phase 4 demo verifies live. |
| A4 | `protego` does NOT raise on HTML input — it parses HTML as text and returns "no rules" (confirming Pitfall 8) | §5 Pattern | If a future protego release DOES raise on HTML, our explicit detection shim becomes redundant but not harmful. |
| A5 | The well-known `/.well-known/http-message-signatures-directory` URL has NO file extension and the spec mandates that exact path (no `.json` suffix) | §5 Pattern | Verified directly against draft-meunier-...-05 via WebFetch; HIGH confidence. |
| A6 | Responsive ai.txt parsers in the wild treat `[content-types]` as a nested-list block, but our v1 parser intentionally returns `content_types={}` (empty) and defers full parsing | §5 Pattern + Fixture corpus | Loss of fidelity for the `[content-types]` section. Acceptable per "minimal viable parser" spirit; can extend in v1.x if a user reports this gap. |
| A7 | `cachetools.TTLCache` does NOT support per-entry TTL (single TTL per cache instance) — verified via cachetools docs | §7 Pattern | Forces the per-bucket-per-endpoint architecture and the "cap origin max-age at default" approximation. Documented in §7 explicitly. |
| A8 | The CLI exit code mapping in D-24/D-25 is exhaustive: `0/1/2/3` for inspect, `0/1/2` for verify, `130` for Ctrl-C | §8 | If a user expects `0` for `restricted` (e.g., for shell pipelines), our exit-code semantics break their workflow. Documented in `--help`. |
| A9 | `responses` library (or `requests-mock`) integrates cleanly with the `requests` adapter for unit tests | §Standard Stack dev-only | Both are mature and widely used; LOW risk. |
| A10 | The verdict-engine "verbose phrase regex" for llms.txt restrictive substrings (`no automated access`, `do not scrape`, etc.) is sufficient for v1 | §Verdict Rule Table | False negatives possible — we'll miss novel phrasing. Acceptable per D-18 strict-leaning philosophy: when in doubt, the verdict comes from robots.txt (authoritative) and ai.txt (structured). llms.txt is informational by design. |
| A11 | The Cloudflare research verifier endpoint will continue to accept the test key vector through Phase 2 (no spec changes mid-phase) | §8 Verify CLI | Verified as of Phase 1 daily cron; if the verifier changes mid-phase, the cron will alert (Phase-1 wiring) and verify CLI behavior will need to be patched. |

**No claims in this research are tagged `[ASSUMED]` in the sense of "needs user confirmation before locking" — all decisions in CONTEXT.md are already locked. Items above are implementation-time risks the planner should be aware of.**

## Open Questions

1. **Should the inspector follow redirects on the four well-known endpoints?**
   - What we know: httpx defaults to NOT following redirects. The §4 pattern explicitly sets `follow_redirects=True`.
   - What's unclear: Some origins serve `/robots.txt` via 301 → `/robots.txt.gz` or similar; some block redirect-following on well-known endpoints.
   - Recommendation: `follow_redirects=True` with `max_redirects=3`. Document in inspector docstring.

2. **Should `wbauth inspect` evaluate robots.txt against the path component of the input URL, or against `/`?**
   - What we know: `Protego.can_fetch(url, ua)` takes a full URL; evaluating against path-of-input-url answers "can I scrape THIS URL?" while evaluating against `/` answers "is the site allow-by-default?".
   - Recommendation: evaluate against `target_url.path` (the input URL's path) — this matches the user's intent ("can I crawl THIS URL?"). Document as such.

3. **Should the cache key include the input URL path or just the host?**
   - What we know: robots.txt content is per-host, not per-path. `(host, "robots")` is the right key for the FETCH cache. The PATH-DEPENDENT verdict (`can_fetch_url` for a specific path) is computed from the cached robots content.
   - Recommendation: cache key is `(host, endpoint)` for the parsed result. The verdict engine then evaluates per-input-URL on every `inspect()` call. This keeps the cache small (one entry per host per endpoint) and correct per RFC 9309.

4. **What should `Identity.user_agent` (the optional Phase-1 field) do in adapters?**
   - What we know: Phase 1 added an optional `user_agent` field to Identity; not currently consumed anywhere.
   - Recommendation: in adapters, if `identity.user_agent` is set AND the outgoing request has no `User-Agent` header, set `request.headers["User-Agent"] = identity.user_agent`. Otherwise leave the request's existing UA alone. Surfaces a polished UX without requiring users to thread UA through twice.
   - Open: may need a new D-decision; flag for user.

5. **Should `wbauth verify` always use the test key, or default to the user's key from `~/.config/wbauth/key.pem`?**
   - What we know: D-25 says "Generates a fresh Identity (or loads default key from ~/.config/wbauth/key.pem)".
   - Reading: "or" implies user choice. The Cloudflare research verifier ONLY accepts the RFC 9421 Appendix B.1.4 test key (verified in Phase 1) — using a real user key will produce the FAILURE banner (signature doesn't validate against test public key).
   - Recommendation: in v1, `wbauth verify` ALWAYS uses `Identity.from_test_key(...)` regardless of `--identity` arg, and prints a clear note: "verify uses the test key against Cloudflare's research verifier; for verification against your own key, register your key in Cloudflare's verified-bots program (Phase 3+)." `--identity` arg is reserved for Phase 3 when we have crawltest.com integration.

6. **Should we add a `--user-agent` override to `wbauth inspect`?**
   - Per D-20 (deferred), no. v1 always uses `wbauth/0.1`. Documented as an open knob for v1.x.

## Sources

### Primary (HIGH confidence)
- Context7 `/encode/httpx` — `httpx.Auth` subclass pattern, `auth_flow`, `sync_auth_flow`, `async_auth_flow`, `requires_request_body`
- Context7 `/psf/requests` — `AuthBase.__call__(prepared_request)` pattern, `PreparedRequest` field surface
- Context7 `/microsoft/playwright-python` — `page.route()`, `route.continue_(headers=)`, async vs sync, handler signatures
- Context7 `/microsoft/playwright` — Route class API, request frame access (iframe coverage)
- IETF datatracker — [draft-meunier-http-message-signatures-directory-05](https://datatracker.ietf.org/doc/html/draft-meunier-http-message-signatures-directory-05) — well-known URL path, content-type, JWKS shape, signing-required semantics, in-band Signature-Agent header
- ai-visibility.org.uk — [ai.txt v1.1.1 specification](https://www.ai-visibility.org.uk/specifications/ai-txt/) — section grammar, content-type, advisory nature
- llmstxt.org — [llms.txt informal spec](https://llmstxt.org/) — H1 + blockquote + H2 + link-list grammar
- github.com/scrapy/protego — Protego API surface (`parse`, `can_fetch`, `sitemaps`)
- pypi.org — version + publication-date checks for `requests`, `playwright`, `protego`, `cachetools`
- docs.python.org/3/library/asyncio-task — `asyncio.gather`, `asyncio.wait_for` semantics
- docs.python.org/3/library/asyncio-runner — `asyncio.run` + KeyboardInterrupt handling in 3.11+

### Secondary (MEDIUM confidence — verified against ≥1 official source)
- superfastpython.com/asyncio-gather-exception/ — `return_exceptions=True` pattern (cross-checked vs. asyncio docs)
- cachetools.readthedocs.io — `TTLCache(maxsize, ttl)` shape (cross-checked vs. PyPI release notes)
- playwright.dev/docs/network — `page.route()` API (mirrors Context7 content)

### Tertiary (LOW confidence — informational only, no claims rest solely on these)
- Anchor Browser docs (third-party Web Bot Auth integration example)
- BrowserStack guide (Playwright network interception examples)

## Metadata

**Confidence breakdown:**
- Standard stack (httpx/requests/playwright/protego/cachetools): HIGH — all versions verified against PyPI registry within the last 24 hours; all API patterns verified against Context7 or official spec.
- Architecture (asyncio.gather pattern, dataclass shape, project layout): HIGH — patterns cross-verified against Python stdlib docs and existing Phase-1 layout.
- Pitfalls (HTML-200, UA mismatch, signing-directory misread, gather swallow, Cache-Control, Playwright registration ordering, httpx unclosed): HIGH — each pitfall has a verifier (test fixture or doc check) attached.
- Verdict engine rule table: HIGH for the rules themselves (deterministic mapping from CONTEXT.md D-18); MEDIUM for the llms.txt phrase-regex (deliberate weak signal — see Open Question 6).
- ai.txt grammar: HIGH on section structure and key:value/bullet rules; MEDIUM on `[content-types]` nested-list rendering (deferred to v1.x per Assumption A6).
- CLI exit code mapping: HIGH (matches D-24/D-25 verbatim).

**Research date:** 2026-05-03
**Valid until:** 2026-06-03 (30 days for stable libs; HTTPX, requests, Playwright are mature; verify cachetools 7.1.1 has not bumped major before pinning).
