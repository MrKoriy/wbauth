# wbauth

**Verifiable identity and pre-flight policy checks for AI agents and web crawlers.**

An open-source toolkit for IETF **Web Bot Auth**. It signs your requests with Ed25519 [HTTP Message Signatures (RFC 9421)](https://www.rfc-editor.org/rfc/rfc9421) and reads a site's published rules before your agent makes a request.

[![npm](https://img.shields.io/npm/v/wb-auth?style=flat-square&color=111111&label=npm)](https://www.npmjs.com/package/wb-auth)
[![License](https://img.shields.io/badge/license-Apache%202.0-111111?style=flat-square)](LICENSE)
[![RFC 9421](https://img.shields.io/badge/RFC-9421-111111?style=flat-square)](https://www.rfc-editor.org/rfc/rfc9421)
[![Python](https://img.shields.io/badge/python-3.11%2B-111111?style=flat-square)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-20%2B-111111?style=flat-square)](https://nodejs.org/)
[![Python CI](https://img.shields.io/github/actions/workflow/status/MrKoriy/wbauth/python.yml?branch=main&style=flat-square&label=python&color=111111)](https://github.com/MrKoriy/wbauth/actions/workflows/python.yml)
[![TypeScript CI](https://img.shields.io/github/actions/workflow/status/MrKoriy/wbauth/typescript.yml?branch=main&style=flat-square&label=typescript&color=111111)](https://github.com/MrKoriy/wbauth/actions/workflows/typescript.yml)

```bash
npm install wb-auth                                              # TypeScript / JavaScript (ESM + CommonJS)
pip install "wbauth-sdk @ git+https://github.com/MrKoriy/wbauth#subdirectory=python"   # Python (PyPI release pending)
```

> The npm package is **`wb-auth`**. The Python distribution is **`wbauth-sdk`**; the import name and CLI are `wbauth`.

---

## Contents

- [Why wbauth exists](#why-wbauth-exists)
- [Quickstart](#quickstart)
- [Signed identity](#signed-identity)
- [Pre-flight policy engine](#pre-flight-policy-engine)
- [Framework integrations](#framework-integrations)
- [CLI](#cli)
- [JWKS directory on Cloudflare Workers](#jwks-directory-on-cloudflare-workers)
- [Standards](#standards)
- [Security model](#security-model)
- [Repository layout](#repository-layout)
- [Development](#development)

---

## Why wbauth exists

To a site, most automated traffic is just an IP address and a `User-Agent` string, and both are trivial to fake. Legitimate agents get caught by the same rate limits, challenges and blocks as abusive scrapers.

Web Bot Auth gives an agent a key pair. The agent publishes its public key in a JWKS directory and signs every request with RFC 9421. The origin (or a CDN such as Cloudflare) fetches the key, checks the signature and knows who it is talking to.

A well-behaved agent should also know what a site allows **before** sending a request. wbauth covers both halves:

| Capability | Result |
|---|---|
| **Signed identity** | Ed25519 RFC 9421 signatures with `tag="web-bot-auth"`, RFC 7638 key IDs, JWKS publishing, Cloudflare-compatible request format |
| **Pre-flight policy** | Parallel fetch of `robots.txt`, `ai.txt`, `llms.txt` and the signing directory, reduced to one deterministic verdict: `allowed`, `restricted` or `forbidden` |

> wbauth does not bypass bot protection, solve challenges or rotate fingerprints. It makes your agent identifiable and helps it follow site rules.

---

## Quickstart

### Python

```python
import httpx
from wbauth import Identity, inspect, signed_client

identity = Identity.load_or_generate(
    "~/.config/wbauth/key.pem",
    signature_agent_url="https://agent.example.com/.well-known/http-message-signatures-directory",
    user_agent="ExampleAgent/1.0 (+https://agent.example.com)",
)

policy = await inspect("https://example.com/articles/42", user_agent=identity.user_agent)
if policy.verdict != "forbidden":
    with signed_client(identity, follow_redirects=True) as client:   # re-signs every redirect hop
        client.get("https://example.com/articles/42")
```

### TypeScript

```ts
import { Identity, createSignedFetch } from "wb-auth";

const identity = await Identity.loadOrGenerate("./wbauth.pem", {
  signatureAgentUrl: "https://agent.example.com/.well-known/http-message-signatures-directory",
  userAgent: "ExampleAgent/1.0 (+https://agent.example.com)",
});

const signedFetch = createSignedFetch(identity);
await signedFetch("https://example.com/articles/42");
```

CommonJS works too: `const { Identity, createSignedFetch } = require("wb-auth");`

### Generate a key once

```bash
wbauth keygen --output wbauth.pem --jwks-output jwks.json
# prints the keyid (RFC 7638 thumbprint); the key file is written with mode 0600
```

---

## Signed identity

Each signed request carries three headers:

```http
Signature-Agent: "https://agent.example.com/.well-known/http-message-signatures-directory"
Signature-Input: sig1=("@authority" "signature-agent");created=1735689600;expires=1735689660;keyid="poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U";alg="ed25519";nonce="...";tag="web-bot-auth"
Signature: sig1=:...:
```

| Parameter | Default |
|---|---|
| Algorithm | Ed25519 |
| `keyid` | RFC 7638 JWK thumbprint (SHA-256, base64url) |
| Covered components | `@authority`, `signature-agent`; plus `content-digest` when there is a body |
| Lifetime | 60 seconds (`expires` must be > 0; configurable) |
| Nonce | 64 random bytes, base64 (as required by `web-bot-auth`) |

Behaviour shared by both SDKs:

- Any request with a body (`POST`, `PUT`, `PATCH`, but also `DELETE`, `QUERY`, …) gets a `Content-Digest` (RFC 9530) that is covered by the signature; streaming bodies are buffered first.
- `@authority` is normalized per RFC 9421 §2.2.3 (lower-case host, no userinfo, no default port), so `https://host:443/` signs exactly like `https://host/` — what Cloudflare derives from `Host`.
- The validity window must be in `(0, 3600]` seconds (default 60). Longer windows would turn a signature into a replayable credential.
- Stale `Signature`, `Signature-Input` and `Signature-Agent` headers are removed before re-signing.
- The identity's `User-Agent` replaces library defaults (`python-requests/*`, `python-httpx/*`, `node`, `undici`) but never overrides one you set explicitly.
- **Redirects are re-signed per hop** for the new `@authority`: Python `signed_client()` / `signed_async_client()` (httpx) and `signed_session()` (requests); TS `createSignedFetch` follows redirects itself (`redirect: "follow"`, the default), rewrites method/body per the fetch spec and drops `Authorization`/`Cookie` on cross-origin hops. Plain `httpx.Client(auth=WebBotAuth(...))` cannot see redirect hops and emits `RedirectNotSignedWarning` if one happens.
- The Python signer builds the RFC 9421 base directly (~2× faster than the generic library path); a property-based test keeps it byte-identical to `http-message-signatures`, and CI cross-verifies Python↔TypeScript signatures on randomized requests.

Shared cross-language vectors live in [`spec/test-vectors/`](spec/test-vectors/); both SDKs must produce byte-identical signature bases.

---

## Pre-flight policy engine

`inspect(url)` fetches each policy source in parallel from the target's own origin (scheme, host, port — so `http://host:8080/x` reads `http://host:8080/robots.txt`), with a 3 s timeout per endpoint, at most 5 redirects, robots.txt truncated at 500 KiB and other bodies capped at 1 MB, and reduces the results to one verdict. Redirects from a public origin to loopback/private/link-local addresses or non-HTTP schemes are refused (SSRF guard).

| Source | Location | Effect |
|---|---|---|
| robots.txt | `/robots.txt` | RFC 9309 via [protego], evaluated for your `User-Agent` and path; `Crawl-delay` is reported |
| ai.txt | `/ai.txt` | Restrictions → `restricted`. A rule that names paths (`- /admin/ not for training`) only applies under those paths; rules without a path are site-wide |
| llms.txt | `/llms.txt` | Informational; restrictive wording → `restricted` |
| Signing directory | `/.well-known/http-message-signatures-directory` | Informational (site supports Web Bot Auth) |

[protego]: https://github.com/scrapy/protego

**Precedence:** `forbidden` > `restricted` > `allowed`. A partial fetch (any endpoint failed) downgrades `allowed` to `restricted`.

**robots.txt failures follow RFC 9309:**

| robots.txt result | Treated as |
|---|---|
| `2xx` | Parsed and evaluated |
| `4xx` (except 429), redirect limit exceeded | Unavailable → no robots restriction |
| `429`, `5xx`, timeout, network error | Unreachable → complete disallow (`forbidden`) |
| HTML instead of robots.txt | `forbidden` (strict) |

```python
policy = await inspect("https://example.com/articles/42", user_agent="ExampleAgent/1.0")

policy.verdict              # "allowed" | "restricted" | "forbidden"
policy.reasons              # ["evaluated against User-Agent='ExampleAgent/1.0'", "robots.txt Crawl-delay: 10s", ...]
policy.robots.crawl_delay   # 10.0
policy.partial, policy.errors
```

Results are cached per origin with a TTL that honours `Cache-Control: max-age` (capped at 24 h; `no-store`/`no-cache` skip the cache, `private` is fine for this client-side cache), including negative results. robots.txt is cached once per origin and evaluated per path and user agent. Expired entries with an `ETag`/`Last-Modified` are revalidated with a conditional GET, so an unchanged file costs a `304`. Concurrent `inspect()` calls for the same origin share one in-flight request per file. A UTF-8 BOM at the start of a policy file is ignored. Pass `client=` to reuse your own `httpx.AsyncClient`.

```python
from wbauth.policy import load_cache, save_cache
load_cache("~/.cache/wbauth/policy.json")   # optional: persist between runs (raw bodies only)
...
save_cache("~/.cache/wbauth/policy.json")
```

---

## Secure defaults & new APIs (0.4)

**Scope signing.** Adapters sign only `https://` requests by default (`allow_insecure=True` / `allowInsecure: true` for local tests) and can be limited to your targets; out-of-scope hops are sent with signature headers stripped.

```python
client = signed_async_client(identity, hosts=["*.example.com"], respect_policy=True)  # + PolicyGuard: forbidden → PolicyForbiddenError, Crawl-delay honoured
```
```ts
const f = createSignedFetch(identity, { hosts: ["api.example.com"] });
```

**Keys.** `keygen` refuses to overwrite; `register` never generates a key. Rotation is persistent with a keyring directory (`active.pem` + `retiring.pem`, both published in the JWKS until the next rotation); keys can be stored encrypted (`password=` / `WBAUTH_KEY_PASSWORD`) or kept in a KMS/HSM via `Identity.from_signer()` / `Identity.fromSigner()`.

```python
identity = Identity.load_keyring("~/.config/wbauth/keys", signature_agent_url=URL)
identity = identity.rotate_keyring("~/.config/wbauth/keys")      # CLI: wbauth rotate --keyring DIR
```

**Verify incoming requests** (both SDKs; nonce replay cache, clock skew, JWKS fetched from `Signature-Agent` with an SSRF guard):

```python
from wbauth import Verifier
from wbauth.verifier import WebBotAuthMiddleware
app.add_middleware(WebBotAuthMiddleware, required=False)   # request.state.web_bot_auth
agent = await Verifier().verify("GET", url, headers)
```
```ts
import { Verifier } from "wb-auth";
const agent = await new Verifier().verify(request);   // WHATWG Request
```

`JSON.stringify(identity)` / `repr(identity)` never contain private key material, and `signatureAgentUrl` is validated (https, no quotes/CRLF).

---

## Framework integrations

### httpx

```python
from wbauth import signed_client, signed_async_client
client = signed_client(identity, follow_redirects=True)   # every hop signed for its own authority
aclient = signed_async_client(identity, http2=False)      # kwargs go to httpx.AsyncClient

from wbauth import WebBotAuth                              # drop-in auth= (no redirect re-signing)
client = httpx.Client(auth=WebBotAuth(identity))
```

### requests

```python
from wbauth import signed_session
session = signed_session(identity)        # re-signs every redirect hop
session.get("https://example.com/")
```

`WebBotAuthAdapter` is available if you manage mounts yourself. Note that `requests` does not re-run `auth=` on redirects, so prefer `signed_session()`.

### Playwright

```bash
pip install "wbauth-sdk[playwright] @ git+https://github.com/MrKoriy/wbauth#subdirectory=python"
```

```python
from wbauth import attach_signing
await attach_signing(page, identity, hosts=["example.com"])   # sign only these hosts (and subdomains)
```

```ts
import { applyTo } from "wb-auth";
await applyTo(page, identity, { hosts: ["example.com"] });
```

Both skip non-HTTP(S) requests and accept a custom predicate (`should_sign` / `shouldSign`). Without `hosts`, every HTTP(S) request is signed, including third-party ones.

### Examples

| Example | Stack |
|---|---|
| [`examples/browser_use_demo.py`](examples/browser_use_demo.py) | Browser Use + `attach_signing` |
| [`examples/openai_agents_demo.py`](examples/openai_agents_demo.py) | OpenAI Agents SDK + `WebBotAuth` |
| [`examples/stagehand_demo.ts`](examples/stagehand_demo.ts) | Stagehand + `wb-auth` |

---

## CLI

```bash
wbauth keygen   [--output PATH] [--jwks-output PATH]
wbauth inspect  URL [--format text|table|json] [--json] [--user-agent UA] [--cache PATH]
                                                    # exit 0 allowed, 1 restricted, 2 forbidden, 3 error
wbauth verify   [--domain] [--identity PEM] [--json] # check signing against Cloudflare's research verifier
wbauth register --identity PEM [--directory URL] [--client-name] [--purpose] [--client-uri] [--expected-user-agent]
wbauth serve    --jwks jwks.json [--port 8080]      # minimal local JWKS host
```

`wbauth inspect --format table` prints a per-source breakdown (found / absent / error and why), colored on a TTY (`NO_COLOR` respected). `--cache PATH` persists the policy cache between runs.

`wbauth register` publishes your key to the hosted directory (default `https://wbauth.silov801.workers.dev`).

---

## JWKS directory on Cloudflare Workers

[`directory/`](directory/) is a Hono Worker backed by D1 that hosts agent keys under `/.well-known/http-message-signatures-directory/{kid}`. Registration is a two-step proof of key ownership:

1. `POST /register/challenge` returns a 5-minute nonce.
2. `POST /register/submit` with the Signature Agent Card, signed by the key itself. The signature must cover `content-digest` (matching the raw body) and `signature-agent`; `kid` must equal the RFC 7638 thumbprint of every key.

**Domain verification.** Proving key ownership does not prove you own the domain in `signature_agent_url`. An agent is marked `domain_verified: true` only if that URL is the directory's own hosted JWKS for the kid, or serves a JWKS containing the registered key. Unverified registrations are accepted but flagged everywhere (`/agents`, `/agents/{kid}`, `/static/all.json`, the web page and badges) — never treat an unverified host as authoritative.

The directory also serves a searchable web page at `/` and a README badge at `/badge/{kid}.svg` (`verified` / `registered`). Challenge and submit calls have separate per-IP daily budgets; IPv6 clients are limited per `/64`.

Reads are edge-cached for 60 s and purged on re-registration. See [`directory/README.md`](directory/README.md) for endpoints, migrations and deployment.

---

## Standards

| Standard | Scope |
|---|---|
| [RFC 9421](https://www.rfc-editor.org/rfc/rfc9421) HTTP Message Signatures | Signature base, `Signature-Input`, `Signature`, `alg="ed25519"` |
| [RFC 9530](https://www.rfc-editor.org/rfc/rfc9530) Digest Fields | `Content-Digest` for bodies |
| [RFC 7638](https://www.rfc-editor.org/rfc/rfc7638) JWK Thumbprint | `keyid` derivation |
| [RFC 8037](https://www.rfc-editor.org/rfc/rfc8037) OKP keys in JOSE | Ed25519 JWK (`kty="OKP"`, `crv="Ed25519"`) |
| [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309) Robots Exclusion Protocol | Parsing, matching, status-code semantics |
| [IETF Web Bot Auth](https://datatracker.ietf.org/wg/webbotauth/about/) (draft) | `Signature-Agent`, `tag="web-bot-auth"`, key directory format |

Web Bot Auth is still an Internet-Draft; wire-format changes will ship as a minor version with a note in [`CHANGELOG.md`](CHANGELOG.md).

---

## Security model

- Private keys stay local. Key files are written with mode `0600`, and the SDKs never send or log key material.
- Signatures are bound to the authority, expire after 60 s by default and carry a random nonce.
- A valid signature proves *who* sent a request, not *what* it may do. A `forbidden` verdict is a stop signal, not a warning.
- Non-goals: evading bot detection, solving CAPTCHAs/Turnstile, spoofing browser fingerprints.

To report a vulnerability, see [`SECURITY.md`](SECURITY.md).

---

## Repository layout

```text
wbauth/
├── python/            Python SDK + CLI (httpx, requests, Playwright adapters, policy engine)
├── typescript/        npm package `wb-auth` (fetch, Playwright)
├── directory/         Cloudflare Worker + D1 JWKS directory
├── examples/          Browser Use, OpenAI Agents, Stagehand demos
└── spec/test-vectors/ Shared cross-language signature fixtures
```

---

## Development

```bash
git clone https://github.com/MrKoriy/wbauth && cd wbauth

# Python (uv workspace)
uv sync --locked
uv run pytest python/tests && uv run ruff check python && uv run pyright

# TypeScript + Worker (npm workspaces)
npm ci
npm run lint && npm run typecheck --workspaces && npm run build && npm test
```

Releases are cut from a `vX.Y.Z` tag; CI checks that the tag matches both package versions before publishing to PyPI and npm (with provenance).

## License

[Apache 2.0](LICENSE)
