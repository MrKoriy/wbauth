# wbauth

**Verifiable identity and pre-flight policy checks for AI agents and web crawlers.**

An open-source toolkit that implements IETF **Web Bot Auth**. It signs your requests with Ed25519 [HTTP Message Signatures (RFC 9421)](https://www.rfc-editor.org/rfc/rfc9421) and reads a site's published rules before your agent makes a request.

[![PyPI](https://img.shields.io/pypi/v/wbauth?style=flat-square&color=111111&label=pypi)](https://pypi.org/project/wbauth/)
[![npm](https://img.shields.io/npm/v/wbauth?style=flat-square&color=111111&label=npm)](https://www.npmjs.com/package/wbauth)
[![License](https://img.shields.io/badge/license-Apache%202.0-111111?style=flat-square)](LICENSE)
[![RFC 9421](https://img.shields.io/badge/RFC-9421-111111?style=flat-square)](https://www.rfc-editor.org/rfc/rfc9421)
[![Python](https://img.shields.io/badge/python-3.10%2B-111111?style=flat-square)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/typescript-5%2B-111111?style=flat-square)](https://www.typescriptlang.org/)
[![Tests](https://img.shields.io/github/actions/workflow/status/MrKoriy/wbauth/ci.yml?branch=main&style=flat-square&label=tests&color=111111)](https://github.com/MrKoriy/wbauth/actions/workflows/ci.yml)

```
pip install wbauth          npm install wbauth
```

---

## Contents

- [Why wbauth exists](#why-wbauth-exists)
- [30-second quickstart](#30-second-quickstart)
- [Signed identity](#signed-identity)
- [Pre-flight policy engine](#pre-flight-policy-engine)
- [Framework integrations](#framework-integrations)
- [CLI](#cli)
- [JWKS directory on Cloudflare Workers](#jwks-directory-on-cloudflare-workers)
- [Architecture](#architecture)
- [Standards and compliance](#standards-and-compliance)
- [Security model](#security-model)
- [Repository layout](#repository-layout)
- [Contributing](#contributing)
- [License](#license)

---

## Why wbauth exists

Most automated traffic on the web looks the same to a site: an IP address and a `User-Agent` string. Anyone can fake either one. Sites defend themselves with rate limits, bot scores, challenges such as Cloudflare Turnstile, and outright blocks. Legitimate agents get caught by the same rules as abusive scrapers because the site has no way to tell them apart.

The fix is **cryptographic identity, not better disguise.**

Web Bot Auth gives an agent a key pair. The agent publishes its public key in a JWKS directory at a stable URL and signs every request with RFC 9421 HTTP Message Signatures. The origin, or a CDN acting for it, fetches the key, checks the signature, and decides what to do with a known party.

Identity is only half the problem. A well-behaved agent should also know what a site allows **before** it sends a request. That information is spread across `robots.txt`, `ai.txt`, `llms.txt` and several `.well-known` endpoints, each with its own format and failure rules.

wbauth covers both halves in one import:

| | Capability | Result |
|---|---|---|
| **1** | **Signed identity** | Ed25519 RFC 9421 signatures, JWKS publishing and verification, and a request format compatible with Cloudflare Verified Bots |
| **2** | **Pre-flight policy engine** | Parallel inspection of `robots.txt`, `ai.txt`, `llms.txt` and `.well-known`, producing one deterministic verdict: `allowed`, `restricted` or `forbidden` |

> wbauth does not bypass bot protection, solve challenges or rotate fingerprints. It makes your agent identifiable and helps it follow site rules. Whether a signed agent gets access is still up to the site.

---

## 30-second quickstart

### Python

**Sign requests**

```python
import httpx
from wbauth import Identity

identity = Identity.load("wbauth.key", agent="https://agent.example.com")
client = httpx.Client(auth=identity.httpx_auth())
client.get("https://example.com/articles/42")
```

**Inspect policy**

```python
from wbauth import inspect

report = await inspect("https://example.com/articles/42")
print(report.verdict)   # allowed | restricted | forbidden
```

### TypeScript

**Sign requests**

```ts
import { Identity, signedFetch } from "wbauth";

const identity = await Identity.load("wbauth.key", { agent: "https://agent.example.com" });
const fetch = signedFetch(identity);
await fetch("https://example.com/articles/42");
```

**Inspect policy**

```ts
import { inspect } from "wbauth";

const report = await inspect("https://example.com/articles/42");
console.log(report.verdict); // "allowed" | "restricted" | "forbidden"
```

**Generate a key once**

```bash
wbauth keygen --out wbauth.key
# → wbauth.key        private key (Ed25519, keep secret)
# → jwks.json         public JWKS, ready to publish
# → keyid             poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U  (RFC 7638 thumbprint)
```

---

## Signed identity

Every outgoing request gets three headers:

```http
GET /articles/42 HTTP/1.1
Host: example.com
Signature-Agent: "https://agent.example.com"
Signature-Input: sig1=("@authority" "signature-agent");\
  created=1767225600;expires=1767225900;\
  keyid="poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U";\
  alg="ed25519";nonce="e8N7S2MFd/qrd6T2R3tdfAuuANngKI7LFtKdI/Vldjg=";\
  tag="web-bot-auth"
Signature: sig1=:jdq0SqOwHdyHr9+r5jw3iYZH6aNGKijYp/EstF4RQTQdi5N5YYKrD+mCT1HA1nZDsi6nJKuHxUi/5Syp3rLWBA==:
```

| Header | Purpose |
|---|---|
| `Signature-Agent` | URL of the agent's key directory, where verifiers resolve the public key |
| `Signature-Input` | Covered components and parameters: `created`, `expires`, `keyid`, `alg`, `nonce`, `tag="web-bot-auth"` |
| `Signature` | Ed25519 signature over the RFC 9421 signature base |

**Defaults**

- **Algorithm:** `ed25519` only. No algorithm negotiation and no RSA fallback.
- **`keyid`:** the RFC 7638 JWK thumbprint (SHA-256, base64url) of the public key.
- **Covered components:** `@authority` and `signature-agent`. More can be added with `components=[...]`.
- **Lifetime:** 300 seconds, plus a fresh 32-byte nonce on every request.
- **Directory:** served at `/.well-known/http-message-signatures-directory` with content type `application/http-message-signatures-directory+json`.

**Verification**

```python
from wbauth import verify

result = await verify(request)        # fetches and caches the JWKS behind Signature-Agent
result.valid, result.keyid, result.agent
```

```ts
import { verify } from "wbauth";

const result = await verify(request); // Request from fetch / Workers / Node
```

**Cross-language parity.** The Python and TypeScript SDKs build the same signature base and produce byte-identical signatures for the same key, nonce, timestamp and request. CI enforces this against a shared fixture set in `tests/vectors/`.

**Cloudflare Verified Bots.** The header layout follows the format Cloudflare documents for Web Bot Auth. To have your agent recognized as verified, you still need to register its key directory through Cloudflare's bot verification process. Signing alone does not grant verified status.

---

## Pre-flight policy engine

`inspect(url)` fetches every policy source in parallel, parses each with a standard-conformant parser and reduces the results to a single verdict.

| Source | Location | Parser |
|---|---|---|
| robots.txt | `/robots.txt` | RFC 9309 via [protego](https://github.com/scrapy/protego) |
| ai.txt | `/ai.txt` | ai.txt v1.1.1 |
| llms.txt | `/llms.txt` | llms.txt (informational, plus content hints) |
| .well-known | `/.well-known/*` | Known AI and agent policy endpoints |

### Verdicts

The engine is deterministic. The same inputs always produce the same verdict, and every verdict comes with the rule that caused it.

| Verdict | Meaning | Typical cause |
|---|---|---|
| `allowed` | No source restricts this agent on this path | No matching disallow and no usage restrictions |
| `restricted` | Access is allowed with conditions | `Crawl-delay`, ai.txt limits on training or reuse, rate hints |
| `forbidden` | Access is denied | `Disallow` matching the path for this user agent, an explicit ai.txt denial, or an unreachable `robots.txt` (5xx) |

**Precedence:** `forbidden` > `restricted` > `allowed`. The most restrictive source wins.

**Failure handling follows RFC 9309:**

| robots.txt status | Treated as |
|---|---|
| `2xx` | Parsed |
| `4xx` | No restrictions (full allow) |
| `5xx` / network error | Complete disallow (`forbidden`) |

```python
report = await inspect("https://example.com/articles/42", user_agent="ExampleAgent")

report.verdict          # "restricted"
report.reasons          # [Reason(source="robots.txt", rule="Crawl-delay: 10")]
report.sources          # per-source status, raw body hash, parsed result
report.crawl_delay      # 10.0
```

---

## Framework integrations

### httpx

```python
import httpx
from wbauth import Identity

identity = Identity.load("wbauth.key", agent="https://agent.example.com")

async with httpx.AsyncClient(auth=identity.httpx_auth()) as client:
    r = await client.get("https://example.com")
```

### requests

```python
import requests
from wbauth import Identity

session = requests.Session()
session.mount("https://", Identity.load("wbauth.key", agent="https://agent.example.com").requests_adapter())
session.get("https://example.com")
```

### Playwright (Python)

```python
from playwright.async_api import async_playwright
from wbauth import Identity, attach_signing

identity = Identity.load("wbauth.key", agent="https://agent.example.com")

async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await browser.new_page()
    await attach_signing(page, identity)      # signs every request the page sends
    await page.goto("https://example.com")
```

### Playwright (TypeScript)

```ts
import { chromium } from "playwright";
import { Identity, attachSigning } from "wbauth";

const identity = await Identity.load("wbauth.key", { agent: "https://agent.example.com" });
const page = await (await chromium.launch()).newPage();
await attachSigning(page, identity);
await page.goto("https://example.com");
```

### Browser Use

`examples/browser_use_demo.py` checks policy before the agent acts, then signs every navigation.

```python
from browser_use import Agent
from wbauth import Identity, attach_signing, inspect

identity = Identity.load("wbauth.key", agent="https://agent.example.com")

if (await inspect(target)).verdict == "forbidden":
    raise SystemExit("Site policy forbids this agent.")

agent = Agent(task=f"Summarize {target}", llm=llm)
await attach_signing(agent.browser_session, identity)
await agent.run()
```

### OpenAI Agents SDK

`examples/openai_agents_demo.py` exposes wbauth as a tool, so the model checks policy before it fetches anything.

```python
from agents import Agent, function_tool
from wbauth import inspect

@function_tool
async def check_policy(url: str) -> str:
    report = await inspect(url)
    return f"{report.verdict}: {'; '.join(r.rule for r in report.reasons)}"

agent = Agent(name="researcher", tools=[check_policy, signed_fetch_tool])
```

### Stagehand

`examples/stagehand_demo.ts` signs the underlying Playwright page.

```ts
import { Stagehand } from "@browserbasehq/stagehand";
import { Identity, attachSigning } from "wbauth";

const stagehand = new Stagehand({ env: "LOCAL" });
await stagehand.init();
await attachSigning(stagehand.page, await Identity.load("wbauth.key", { agent: AGENT_URL }));
await stagehand.page.goto("https://example.com");
```

| Integration | Python | TypeScript | Example |
|---|:-:|:-:|---|
| httpx | ● | — | — |
| requests | ● | — | — |
| fetch | — | ● | — |
| Playwright | ● | ● | — |
| Browser Use | ● | — | `examples/browser_use_demo.py` |
| OpenAI Agents | ● | — | `examples/openai_agents_demo.py` |
| Stagehand | — | ● | `examples/stagehand_demo.ts` |

---

## CLI

```bash
wbauth keygen  --out wbauth.key
wbauth inspect https://example.com/articles/42 --user-agent ExampleAgent
wbauth verify  --request request.http
```

```text
$ wbauth inspect https://example.com/articles/42

  robots.txt     200   Crawl-delay: 10
  ai.txt         200   training: disallow
  llms.txt       404   —
  .well-known    —     none found

  verdict        restricted
```

Exit codes: `0` allowed, `1` restricted, `2` forbidden, `3` error. These are safe to use as gates in shell scripts and CI.

---

## JWKS directory on Cloudflare Workers

`directory/` hosts your public keys as a Cloudflare Worker backed by D1. It fits within the Workers and D1 free tiers, so it adds no billing.

```bash
cd directory
npx wrangler d1 create wbauth-directory
npx wrangler d1 migrations apply wbauth-directory
npx wrangler deploy
wbauth publish jwks.json --directory https://agent.example.com
```

| Endpoint | Response |
|---|---|
| `GET /.well-known/http-message-signatures-directory` | JWKS, `application/http-message-signatures-directory+json`, signed per Web Bot Auth |
| `POST /keys` | Add a key (authenticated) |
| `DELETE /keys/:keyid` | Revoke a key (authenticated) |

To rotate a key, publish the new one, overlap both for at least one cache TTL, then revoke the old one.

---

## Architecture

```text
                         ┌──────────────────────────────────────────┐
                         │                 wbauth                   │
                         │                                          │
   agent / crawler ────▶ │  1. inspect(url)                         │
                         │     ├─ robots.txt   (RFC 9309, protego)  │
                         │     ├─ ai.txt       (v1.1.1)             │
                         │     ├─ llms.txt                          │
                         │     └─ .well-known/*                     │
                         │            │  fan-out, parallel          │
                         │            ▼                             │
                         │     verdict: allowed│restricted│forbidden│
                         │            │                             │
                         │            ▼  (if not forbidden)         │
                         │  2. sign(request)                        │
                         │     Ed25519 · RFC 9421 · tag=web-bot-auth│
                         └────────────┬─────────────────────────────┘
                                      │ Signature-Agent
                                      │ Signature-Input
                                      │ Signature
                                      ▼
                         ┌──────────────────────────┐
                         │  origin / CDN verifier   │
                         └────────────┬─────────────┘
                                      │ GET /.well-known/
                                      │ http-message-signatures-directory
                                      ▼
                         ┌──────────────────────────┐
                         │  JWKS directory          │
                         │  Cloudflare Worker + D1  │
                         └──────────────────────────┘
```

| Stage | Component | Input | Output |
|---|---|---|---|
| Policy | `inspect` | URL, user agent | `Report` (verdict, reasons, sources) |
| Identity | `Identity` | Ed25519 key, agent URL | Signer bound to `keyid` |
| Transport | Adapters | Request | Signed request |
| Discovery | `directory/` | — | Public JWKS |
| Verification | `verify` | Signed request | `valid`, `keyid`, `agent` |

---

## Standards and compliance

| Standard | Scope in wbauth |
|---|---|
| [RFC 9421](https://www.rfc-editor.org/rfc/rfc9421): HTTP Message Signatures | Signature base, `Signature-Input`, `Signature`, Ed25519 (`alg="ed25519"`) |
| [RFC 7638](https://www.rfc-editor.org/rfc/rfc7638): JWK Thumbprint | `keyid` derivation, SHA-256, base64url |
| [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309): Robots Exclusion Protocol | Parsing, matching and status-code semantics via protego |
| [RFC 8037](https://www.rfc-editor.org/rfc/rfc8037): OKP keys in JOSE | Ed25519 JWK representation (`kty="OKP"`, `crv="Ed25519"`) |
| [IETF Web Bot Auth](https://datatracker.ietf.org/wg/webbotauth/about/) (draft) | `Signature-Agent`, `tag="web-bot-auth"`, key directory format |
| ai.txt v1.1.1 | AI usage directives |
| llms.txt | Content hints for language models |

Web Bot Auth is still an Internet-Draft. wbauth follows the current draft and pins the targeted revision in `SPEC_VERSION`. Changes to the draft come with a minor version bump and a migration note.

---

## Security model

**Guarantees**

- Private keys never leave the process. The SDKs do not send or log key material.
- Each signature is bound to the authority it was issued for and expires quickly, which limits replay. A per-request nonce lets verifiers reject duplicates.
- Verification refuses unknown algorithms, expired signatures, missing `tag="web-bot-auth"` and `keyid` mismatches.

**Non-goals**

- Evading bot detection, solving CAPTCHAs or Turnstile, or spoofing browser fingerprints.
- Overriding a site's policy. A `forbidden` verdict is a stop signal, not a warning.
- Authorization. A valid signature proves *who* sent a request, not *what* it is allowed to do.

To report a vulnerability, follow [`SECURITY.md`](SECURITY.md). Do not open a public issue.

---

## Repository layout

```text
wbauth/
├── python/            Python SDK, CLI, adapters (httpx, requests, Playwright)
├── typescript/        TypeScript SDK, fetch middleware, Playwright
├── directory/         Cloudflare Worker + D1 JWKS directory
├── examples/
│   ├── browser_use_demo.py
│   ├── openai_agents_demo.py
│   └── stagehand_demo.ts
├── tests/vectors/     Shared cross-language signature fixtures
└── SPEC_VERSION       Targeted Web Bot Auth draft revision
```

---

## Contributing

```bash
git clone https://github.com/MrKoriy/wbauth && cd wbauth
make test        # Python + TypeScript + cross-language vectors
```

Pull requests must keep the shared vectors byte-equal across both SDKs. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## License

[Apache 2.0](LICENSE) © Leonid Kutlin ([@MrKoriy](https://github.com/MrKoriy))