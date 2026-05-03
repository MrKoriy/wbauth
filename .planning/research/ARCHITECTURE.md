# Architecture Research

**Domain:** Agent-side identity & policy SDK + lightweight hosted directory
**Researched:** 2026-05-03
**Confidence:** HIGH for SDK and signing layer (RFC 9421, draft-meunier), MEDIUM for directory backend (greenfield decisions), MEDIUM for cross-language vector sharing.

---

## 1. System Overview

The product is three artifacts that share one concept (an "agent passport") but live in three runtime contexts. Two of them are libraries that run in the user's process; one is a tiny stateless web service. Strict separation prevents the directory from becoming a single point of failure for the SDK.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          AGENT PROCESS (user code)                       │
│                                                                          │
│   ┌────────────────────┐         ┌──────────────────────────────────┐   │
│   │  Browser Use /     │         │  Custom Playwright /             │   │
│   │  Stagehand /       │  uses   │  httpx / requests / fetch        │   │
│   │  OpenAI Agents SDK │ ──────► │  / aiohttp / axios               │   │
│   └────────┬───────────┘         └──────────────┬───────────────────┘   │
│            │                                    │                        │
│            │  imports                           │  signs each request    │
│            ▼                                    ▼                        │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              agentpassport SDK  (Python  |  TypeScript)          │   │
│   │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐    │   │
│   │  │  Identity    │ │   Signer     │ │   Policy Inspector   │    │   │
│   │  │  (keypair +  │ │  (RFC 9421)  │ │   (.well-known       │    │   │
│   │  │   directory) │ │              │ │    fan-out + cache)  │    │   │
│   │  └──────┬───────┘ └──────┬───────┘ └──────────┬───────────┘    │   │
│   │         │  HTTP-client adapters                │                │   │
│   │         │  (httpx Auth / requests TransportAdapter /            │   │
│   │         │   aiohttp middleware / fetch wrap / undici            │   │
│   │         │   Dispatcher / Playwright route hook)                 │   │
│   └─────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │ HTTPS
                ┌──────────────────┼──────────────────────────┐
                │                  │                          │
                ▼                  ▼                          ▼
   ┌──────────────────────┐ ┌──────────────────────┐ ┌─────────────────┐
   │  Target site         │ │  Target site         │ │ agentpassport.dev│
   │  (Cloudflare /       │ │  /.well-known/*      │ │  (FastAPI +      │
   │  Akamai verifies     │ │  robots.txt          │ │   Postgres)      │
   │  signature, fetches  │ │  ai.txt / llms.txt   │ │  Read: cached    │
   │  /.well-known/       │ │  mcp.json            │ │  JSON via CDN    │
   │  http-message-       │ │  agent.json          │ │  Write: API      │
   │  signatures-         │ │                      │ │  with proof of   │
   │  directory)          │ │                      │ │  key ownership   │
   └──────────────────────┘ └──────────────────────┘ └─────────────────┘
```

The SDK never *requires* the hosted directory in order to sign requests. An agent can publish its key directory at any HTTPS URL it controls (GitHub Pages, S3 bucket, its own domain). The hosted directory is convenience, not a critical dependency. This is the single most important architectural decision and follows the IETF draft model (`Signature-Agent` is a URL, not a directory ID).

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|---------------|------------------------|
| **SDK / Identity** | Manage Ed25519 keypair lifecycle (generate, load, persist, rotate). Compose JWKS for key directory. Expose key thumbprint as `kid`. | Python: `cryptography` (PyCA). TS: `@noble/curves` Ed25519. |
| **SDK / Signer** | Build RFC 9421 signature base, sign with Ed25519, attach `Signature` + `Signature-Input` + `Signature-Agent` headers. Stateless given a request and a key. | Python: pure stdlib + `cryptography`. TS: `web-bot-auth` npm package as reference, but vendored to avoid Cloudflare lock-in. |
| **SDK / Adapter layer** | Idiomatic per-client integration. Same Signer, different glue. | `httpx.Auth` subclass, `requests.adapters.HTTPAdapter`, aiohttp `ClientMiddleware`, monkey-patched `fetch`, undici interceptor, Playwright `route()` handler. |
| **SDK / Policy Inspector** | Fetch `/.well-known/{robots.txt, ai.txt, llms.txt, mcp.json, agent.json}`, parse, return one unified `Policy` object. Caches per-host with TTL. | `asyncio.gather` (Python) / `Promise.allSettled` (TS), in-memory LRU + on-disk JSON for cross-process reuse. |
| **Directory / Read API** | Serve agent records by ID or key thumbprint. Read-heavy, cache-everything. Optionally also serve as a key directory mirror. | FastAPI route → Postgres → 5-minute Cloudflare CDN cache, OR static JSON dump rebuilt on every write. |
| **Directory / Write API** | Register a new agent identity. Verify caller controls the private key (signed challenge). | FastAPI POST endpoint, signature verification with same code path the SDK uses. |
| **Directory / Storage** | Persist `(agent_id, owner_email, public_key_jwks, well_known_url, metadata, created_at)`. | Postgres (managed). Single table. |

**Boundary discipline:** the SDK never imports anything from the directory backend, and the directory backend imports the SDK *only* to reuse the signature-verification primitive. This keeps the SDK installable and useful with zero cloud dependencies.

---

## 2. Recommended Project Structure

A monorepo is the right call: the spec, test vectors, and three implementations need to evolve in lockstep, and three repos for a solo dev going on a 6-month hiatus is three things to forget how to release.

```
agentpassport/                      # GitHub root, Apache 2.0
├── spec/                           # Source of truth — language-agnostic
│   ├── README.md                   # Pointers to IETF drafts being implemented
│   ├── policy-schema.json          # JSON Schema for the Policy object
│   ├── directory-record.json       # JSON Schema for an agentpassport.dev record
│   ├── test-vectors/               # Shared cross-language correctness oracle
│   │   ├── sign/                   # {input.json, expected-signature.txt} pairs
│   │   ├── verify/                 # {request.json, jwks.json, expected: ok|fail}
│   │   └── policy-parse/           # {fixtures/site/, expected-policy.json}
│   └── examples/                   # Annotated example requests + JWKS files
│
├── python/                         # Python SDK — primary
│   ├── pyproject.toml              # Hatch or PDM, no Poetry (slower CI)
│   ├── src/agentpassport/
│   │   ├── __init__.py             # Public API: Identity, sign, inspect
│   │   ├── identity.py             # Keypair gen/load/persist, JWKS export
│   │   ├── signer.py               # RFC 9421 signature base + Ed25519 sign
│   │   ├── verifier.py             # Verification path (used by directory)
│   │   ├── policy/
│   │   │   ├── __init__.py         # inspect(url) entry point
│   │   │   ├── fetcher.py          # asyncio.gather across .well-known
│   │   │   ├── parsers/
│   │   │   │   ├── robots.py       # urllib.robotparser wrapper
│   │   │   │   ├── ai_txt.py       # ai.txt schema (custom)
│   │   │   │   ├── llms_txt.py     # markdown sitemap
│   │   │   │   ├── mcp.py          # SEP-1649 well-known/mcp.json
│   │   │   │   └── agent_json.py   # A2A Agent Card
│   │   │   ├── cache.py            # LRU + on-disk JSON, per-host TTL
│   │   │   └── policy.py           # Unified Policy dataclass
│   │   └── adapters/
│   │       ├── httpx_auth.py       # httpx.Auth subclass
│   │       ├── requests_adapter.py # requests transport adapter
│   │       └── aiohttp_mw.py       # aiohttp ClientMiddleware
│   ├── tests/
│   │   ├── test_signer.py          # Loads spec/test-vectors/sign/*
│   │   ├── test_verifier.py        # Loads spec/test-vectors/verify/*
│   │   └── test_policy.py          # Loads spec/test-vectors/policy-parse/*
│   └── examples/
│       ├── browser_use_demo.py
│       ├── playwright_openai_demo.py
│       └── plain_httpx_demo.py
│
├── typescript/                     # TS/Node SDK
│   ├── package.json                # type: module, exports map for CJS+ESM
│   ├── src/
│   │   ├── index.ts                # Public API mirroring python/__init__.py
│   │   ├── identity.ts             # @noble/curves Ed25519
│   │   ├── signer.ts               # RFC 9421 — vendored from cloudflare/web-bot-auth or thin wrapper
│   │   ├── verifier.ts
│   │   ├── policy/
│   │   │   └── ...                 # Mirror python/policy/ structure
│   │   └── adapters/
│   │       ├── fetch.ts            # createSignedFetch(identity) returns fetch-compatible
│   │       ├── undici.ts           # Undici Dispatcher interceptor
│   │       ├── axios.ts            # axios interceptor
│   │       └── playwright.ts       # page.route() helper
│   ├── tests/                      # Vitest, loads spec/test-vectors/*
│   └── examples/
│       ├── stagehand_demo.ts
│       └── browser_use_node_demo.ts
│
├── directory/                      # agentpassport.dev backend
│   ├── pyproject.toml              # Reuses python/ as a dependency for verifier.py
│   ├── src/agentpassport_dir/
│   │   ├── main.py                 # FastAPI app, ~150 LoC total
│   │   ├── models.py               # SQLAlchemy or Pydantic
│   │   ├── routes/
│   │   │   ├── register.py         # POST /v1/register (signed challenge)
│   │   │   ├── lookup.py           # GET /v1/agents/{id}
│   │   │   ├── search.py           # GET /v1/agents?owner=...
│   │   │   └── well_known.py       # GET /.well-known/http-message-signatures-directory
│   │   ├── db.py                   # asyncpg, single table
│   │   └── snapshot.py             # Periodic dump of all records to /static/all.json
│   ├── migrations/                 # Single SQL file is fine
│   ├── deploy/
│   │   ├── railway.toml
│   │   └── fly.toml
│   └── tests/
│
├── docs/                           # Astro or mkdocs-material — static site
│   ├── quickstart-python.md
│   ├── quickstart-typescript.md
│   ├── why.md
│   ├── faq.md
│   └── api-reference/
│
└── .github/
    └── workflows/
        ├── python.yml              # Run pytest, mypy, ruff
        ├── typescript.yml          # Run vitest, tsc, biome
        ├── cross-language.yml      # Run BOTH against spec/test-vectors/
        └── deploy-directory.yml    # Auto-deploy on push to main/directory/
```

### Structure Rationale

- **`spec/` at the top, not under `python/`:** signals that the spec is authoritative and language-agnostic. Test vectors live here so neither SDK can drift; cross-language CI runs both and fails the PR if either disagrees with the canonical vector.
- **`python/` and `typescript/` siblings, not nested:** treats them as peers. Avoids the trap where TS feels like a port of Python (which would make it un-idiomatic).
- **`directory/` depends on `python/`:** for the verifier code path only. This is the one cross-cut: the same code that signs in the SDK verifies in the backend, so `register` cannot accept a forged proof-of-key-ownership.
- **`docs/` static-only:** no SSR, no backend. Hosted on GitHub Pages or Cloudflare Pages. Survives indefinitely with zero maintenance.
- **No `cli/` directory:** add a `python -m agentpassport keygen` entry point inside `python/` rather than spawning a separate package. One install, one mental model.

---

## 3. Architectural Patterns

### Pattern 1: Signer is a Pure Function; Adapters are Thin Glue

**What:** Keep `signer.sign(request, identity) -> headers` as a pure function with no I/O and no client-library awareness. Each HTTP-client adapter is a 30-50 line file that (a) extracts a normalized request representation, (b) calls `signer.sign`, (c) attaches headers in the client's idiomatic way.

**When to use:** Always for this project. The reason both Stripe and AWS SDKs work across many languages is that the signing core is tiny and pure; the adapters are bulky but trivial.

**Trade-offs:** More files than a single monolithic class, but each file is easy to audit and easy to add a new client for. The cost of supporting another HTTP client (e.g., `niquests`, or a future `pyfetch`) is one file.

**Python example:**
```python
# src/agentpassport/signer.py — no I/O, no client awareness
def sign(request: NormalizedRequest, identity: Identity, *,
         created: int | None = None, expires: int | None = None,
         nonce: str | None = None) -> SignatureHeaders:
    base = build_signature_base(request, created, expires, nonce, identity.kid)
    sig = identity.private_key.sign(base.encode())
    return SignatureHeaders(
        signature=f'sig1=:{base64.b64encode(sig).decode()}:',
        signature_input=base.input_line,
        signature_agent=f'"{identity.directory_url}"',
    )

# src/agentpassport/adapters/httpx_auth.py — thin glue
class WebBotAuth(httpx.Auth):
    requires_request_body = False  # we sign headers + URL only
    def __init__(self, identity: Identity):
        self.identity = identity
    def auth_flow(self, request: httpx.Request):
        normalized = NormalizedRequest.from_httpx(request)
        headers = sign(normalized, self.identity)
        request.headers["Signature"] = headers.signature
        request.headers["Signature-Input"] = headers.signature_input
        request.headers["Signature-Agent"] = headers.signature_agent
        yield request
```

**TS example (mirrors Python intentionally):**
```typescript
// src/signer.ts — pure
export function sign(request: NormalizedRequest, identity: Identity, opts?: SignOpts): SignatureHeaders { ... }

// src/adapters/fetch.ts — thin glue
export function createSignedFetch(identity: Identity, base: typeof fetch = fetch): typeof fetch {
  return async (input, init) => {
    const req = new Request(input, init);
    const normalized = NormalizedRequest.fromFetch(req);
    const headers = sign(normalized, identity);
    req.headers.set("Signature", headers.signature);
    req.headers.set("Signature-Input", headers.signatureInput);
    req.headers.set("Signature-Agent", headers.signatureAgent);
    return base(req);
  };
}
```

### Pattern 2: Identity is a Long-Lived Object, Not a Decorator Argument

**What:** Construct `Identity` once at process start (loads or generates the keypair, validates the directory URL). Pass it to every adapter / decorator / sign call. Do not let users pass paths or PEM strings inline at every call site — that path leads to keys in logs.

**When to use:** Always.

**Trade-offs:** Slightly more setup ceremony than `@signed("./key.pem")`, but the security win (single point that touches the private key) is non-negotiable.

```python
# Setup once
identity = Identity.load_or_generate(
    keyfile="~/.agentpassport/key.json",
    directory_url="https://agentpassport.dev/.well-known/http-message-signatures-directory/abc123",
)

# Use everywhere
client = httpx.Client(auth=WebBotAuth(identity))
```

### Pattern 3: Policy Inspector — Parallel Fetch, Independent Failure, One Output

**What:** `inspect(url)` fans out to all `.well-known` endpoints concurrently, treats each as independently optional, returns a single `Policy` object where missing endpoints are explicit `None` not exceptions.

**When to use:** Always for the inspector. Sites will support 0-5 of the 6 endpoints; partial information is the normal case.

**Trade-offs:** A single hung endpoint can stall the whole call. Mitigate with strict per-fetch timeout (3 s default, configurable).

```python
async def inspect(url: str, *, cache: PolicyCache | None = None,
                  timeout: float = 3.0) -> Policy:
    host = urlparse(url).netloc
    if cache and (cached := cache.get(host)):
        return cached

    async with httpx.AsyncClient(timeout=timeout) as client:
        results = await asyncio.gather(
            fetch_robots(client, host),
            fetch_ai_txt(client, host),
            fetch_llms_txt(client, host),
            fetch_mcp(client, host),
            fetch_agent_json(client, host),
            return_exceptions=True,  # one failure does not poison the rest
        )

    policy = Policy(
        host=host,
        robots=results[0] if not isinstance(results[0], Exception) else None,
        ai_txt=results[1] if not isinstance(results[1], Exception) else None,
        llms_txt=results[2] if not isinstance(results[2], Exception) else None,
        mcp=results[3] if not isinstance(results[3], Exception) else None,
        agent_card=results[4] if not isinstance(results[4], Exception) else None,
        fetched_at=time.time(),
        partial=any(isinstance(r, Exception) for r in results),
    )
    if cache:
        cache.set(host, policy, ttl=3600)
    return policy
```

### Pattern 4: Directory as a Read-Through Cache, Not an Always-Online Dependency

**What:** The directory's read API serves from CDN-cached JSON. Even if Postgres is down, lookups continue to work for any record served in the last hour. Better: write a job that snapshots the entire directory to `/static/all.json` after each successful registration, and serve that from CDN as the canonical read path. The dynamic API becomes the write path + low-volume miss handler.

**When to use:** Always for this directory. Read traffic > write traffic by 100x.

**Trade-offs:** Eventual consistency on registration (~1 minute). Acceptable for an identity directory; nobody registers and needs verification within 60 seconds.

### Pattern 5: Proof-of-Key-Ownership for Registration

**What:** To register an agent, the caller signs a server-issued challenge with the private key they're claiming. The directory verifies the signature using the *exact same* code path it uses to verify Web Bot Auth signatures on incoming requests. No email verification, no OAuth. The cryptographic proof is the registration.

**When to use:** Always for the directory. Email verification adds a moving part (SMTP) that breaks during the army period.

**Trade-offs:** No human-readable account recovery. If the user loses their key, they register a new identity — accepted, because the whole point is the key *is* the identity.

```python
# Pseudo-flow
# 1. POST /v1/register/challenge { "kid": "abc123" }
#    -> { "nonce": "...", "expires_at": "..." }
# 2. POST /v1/register { "nonce": "...", "jwks": {...},
#                        "directory_url": "...",
#                        "owner_email_optional": "...",
#                        "signature": "...", "signature_input": "..." }
#    Server verifies signature over the entire request body, including the nonce.
#    If valid AND nonce unused AND not expired -> insert.
```

---

## 4. Data Flow

### Flow A: Sign an Outgoing Request

```
Agent calls: client.get("https://target.com/page")
    ↓
httpx prepares Request
    ↓
WebBotAuth.auth_flow(request) invoked
    ↓
NormalizedRequest.from_httpx(request)   # extracts method, URL, headers
    ↓
signer.sign(normalized, identity)       # builds RFC 9421 signature base, signs Ed25519
    ↓
Returns SignatureHeaders                 # {signature, signature_input, signature_agent}
    ↓
Headers attached to httpx.Request
    ↓
httpx sends request over the wire
    ↓
Cloudflare/Akamai/site receives, sees Signature-Agent header,
    fetches that URL → gets JWKS → verifies signature → routes as verified bot
    ↓
Response returns to agent
```

**No network call from SDK during signing.** The Signature-Agent header points at a directory; the verifier (target site) is the one that fetches it. This is critical for latency.

### Flow B: Register an Identity at agentpassport.dev

```
Agent: identity = Identity.generate()
Agent: agentpassport.directory.register(identity, owner_email="me@example.com")
    ↓ HTTPS
agentpassport.dev: POST /v1/register/challenge
    ↓
DB: INSERT challenge (nonce, expires_at)
    ↓ HTTPS
agent: receives nonce
    ↓
agent: builds registration payload, signs it with private key
    ↓ HTTPS
agentpassport.dev: POST /v1/register {payload, signature}
    ↓
verifier.verify(payload, signature, jwks)  # SAME function the SDK exposes
    ↓ if ok and nonce valid
DB: INSERT agent record
    ↓
Background task: regenerate /static/all.json snapshot
    ↓
Cloudflare CDN: serves /static/all.json (purged)
    ↓
agent: receives {agent_id, public_directory_url}
```

### Flow C: Verify an Incoming Agent (target site → directory)

This is *not* implemented by us in v1 (out of scope per PROJECT.md). But the directory must support it because Cloudflare/Akamai will hit `/.well-known/http-message-signatures-directory/{agent_id}` to fetch JWKS for verification. The directory exposes this read path; everything else is on the verifier.

```
Cloudflare/Akamai sees Signature-Agent: "https://agentpassport.dev/.well-known/.../abc123"
    ↓ HTTPS
agentpassport.dev: GET /.well-known/http-message-signatures-directory/abc123
    ↓ Cloudflare CDN cache hit (95% of cases)
    ↓ on miss → FastAPI → DB → cache
returns JWKS as application/http-message-signatures-directory+json
    ↓
Cloudflare/Akamai verifies signature locally
```

### Flow D: Pre-flight Policy Lookup

```
Agent: policy = await agentpassport.inspect("https://target.com/some/page")
    ↓
PolicyInspector: extract host = "target.com"
    ↓
Cache check (in-memory LRU + on-disk JSON keyed by host)
    ↓ miss
asyncio.gather(
    fetch /robots.txt,
    fetch /.well-known/ai.txt,
    fetch /llms.txt,           # Note: ROOT, not .well-known per Howard's spec
    fetch /.well-known/mcp.json,
    fetch /.well-known/agent.json,
    timeout=3s each, return_exceptions=True,
)
    ↓
Parse each response with its dedicated parser; failures → None
    ↓
Construct Policy(robots=..., ai_txt=..., llms_txt=..., mcp=..., agent_card=...,
                 partial=bool, fetched_at=...)
    ↓
Cache.set(host, policy, ttl=3600)
    ↓
Return Policy to agent
```

---

## 5. Hard Interface Contracts

These are the contracts that must be locked early because changing them later breaks consumers.

### 5.1 Identity / JWKS shape (agent → directory and agent → key file)

```json
{
  "keys": [
    {
      "kty": "OKP",
      "crv": "Ed25519",
      "kid": "base64url-thumbprint-per-RFC-7638",
      "x": "base64url-public-key-bytes",
      "use": "sig",
      "alg": "ed25519",
      "nbf": 1735689600,
      "exp": 1798761600
    }
  ]
}
```

Served at the agent's directory URL with `Content-Type: application/http-message-signatures-directory+json`.

### 5.2 Signature headers on outgoing requests

```
Signature-Agent: "https://agentpassport.dev/.well-known/http-message-signatures-directory/abc123"
Signature-Input: sig1=("@authority" "signature-agent");created=1735689600;expires=1735690200;keyid="abc123";alg="ed25519";nonce="...";tag="web-bot-auth"
Signature: sig1=:base64-signature:
```

The components signed are at minimum `@authority` and `signature-agent`, per the IETF draft. Tag is always `web-bot-auth`.

### 5.3 Directory Record (returned by GET /v1/agents/{id})

```json
{
  "agent_id": "abc123",
  "kid": "base64url-thumbprint",
  "directory_url": "https://agentpassport.dev/.well-known/http-message-signatures-directory/abc123",
  "owner": {
    "name_optional": "...",
    "email_hashed_optional": "sha256:..."
  },
  "metadata": {
    "framework_optional": "browser-use@0.6.2",
    "purpose_optional": "research crawler",
    "homepage_optional": "https://example.com"
  },
  "created_at": "2026-05-10T12:00:00Z",
  "revoked_at": null,
  "jwks_url": "https://agentpassport.dev/.well-known/http-message-signatures-directory/abc123"
}
```

Schema versioned at the URL prefix (`/v1/`). Never delete fields; deprecate by ignoring them.

### 5.4 Policy object (returned by inspect())

```python
@dataclass(frozen=True)
class Policy:
    host: str
    robots: RobotsRules | None         # parsed user-agent rules
    ai_txt: AiTxt | None               # AI-specific permissions
    llms_txt: LlmsTxt | None           # markdown sitemap
    mcp: McpServerCard | None          # SEP-1649 server discovery
    agent_card: AgentCard | None       # A2A agent.json
    fetched_at: float                  # unix timestamp
    partial: bool                      # True if any fetch failed
    errors: dict[str, str]             # {endpoint_name: error_message} for partials

    def can_fetch(self, user_agent: str, url: str) -> bool: ...
    def is_ai_allowed(self) -> bool: ...
    def has_mcp(self) -> bool: ...
    def rate_limit_hint(self) -> int | None: ...
```

The TS equivalent is a structurally identical interface with camelCase names. The JSON serialization (used in test vectors and as the cache format) is the source of truth; both SDKs serialize/deserialize through it.

### 5.5 Test Vector Format

Every vector under `spec/test-vectors/sign/{name}/` contains:
- `input.json` — `{request: {...}, identity: {jwks_private: {...}, directory_url: "...", created: 123, expires: 456, nonce: "..."}}`
- `expected.json` — `{signature: "...", signature_input: "...", signature_agent: "..."}`

Both SDKs run a test that loads each vector and asserts byte-equal output. This is the cross-language consistency mechanism. No subprocess, no WASM — just a JSON file as the contract.

---

## 6. Build Order

The critical path is **getting one signed request through Cloudflare's verifier**. Everything else either depends on or distributes that capability.

### Phase 1 (Week 1-2): Spec + Python signer + verifier loopback

1. `spec/` — write the JSON schemas, copy the IETF draft references, build the first 5 sign-vectors by hand using the cloudflare/web-bot-auth TS reference as oracle.
2. `python/agentpassport/identity.py` — keypair gen/load.
3. `python/agentpassport/signer.py` — RFC 9421 sign for Ed25519 only (no other algorithms).
4. `python/agentpassport/verifier.py` — verify path. Self-loopback test: sign a request, verify it, expect ok.
5. **Smoke test against Cloudflare's debug endpoint** at `https://http-message-signatures-example.research.cloudflare.com/debug` — this is the first external validation that the implementation matches the spec.

**Critical-path rationale:** if the signature is wrong here, nothing else matters. Cloudflare's debug endpoint is the cheapest external oracle. Hit it day 3.

### Phase 2 (Week 2-3): Python adapters + first integration demo

6. `python/agentpassport/adapters/httpx_auth.py` — primary adapter.
7. `python/agentpassport/adapters/requests_adapter.py`.
8. `python/agentpassport/adapters/aiohttp_mw.py`.
9. `examples/playwright_openai_demo.py` — the killer demo: agent hits a Cloudflare-protected page, fails; user adds 3 lines, agent passes. This is also the Loom video.

### Phase 3 (Week 3-4): Policy Inspector

10. `python/agentpassport/policy/` — fetcher + parsers + cache.
11. Policy works against ~10 real sites manually verified. Treat each .well-known parser as independent; ship even with 3 of 5 parsers if needed and add others later.

### Phase 4 (Week 4-5): Directory backend

12. `directory/` — FastAPI scaffold, single Postgres table, register + lookup routes.
13. Snapshot job + Cloudflare CDN in front.
14. Deploy to Railway; manual end-to-end: register an identity, sign a request with that identity's directory URL, hit Cloudflare debug, confirm verification passes.

**Why directory after SDK and not before:** the SDK must work without the directory. Building the directory first creates pressure to couple them. Build the SDK to be useful with any HTTPS-served JWKS (GitHub Pages works), then add the directory as a hosted convenience.

### Phase 5 (Week 5-6): TypeScript SDK (parallel-able with directory)

15. `typescript/` — port using `spec/test-vectors/` as the conformance gate. The test vectors guarantee byte-equality with Python. Use cloudflare/web-bot-auth npm package as a reference but vendor the signing if necessary to keep API consistent with Python.
16. TS adapters: fetch wrapper, undici interceptor, axios, Playwright.
17. `examples/stagehand_demo.ts`.

**Why TS last and parallel-able:** TS is delegated to agents per PROJECT.md constraints. The spec + test vectors make this delegation safe — even a TS implementation by a less-trusted contributor can be conformance-tested against the canonical vectors. Without that contract, the TS port becomes a permanent maintenance liability.

### Phase 6 (Week 6): Docs + landing + distribution

18. Astro docs site, GitHub Pages.
19. Landing with Loom demo.
20. PR into `examples/` of Browser Use, Stagehand, mcp-agent.

### Critical-Path Diagram

```
spec ──┬──► python.signer ──► python.verifier ──► Cloudflare debug PASS ────┐
       │         │                  │                                       │
       │         ▼                  ▼                                       │
       │   python.adapters    directory.verify (reuses python.verifier)     │
       │         │                  │                                       │
       │         ▼                  ▼                                       │
       │   demo (Browser Use)  directory deploy ──► registration E2E PASS   │
       │         │                                                          │
       └─► test-vectors ──► typescript.signer ──► typescript.verifier ──────┘
                                                          │
                                                          ▼
                                                    TS demo (Stagehand)
                                                          │
                                                          ▼
                                                    Distribution PRs
```

---

## 7. Failure Modes & Fail-Soft Behavior

Every external dependency must degrade gracefully. The SDK must never raise an exception that the user has to catch defensively for any external failure that isn't their fault.

| Failure | What breaks | SDK behavior |
|---------|------------|--------------|
| **agentpassport.dev is down** | Identity registration fails. Agents that already registered keep working (their directory URL points at the cached CDN snapshot). | New `Identity.register()` call returns `RegistrationDeferred` with retry helper. Existing `Identity.load()` works untouched. |
| **agentpassport.dev CDN snapshot stale** | Recently-registered agents may not be verifiable for ~1 minute. | Acceptable. Document the eventual consistency window. |
| **Target site does not implement Web Bot Auth** | Signature is sent but ignored. Cloudflare CAPTCHA may still trigger if the site is not in the verified-bots program. | SDK does its job (signs); upstream behavior is out of scope. Log a one-time INFO that we don't know if the site verifies. |
| **Target site `.well-known/*` returns 404** | One or more parsers see no data. | `Policy.<endpoint> = None`. `Policy.partial = False` (a missing endpoint is not a failure, it's a normal absence). |
| **Target site `.well-known/*` times out** | Inspector hangs. | Per-endpoint `timeout=3s`. On timeout, that endpoint is None and `Policy.partial = True`, `Policy.errors[endpoint] = "timeout"`. |
| **Target site `.well-known/mcp.json` returns malformed JSON** | Parser crashes. | Each parser wrapped in try/except; on parse error, `Policy.<endpoint> = None`, `Policy.errors[endpoint] = "parse_error: ..."`. |
| **Private key file unreadable / wrong permissions** | Cannot sign. | Raise `IdentityError` at `Identity.load()` time, with actionable message ("File mode is 0644, should be 0600"). Never lazy-fail at first sign. |
| **Clock skew on agent host** | `created`/`expires` timestamps wrong, verifier rejects. | Document. Optional: `Identity.set_clock_offset()` for explicit correction. Not auto-syncing — that's NTP's job. |
| **Cloudflare changes signing component requirements** | Signatures rejected by Cloudflare even though spec-compliant. | This has actually happened (Cloudflare doesn't support every RFC 9421 parameter). Test against the debug endpoint in CI weekly via a scheduled GitHub Action. Fail loudly. |
| **`@noble/curves` or `cryptography` library has a CVE** | Signing may use vulnerable crypto. | Pinned major version, weekly Dependabot, CI alerts. Solo dev cannot patch in real time during army period — accept this risk by using mature, audited libraries (PyCA cryptography, @noble/curves) where the risk is minimized. |
| **Postgres connection pool exhausted in directory** | Registration writes fail; reads still served from CDN snapshot. | Connection pool sized small (10), with explicit error response and `Retry-After`. |
| **Railway/Fly.io hosting goes down for hours** | Directory unavailable. | CDN cache covers most reads. Document GitHub Pages mirror of `/static/all.json` updated nightly via GitHub Actions. The mirror is the disaster-recovery snapshot. |

The single architectural choice that makes most of this work: **the SDK depends on no service of ours**. An agent can use this SDK with zero contact to agentpassport.dev. The directory is an opt-in convenience.

---

## 8. Optimizing for the 6+ Month Unmaintained Window

This is the architectural North Star. Every decision filtered through "will this still work if I touch nothing for 8 months?"

| Choice | Maintenance burden avoided |
|--------|---------------------------|
| FastAPI on Railway with managed Postgres | No server OS to patch, no Postgres to tune, automatic security updates. |
| Cloudflare CDN in front of all reads | Reduces backend load; if backend dies, cached records still serve. |
| Static `/static/all.json` snapshot mirrored to GitHub Pages | Disaster-recovery copy that survives even if Railway+Postgres+Cloudflare all fail simultaneously. |
| No CI/CD requiring secrets rotation | Deploy on push to main, no manual interventions. |
| No email service (no Mailgun, no SES) | One fewer credential to expire, one fewer service to fail. |
| No background job queue (no Celery, no Redis) | Snapshot job is a single FastAPI startup hook + threading.Timer; embarrassing but it survives unattended. |
| Pinned major versions only, weekly Dependabot PRs | Catches security issues; minor-version drift is fine. |
| Documentation in `docs/` as static markdown | No CMS to die, no SaaS to expire. |
| Tests run on GitHub Actions with no external deps | Won't break because some test service shut down. |
| Cross-language CI gate uses spec/test-vectors files | Works as long as Python and Node still exist. |
| No analytics/telemetry on the SDK | One fewer thing to fail, no privacy obligations. |
| No anti-bot evasion features | No arms race; spec-compliant code stays valid as the spec evolves slowly. |

**Things explicitly avoided** because they require ongoing attention:
- Self-hosted Postgres
- Custom domain certificates managed manually (use Railway/Fly.io managed certs)
- Hand-rolled rate limiting (use Cloudflare's)
- Anything requiring a credit card on a service the dev cannot access from RU (Vercel, Stripe)
- Email-based account recovery
- A user dashboard / web UI in v1
- WebSockets, SSE, or any long-lived connection

---

## 9. Anti-Patterns

### Anti-Pattern 1: "Sign at the application layer with a decorator"

**What people do:** A `@signed` decorator that wraps a user function and signs *something* — but the function may make 0, 1, or N HTTP calls, and the decorator has no visibility into them.

**Why it's wrong:** Signing must happen at the HTTP-client boundary, on each individual request. A decorator on a Python function cannot reach into an httpx call inside it without monkey-patching.

**Do this instead:** Decorator/wrapper goes on the *client* (`httpx.Client`, `aiohttp.ClientSession`, `fetch`), not on the user's function. PROJECT.md mentions a "decorator" — interpret this as a *client-construction* helper (`make_signed_client(identity)` or `WebBotAuth(identity)` passed to client constructor), not a function decorator.

### Anti-Pattern 2: "Make the directory the source of truth for identity"

**What people do:** Tightly couple the SDK to the directory, requiring every signing operation to fetch the agent's record from the directory first.

**Why it's wrong:** Adds latency, creates a hard dependency, and is conceptually wrong: the agent owns the private key, the agent *is* the identity. The directory is a phone book.

**Do this instead:** SDK reads the keypair locally; directory URL is a string the SDK embeds in `Signature-Agent`. Agent can publish JWKS at any HTTPS URL.

### Anti-Pattern 3: "Cache the policy globally with a long TTL"

**What people do:** Cache `inspect(url)` results for 24 hours globally to reduce traffic.

**Why it's wrong:** Site policies change. Aggressive caching means agents continue to scrape sites that have just added an `ai.txt` deny rule.

**Do this instead:** Default 1-hour per-host TTL, cache invalidation on user request, document clearly. Honor `Cache-Control` headers from the source if present.

### Anti-Pattern 4: "Auto-rotate keys silently"

**What people do:** SDK rotates the keypair on a schedule for "security."

**Why it's wrong:** The directory record points at a specific kid. Rotating the key invalidates verification until the directory updates. For agents on infrequent runs this is permanently broken.

**Do this instead:** Manual rotation only, with an explicit `Identity.rotate()` that registers the new key with the directory and keeps the old one valid until expiry. Document rotation as a deliberate act.

### Anti-Pattern 5: "Use a single global httpx client"

**What people do:** Create a singleton signed client and reuse forever.

**Why it's wrong:** Connection pool exhaustion, hard to test, and ties the lifetime of the process to one configuration.

**Do this instead:** `WebBotAuth(identity)` is reusable across many client instances. Show users how to construct fresh clients per task.

### Anti-Pattern 6: "1:1 port from Python to TypeScript"

**What people do:** Naively translate Python class names, method conventions, and async patterns into TS — `policy.fetched_at`, snake_case fields in JSON output, `async def` paradigms applied to Promise chains awkwardly.

**Why it's wrong:** TS users find it un-idiomatic and assume the library is low-quality. JSON wire formats (test vectors, directory records) should be canonical (probably snake_case to match IETF drafts), but TS public API uses camelCase.

**Do this instead:** Same concepts, idiomatic surface in each language. `Identity.loadOrGenerate()` in TS, `Identity.load_or_generate()` in Python, both calling into byte-equal signing primitives.

---

## 10. Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **Cloudflare verified-bot directory** | Manual one-time form submission per the docs at `developers.cloudflare.com/bots/reference/bot-verification/web-bot-auth/`. After submission, Cloudflare crawls the agent's directory URL. | Submit `agentpassport.dev` itself as a verified bot using the toolkit's own SDK to dogfood. |
| **Cloudflare debug endpoint** | `https://http-message-signatures-example.research.cloudflare.com/debug` accepts signed requests and returns whether verification succeeded. | Use in CI weekly + after every signer change. This is the conformance oracle. |
| **Railway managed Postgres** | Standard `DATABASE_URL` env var, connection via asyncpg. | Keep schema simple — single migration file. |
| **Cloudflare CDN (in front of agentpassport.dev)** | Set TTLs in response `Cache-Control` headers. Use Cloudflare Cache API or just headers. | All read endpoints cacheable, write endpoints `no-store`. |
| **GitHub Pages (mirror)** | GitHub Action runs nightly, dumps `/static/all.json` from agentpassport.dev to `gh-pages` branch. | Disaster-recovery; no SLA needed. |
| **PyPI / npm** | GitHub Actions on tag push, OIDC for trusted publishing (no long-lived tokens). | Critical: OIDC publishing means no token to rotate during the army period. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| **SDK signer ↔ adapters** | Python: in-process function call returning a dataclass. TS: same. | Pure function, no I/O. |
| **SDK ↔ directory** | HTTPS REST, only for `register` and `lookup`. Never required for signing. | Optional dependency. |
| **Directory backend ↔ Python SDK code** | `directory/` imports `python/agentpassport.verifier` as a library dependency. | Single point of crypto reuse; ensures registration challenge verification matches what verifiers see in production. |
| **Spec ↔ Python tests** | Python tests load JSON files from `spec/test-vectors/`. | Path: `spec/test-vectors/sign/*/{input.json, expected.json}`. |
| **Spec ↔ TS tests** | Vitest tests load same JSON files. | Same path; cross-language CI runs both, fails if either drifts. |
| **Policy parsers ↔ Policy dataclass** | Each parser is `parse(bytes) -> ParsedX | None`. Inspector composes. | Parsers are independently testable; vectors live in `spec/test-vectors/policy-parse/fixtures/`. |
| **Identity ↔ on-disk keyfile** | JSON file at `~/.agentpassport/key.json` (override via env var or constructor arg). Mode 0600 enforced. | Keep format identical between Python and TS so users can switch SDKs with the same key. |

---

## 11. Scaling Considerations

The directory is the only thing that scales; the SDK runs in user processes.

| Scale | Architecture |
|-------|--------------|
| **0-1k registered identities** | FastAPI single instance on Railway hobby tier, single Postgres, no CDN even needed. |
| **1k-100k identities** | Add Cloudflare CDN in front (free tier covers this). Snapshot job runs every minute. Postgres on Railway pro tier. |
| **100k-1M identities** | Pre-compute snapshot per-prefix (`/v1/agents/abc*`), serve as static. Add a read replica on Postgres. Move snapshot job to a cron worker. This is well past v1; the dev is back from the army by then. |
| **>1M identities** | Reconsider as a federated directory (each agent host its own JWKS, agentpassport.dev becomes a search index). This is a v3 problem at earliest. |

### Scaling Priorities

1. **First bottleneck: read traffic on `/.well-known/http-message-signatures-directory/{id}`.** Each verified request from Cloudflare may hit it. Mitigation: Cloudflare CDN with 5-minute cache. Verifiers are themselves expected to cache (per the IETF draft).
2. **Second bottleneck: Postgres writes during a viral moment.** Mitigation: queue registrations through an in-memory deque if write load exceeds 10/s; rare. Most of the time writes are <1/s.
3. **Third bottleneck: snapshot job blocking the event loop.** Mitigation: run in a thread, not async; small enough to not matter for years.

**The SDK does not scale — it runs in the user's process.** Per-host policy cache is per-process; that's fine because the inspector is cheap (5 HTTP requests in parallel, mostly 404s, ~200ms typical).

---

## Sources

- [draft-meunier-web-bot-auth-architecture-02 (IETF)](https://datatracker.ietf.org/doc/html/draft-meunier-web-bot-auth-architecture-02) — primary spec
- [draft-meunier-http-message-signatures-directory-05 (IETF)](https://datatracker.ietf.org/doc/html/draft-meunier-http-message-signatures-directory-05) — JWKS directory format
- [RFC 9421 — HTTP Message Signatures](https://datatracker.ietf.org/doc/html/rfc9421) — signing primitive
- [Cloudflare web-bot-auth reference (TypeScript)](https://github.com/cloudflare/web-bot-auth) — TS reference impl, used as oracle
- [Cloudflare Web Bot Auth docs](https://developers.cloudflare.com/bots/reference/bot-verification/web-bot-auth/) — directory submission flow, validation rules
- [Cloudflare verified-bots message signatures blog](https://blog.cloudflare.com/verified-bots-with-cryptography/) — submission UX
- [Cloudflare debug endpoint](https://http-message-signatures-example.research.cloudflare.com/) — external conformance oracle
- [SEP-1649: MCP Server Cards via .well-known](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1649) — MCP discovery
- [SEP-2127 PR: well-known mcp.json](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2127) — current state of the discovery proposal
- [draft-serra-mcp-discovery-uri-04 (IETF)](https://datatracker.ietf.org/doc/draft-serra-mcp-discovery-uri/) — MCP URI scheme
- [HTTPX Authentication docs](https://www.python-httpx.org/advanced/authentication/) — `Auth` subclass pattern
- [HTTPX `_auth.py` source](https://github.com/encode/httpx/blob/master/httpx/_auth.py) — reference for adapter implementation
- [aiohttp Client Middleware Cookbook](https://docs.aiohttp.org/en/stable/client_middleware_cookbook.html) — middleware signature and patterns
- [requests Transport Adapters](https://requests.readthedocs.io/en/latest/_modules/requests/adapters/) — PreparedRequest hook point
- [Undici Dispatcher docs](https://github.com/nodejs/undici/blob/main/docs/docs/api/Dispatcher.md) — Node interceptor model
- [Playwright Network docs](https://playwright.dev/docs/network) — `page.route()` for header injection
- [Stytch: How to implement Web Bot Auth](https://stytch.com/blog/how-to-implement-web-bot-auth-signing/) — practical implementation walkthrough
- [OpenBotAuth open-source toolkit](https://github.com/OpenBotAuth/openbotauth) — adjacent OSS reference
- [AWS Bedrock AgentCore Web Bot Auth](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-web-bot-auth.html) — second reference implementation
- [Google `agent.bot.goog` identity](https://nohacks.co/blog/google-agent-user-agent) — production deployment example
- [Railway FastAPI+Postgres deploy guide](https://docs.railway.com/guides/fastapi) — deployment template
- [Fly.io FastAPI deploy guide](https://fly.io/docs/python/frameworks/fastapi/) — alternative deployment

---
*Architecture research for: Agent Identity & Policy Toolkit*
*Researched: 2026-05-03*
