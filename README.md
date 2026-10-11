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
pip install "wbauth @ git+https://github.com/MrKoriy/wbauth#subdirectory=python"   # Python (PyPI release pending)
```

> The npm package is **`wb-auth`**. The Python distribution and CLI are called `wbauth`.

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
from wbauth import Identity, WebBotAuth, inspect

identity = Identity.load_or_generate(
    "~/.config/wbauth/key.pem",
    signature_agent_url="https://agent.example.com/.well-known/http-message-signatures-directory",
    user_agent="ExampleAgent/1.0 (+https://agent.example.com)",
)

policy = await inspect("https://example.com/articles/42", user_agent=identity.user_agent)
if policy.verdict != "forbidden":
    with httpx.Client(auth=WebBotAuth(identity)) as client:
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
| Nonce | Random per request |

Behaviour shared by both SDKs:

- Bodies on `POST`/`PUT`/`PATCH` get a `Content-Digest` (RFC 9530) that is covered by the signature; streaming bodies are buffered first.
- Stale `Signature`, `Signature-Input` and `Signature-Agent` headers are removed before re-signing.
- The identity's `User-Agent` replaces library defaults (`python-requests/*`, `python-httpx/*`, `node`, `undici`) but never overrides one you set explicitly.
- Python's `signed_session()` re-signs every redirect hop for the new authority. In TS, pass `redirect: "manual"` to `createSignedFetch` if you need to re-sign cross-host redirects yourself.

Shared cross-language vectors live in [`spec/test-vectors/`](spec/test-vectors/); both SDKs must produce byte-identical signature bases.

---

## Pre-flight policy engine

`inspect(url)` fetches each policy source in parallel (3 s timeout per endpoint, at most 5 redirects, robots.txt truncated at 500 KiB, other bodies capped at 1 MB) and reduces the results to one verdict.

| Source | Location | Effect |
|---|---|---|
| robots.txt | `/robots.txt` | RFC 9309 via [protego], evaluated for your `User-Agent` and path; `Crawl-delay` is reported |
| ai.txt | `/ai.txt` | Restrictions → `restricted` |
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

Results are cached per host with a TTL that honours `Cache-Control: max-age` (capped at 24 h), including negative results. robots.txt is cached once per host and evaluated per path and user agent. Pass `client=` to reuse your own `httpx.AsyncClient`.

---

## Framework integrations

### httpx

```python
from wbauth import WebBotAuth
client = httpx.Client(auth=WebBotAuth(identity))          # also works with httpx.AsyncClient
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
pip install "wbauth[playwright]"
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
wbauth inspect  URL [--json] [--user-agent UA]      # exit 0 allowed, 1 restricted, 2 forbidden, 3 error
wbauth verify   [--domain] [--identity PEM] [--json] # check signing against Cloudflare's research verifier
wbauth register --identity PEM [--directory URL] [--client-name] [--purpose] [--client-uri] [--expected-user-agent]
wbauth serve    --jwks jwks.json [--port 8080]      # minimal local JWKS host
```

`wbauth register` publishes your key to the hosted directory (default `https://wbauth.silov801.workers.dev`).

---

## JWKS directory on Cloudflare Workers

[`directory/`](directory/) is a Hono Worker backed by D1 that hosts agent keys under `/.well-known/http-message-signatures-directory/{kid}`. Registration is a two-step proof of key ownership:

1. `POST /register/challenge` returns a 5-minute nonce.
2. `POST /register/submit` with the Signature Agent Card, signed by the key itself. The signature must cover `content-digest` (matching the raw body) and `signature-agent`; `kid` must equal the RFC 7638 thumbprint of every key.

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
