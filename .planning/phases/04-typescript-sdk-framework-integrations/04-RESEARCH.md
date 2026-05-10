# Phase 4: TypeScript SDK & Framework Integrations - Research

**Researched:** 2026-05-10
**Domain:** TypeScript SDK (signer + adapters), three framework demo scripts (Browser Use Python, Stagehand TS, OpenAI Agents Python)
**Confidence:** HIGH for §1–§4, §9–§10; MEDIUM for §6–§8 (framework APIs current but examples bound to live LLM APIs / browser env we don't run in CI)

## Summary

Phase 4 has a tighter integration surface than Phases 1–3 because the heavy lifting is already done. The Python signer is locked, the test vectors are byte-equal oracles, the Cloudflare-vendored `web-bot-auth` 0.1.3 npm package handles RFC 9421 mechanics, and Phase 1 already has TS vector tests passing against four of the five vectors. What's missing is glue:

1. A `wbauth.sign(NormalizedRequest, Identity)` TS function that wraps `signatureHeaders` + `signerFromJWK` with Web Bot Auth defaults baked in (mirrors Python's `wbauth.signer.sign`).
2. A `wbauth.Identity` class that loads/persists the **same PKCS8 PEM file** Python writes (`Ed25519PrivateKey` → PKCS8 NoEncryption PEM at 0o600).
3. Two ≤50-LOC adapter files (`createSignedFetch`, `applyTo`).
4. Vitest mock-based tests that reuse `spec/test-vectors/` with the same monkeypatch-fixed-nonce trick the Python conformance tests use.
5. Three runnable example scripts with optional-LLM fallback so they pass smoke-test on a CI box with no API keys.

**Primary recommendation:** Use **Node 20+ stdlib `node:crypto` `createPrivateKey(pem).export({format:'jwk'})`** for PEM→JWK conversion. This is verified to produce a JWK byte-identical to what the Python side persists (same `d` and `x` strings as the test vector). No new TS dependency needed for cross-language key loading. The entire TS SDK stays at `web-bot-auth` + nothing else (Node stdlib only otherwise).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| RFC 9421 signature production (TS) | TS SDK / `wbauth` package | `web-bot-auth` 0.1.3 npm | All signing primitives delegated to Cloudflare's vendored lib. |
| Ed25519 PEM↔JWK conversion (TS) | Node 20+ stdlib (`node:crypto`) | — | `createPrivateKey(pem).export({format:'jwk'})` is the canonical path. Avoids `jose`/`@panva` dep. |
| Identity file format (cross-language) | Python (already implemented) | TS Identity must read the same file | Python's PKCS8 NoEncryption PEM written via `os.open(O_EXCL, 0o600)` is the source-of-truth format. TS reads PEM → derives JWK → loads `signerFromJWK`. |
| Signature-Agent URL injection | TS `wbauth.sign()` | — | Mirror Python: mutate `request.headers["Signature-Agent"]` BEFORE building canonical bytes. |
| Content-Digest auto-computation | TS adapter glue (`_utils.ts`) | — | Python lives in `wbauth.adapters._utils.ensure_content_digest`. Mirror exactly: SHA-256, structured-fields form `sha-256=:<base64>:`. |
| `createSignedFetch` (HTTP wrapper) | TS adapter `adapters/fetch.ts` | Native `fetch` (Node 20+) | Wraps `globalThis.fetch`. Returns a `typeof fetch`-compatible function. |
| `applyTo(page, identity)` (Playwright) | TS adapter `adapters/playwright.ts` | Playwright `page.route` API | Async; registers `page.route("**/*", handler)` mirroring Python. |
| Cross-language byte-equality oracle | `spec/test-vectors/` JSON | Vitest + pytest both load these | Already wired in Phase 1; extend pattern to adapter conformance tests. |
| Live-browser tests | OUT OF CI (D-65) | Examples directory only | Real Playwright runs only in `examples/*_demo.{py,ts}`, never in CI. |
| LLM call (in examples) | OUT OF CI | Optional, mock-fallback when env var absent | `OPENAI_API_KEY`/etc. unset → mock-mode that demonstrates the SDK API surface only. |

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **L-01 → L-15** carry-forward: package name `wbauth`, public TS API surface `import { sign, Identity, createSignedFetch, applyTo } from "wbauth"`, camelCase TS / snake_case wire, ≤50 LOC adapters, wraps `cloudflare/web-bot-auth` 0.1.3 (don't reimplement RFC 9421), `spec/test-vectors/` is the cross-language oracle, Worker URL `https://wbauth.silov801.workers.dev` for live demos, Cloudflare research verifier as conformance oracle for smoke tests.
- **D-58:** TS SDK ships signer + adapters only — **NO `inspect()` port**. Public surface = `sign`, `Identity` (with `loadOrGenerate`, `fromTestKey`, `kid` accessor, `exportJwks`, `rotate`), `createSignedFetch`, `applyTo`.
- **D-59:** TS Identity API mirrors Python: `Identity.loadOrGenerate(path, { signatureAgentUrl, userAgent? })`, `Identity.fromTestKey(signatureAgentUrl)`, `identity.kid`, `identity.exportJwks()`, `identity.rotate()`.
- **D-60:** Single on-disk key format works in both SDKs (Python writes, TS reads, or vice-versa).
- **D-61:** `createSignedFetch(identity)` returns a `typeof fetch` wrapper. Wraps `globalThis.fetch`.
- **D-62:** `applyTo(page, identity)` is async, registers `page.route("**/*", handler)`, signs via `wbauth.sign()`, calls `route.continue({ headers })`.
- **D-63:** No `undici` Dispatcher in v1.
- **D-64:** Vitest + same `spec/test-vectors/` JSON files. Cross-language byte-equal headers.
- **D-65:** **NO live Playwright browser tests in CI.** Mock `Page`/`Route` in vitest.
- **D-66:** Cross-language Identity round-trip test: Python `wbauth keygen` → TS `Identity.loadOrGenerate` → sign vector 01 → assert byte-equal vs Python.
- **D-67:** Three examples: `examples/browser_use_demo.py`, `examples/stagehand_demo.ts`, `examples/openai_agents_demo.py`. All runnable with optional-LLM fallback.
- **D-68:** Top-of-file docstring on each example explaining demo + run command + what's mocked vs real.
- **D-69:** Mock-mode targets `https://wbauth.silov801.workers.dev/agents`. Real-mode (LLM key set) → benign `https://example.com`.
- **D-70:** Examples need NOT pass full Cloudflare verification end-to-end. Phase 1 daily-cron canary handles that.
- **D-71:** **DIST-07 deferred to Phase 5** (not Phase 4).

### Claude's Discretion

- **D-72:** Internal TS module organization (`typescript/src/identity.ts`, `typescript/src/signer.ts`, `typescript/src/adapters/fetch.ts`, etc.). Planner picks based on Phase 1 skeleton.
- **D-73:** Vitest fixture loading mechanism — extend existing `typescript/tests/helpers.ts` from Phase 1.
- **D-74:** Choice between exporting from `wbauth` root vs subpath `wbauth/adapters` — match Python's `from wbauth.adapters import WebBotAuth` ergonomics where reasonable; TS-idiomatic flat exports otherwise.
- **D-75:** Example file headers / preamble style.

### Deferred Ideas (OUT OF SCOPE)

- TS `inspect()` port → v1.x. Trigger: 5+ TS users ask OR a Stagehand integration explicitly needs in-process policy.
- TS `undici` Dispatcher → v1.x. Trigger: Stagehand or Browser Use TS users specifically.
- TS CLI binary `wbauth` for Node → Phase 5 or v1.x. Phase 4 ships SDK only.
- DIST-07 (upstream PRs) → **Phase 5**, actively scheduled.
- TS-side `wbauth verify` CLI equivalent → N/A in v1.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ADAPT-04 | TS `fetch` adapter — `createSignedFetch(identity)` returns a wrapped `fetch` with identical signature semantics | §3 below — ≤50 LOC concrete code |
| ADAPT-05 | TS Playwright integration helper — `applyTo(page, identity)` mirroring Python | §4 below — ≤50 LOC concrete code with mock test pattern |
| DIST-04 | Working integration recipe + tested example for Browser Use (`examples/browser_use_demo.py`) | §6 below — full runnable script |
| DIST-05 | Working integration recipe + tested example for Stagehand (`examples/stagehand_demo.ts`) | §7 below — full runnable script |
| DIST-06 | Working integration recipe + tested example for Playwright + OpenAI Agents SDK (`examples/openai_agents_demo.py`) | §8 below — full runnable script |

ADAPT-06 (byte-equal vector conformance) is implicit — covered for TS adapters via the vitest pattern in §9.
ADAPT-07 (≤50 LOC of glue) is enforced by the concrete code in §3 and §4.
IDENT-04 was already satisfied for Python in Phase 1; the cross-language Identity round-trip test in §5 extends it to TS.

## Standard Stack

### Core (already installed in `typescript/`)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `web-bot-auth` | 0.1.3 (npm; pub 2026-03-09) | RFC 9421 + Web Bot Auth signing primitives | Cloudflare-vendored reference impl; subpath export `web-bot-auth/crypto` exposes `signerFromJWK`. **Already a dep of `typescript/package.json`.** [VERIFIED: `npm view web-bot-auth version` → 0.1.3, modified 2026-03-09] |
| `tsup` | 8.5.1 | ESM+CJS+`.d.ts` bundling | Already configured (`tsup.config.ts`) for dual-format output via `outExtension`. [VERIFIED: `npm view tsup version` → 8.5.1] |
| `vitest` | 4.1.5 | Unit tests, fixture loader | Already configured. [VERIFIED: `npm view vitest version` → 4.1.5] |
| `@types/node` | ^20 | Type defs for `node:crypto`, `node:fs`, `node:path` | Already in devDependencies. |
| `typescript` | ^6 | Compiler | Already in devDependencies; tsconfig has `target: ES2022`, `module: ESNext`, `strict: true`. |
| `@biomejs/biome` | ^2 | Lint + format | Already configured. |

### New Dev Dependency (Phase 4)

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `@playwright/test` (or `playwright`) | 1.59.1 | **Type imports only** — `Page`, `Route`, `Request` types for `applyTo` signature; no browser binaries needed | Required so `adapters/playwright.ts` can type its arg as `Page`. Add as **`peerDependency` + `devDependency`** so end users only install it if they actually use the Playwright adapter. **Do not add as `dependencies`** — would force every fetch-only consumer to download Playwright. [VERIFIED: `npm view playwright version` → 1.59.1] |

### Runtime / Build

| Tool | Version | Notes |
|------|---------|-------|
| **Node** | 20 LTS minimum (per root `package.json` `engines.node: ">=20"`) | `web-bot-auth` 0.1.3 needs Node 18+ for native Ed25519 in WebCrypto, but our root requires 20+. Confirmed. |
| `npm` | ≥10 | Workspaces driver; `typescript/` is a workspace. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `node:crypto` for PEM→JWK | `jose` 5.x by panva | `jose` works but adds ~150KB. Node stdlib is zero-dep and verified to produce identical JWK (see §2). **Reject `jose`.** |
| Native `fetch` | `axios`, `node-fetch`, `undici` | Native is in Node 20+. Adding any of these forces a dep on consumers. **Reject.** Already locked by D-63 + STACK.md "Don't use `axios`/`node-fetch`". |
| `@playwright/test` | `playwright` (lighter) | `playwright` is fine; only need type exports. We import `import type { Page, Route, Request } from "playwright"` — types-only import, zero runtime cost. **Use `playwright` as peerDep + devDep.** |
| Per-vector parametrized vitest | `vitest --workspace` | Overkill for 5 vectors. The existing `for (const v of vectors) it(...)` loop in `tests/vectors.test.ts` is the right pattern. |

**Installation (delta from Phase 1 `typescript/package.json`):**

```jsonc
// typescript/package.json — additions
{
  "devDependencies": {
    "playwright": "^1.59"  // type-only at compile, used in adapters/playwright tests via mocks
  },
  "peerDependencies": {
    "playwright": "^1"     // signal to consumers: install only if you use applyTo
  },
  "peerDependenciesMeta": {
    "playwright": { "optional": true }
  }
}
```

**Version verification (run before Plan 01 commit):**

```bash
npm view web-bot-auth version          # expect 0.1.3
npm view playwright version             # expect 1.59.x or newer
npm view tsup version                   # expect 8.5.x
npm view vitest version                 # expect 4.1.x
```

---

## §1 — `web-bot-auth` 0.1.3 npm: Sign-Side API Surface

This section is the single authoritative reference for the planner. Everything below is verified against the **installed** `node_modules/web-bot-auth/dist/index.d.ts` and the official README.

### 1.1 Public exports the TS signer needs

```typescript
// From "web-bot-auth"
import {
  signatureHeaders,                          // async sign helper
  REQUEST_COMPONENTS,                        // ["@authority", "signature-agent"]
  REQUEST_COMPONENTS_WITHOUT_SIGNATURE_AGENT, // ["@authority"]
  HTTP_MESSAGE_SIGNATURE_TAG,                // "web-bot-auth"
  generateNonce,                             // returns base64 NONCE_LENGTH_IN_BYTES = 64
  type SignatureParams,
  type SignatureHeaders,
} from "web-bot-auth";

// From "web-bot-auth/crypto"
import {
  signerFromJWK,                             // (jwk: JsonWebKey) => Promise<Signer>
  jwkToKeyID,                                // re-export of jsonwebkey-thumbprint
  Ed25519Signer,                             // class — has .keyid (= JWK thumbprint) and .alg
} from "web-bot-auth/crypto";
```

**Source:** `node_modules/web-bot-auth/dist/index.d.ts` lines 1–59 (verified live 2026-05-10).

### 1.2 `signatureHeaders` signature

```typescript
declare function signatureHeaders<T extends RequestLike | ResponseLike | ResponseRequestPair>(
  message: T,
  signer: Signer,
  params: SignatureParams,
): Promise<SignatureHeaders>;

interface SignatureParams {
  created: Date;       // REQUIRED — creation timestamp
  expires: Date;       // REQUIRED — expiration timestamp
  nonce?: string;      // Optional — defaults to generateNonce() (64 random bytes b64)
  key?: string;        // Optional — Signature label (default "sig1")
  components?: Component[];  // Optional — overrides smart default
}

type SignatureHeaders = {
  Signature: string;          // "sig1=:<base64-sig>:"
  "Signature-Input": string;  // 'sig1=("@authority" "signature-agent");created=...;expires=...;keyid="...";alg="ed25519";nonce="...";tag="web-bot-auth"'
};
```

### 1.3 Default `components` behavior (CRITICAL — matches Python `DEFAULT_COMPONENTS`)

If `params.components` is **not provided**, `web-bot-auth` 0.1.3 picks based on whether the request has a `signature-agent` header:

- **`signature-agent` header present** → `REQUEST_COMPONENTS = ["@authority", "signature-agent"]`
- **No `signature-agent` header** → `REQUEST_COMPONENTS_WITHOUT_SIGNATURE_AGENT = ["@authority"]`

This matches Python's `DEFAULT_COMPONENTS = ("@authority", "signature-agent")` because the TS signer **must always pre-set Signature-Agent before calling `signatureHeaders`** (Python does the same — `signer.py` line 143). Result: byte-equal default components.

**For POST/PUT/PATCH with body, we must explicitly pass `components: ["@authority", "signature-agent", "content-digest"]`** to match Python's `_components_for(method, has_body=True)`. This is **identical to** the existing pattern already used in `typescript/tests/vectors.test.ts` (lines 65–80) for vector 02.

### 1.4 Concrete TS `wbauth.sign()` (mirrors Python `signer.py`)

```typescript
// typescript/src/signer.ts
import {
  signatureHeaders,
  REQUEST_COMPONENTS,
  type SignatureParams,
} from "web-bot-auth";
import type { Identity } from "./identity.js";
import type { NormalizedRequest } from "./normalized-request.js";

const WEB_BOT_AUTH_TAG = "web-bot-auth";  // Pitfall 6 — never change
const DEFAULT_LABEL = "sig1";
const DEFAULT_EXPIRES_SECONDS = 60;
const DIGEST_METHODS = new Set(["POST", "PUT", "PATCH"]);

export interface SignatureHeaders {
  signature: string;
  signatureInput: string;
  signatureAgent: string;
}

export interface SignOptions {
  created?: Date;
  expiresAfterSeconds?: number;
  nonce?: string;
  label?: string;
}

/** Components selector — mirrors Python `_components_for`. */
function componentsFor(method: string, hasBody: boolean): string[] {
  const base = ["@authority", "signature-agent"];
  if (hasBody && DIGEST_METHODS.has(method.toUpperCase())) {
    base.push("content-digest");
  }
  return base;
}

export async function sign(
  request: NormalizedRequest,
  identity: Identity,
  opts: SignOptions = {},
): Promise<SignatureHeaders> {
  // 1. Defensive https:// check (Identity ctor enforces too — Pitfall 1).
  if (!identity.signatureAgentUrl.startsWith("https://")) {
    throw new Error(
      `signature_agent_url must be https://, got: ${identity.signatureAgentUrl}`,
    );
  }

  // 2. Set Signature-Agent header. RFC 8941 string in double quotes.
  const signatureAgentHeader = `"${identity.signatureAgentUrl}"`;
  request.headers["Signature-Agent"] = signatureAgentHeader;

  // 3. Defaults.
  const created = opts.created ?? new Date();
  const expiresAfterSeconds = opts.expiresAfterSeconds ?? DEFAULT_EXPIRES_SECONDS;
  const expires = new Date(created.getTime() + expiresAfterSeconds * 1000);
  const label = opts.label ?? DEFAULT_LABEL;

  // 4. Components based on body presence.
  const hasBody = request.body !== null && request.body !== undefined;
  const components = componentsFor(request.method, hasBody);

  // 5. Build a Web `Request` for web-bot-auth's `signatureHeaders`.
  const headers = new Headers();
  for (const [k, v] of Object.entries(request.headers)) headers.set(k, v);
  const init: RequestInit = { method: request.method, headers };
  if (hasBody) init.body = request.body!;
  const req = new Request(request.url, init);

  // 6. Delegate. The signer is the active key's signer (see Identity below).
  const params: SignatureParams = {
    created,
    expires,
    key: label,
    components,
    ...(opts.nonce !== undefined ? { nonce: opts.nonce } : {}),
    // tag is hard-coded to "web-bot-auth" by signatureHeaders() automatically
    // when called via the "web-bot-auth" entry point (vs raw http-message-sig).
  };
  const result = await signatureHeaders(req, identity._signer(), params);

  // 7. Mutate request.headers (mirror Python signer behavior).
  request.headers["Signature"] = result.Signature;
  request.headers["Signature-Input"] = result["Signature-Input"];

  return {
    signature: result.Signature,
    signatureInput: result["Signature-Input"],
    signatureAgent: signatureAgentHeader,
  };
}
```

**LOC count:** ~50 lines of meaningful code. Not glue, but not far off — this is the wrapping function, not the adapters. Adapters in §3 and §4 are each ≤50 LOC of glue per ADAPT-07.

**Verified byte-equal pattern:** This is exactly the pattern `typescript/tests/vectors.test.ts` already uses (lines 35–95) — extending it from a one-shot test into a permanent module is mechanical.

---

## §2 — TS `Identity` (Reads Python's PKCS8 PEM File)

### 2.1 Python's on-disk format (the source-of-truth)

`python/src/wbauth/identity.py` line 282–293:

```python
key = Ed25519PrivateKey.generate()
pem = key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
os.write(fd, pem)
```

**Format:** PKCS8 NoEncryption PEM. Default extension `.pem`. Default path `~/.config/wbauth/key.pem`. Mode 0o600.

The on-disk file does **NOT** contain `signature_agent_url` — that's a runtime constructor argument in both Python and TS. (Python `load_or_generate(path, *, signature_agent_url, user_agent=None)`.)

### 2.2 PEM → JWK in pure Node stdlib (VERIFIED)

```bash
$ node -e "
const { createPrivateKey } = require('node:crypto');
const pem = '-----BEGIN PRIVATE KEY-----\nMC4CAQAwBQYDK2VwBCIEIJ+DYvh6SEqVTm50DFtMDoQikTmiCqirVv9mWG9qfSnF\n-----END PRIVATE KEY-----';
const jwk = createPrivateKey(pem).export({ format: 'jwk' });
console.log(JSON.stringify(jwk, null, 2));
"
{
  "crv": "Ed25519",
  "d": "n4Ni-HpISpVObnQMW0wOhCKROaIKqKtW_2ZYb2p9KcU",
  "x": "JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bs",
  "kty": "OKP"
}
```

**This is byte-identical to the JWK fields in `spec/test-vectors/01-basic-get/input.json`** (kty, crv, d, x). [VERIFIED: live `node` execution 2026-05-10 against the RFC 9421 Appendix B.1.4 test key in PKCS8 PEM form.]

**Implication:** No `jose`, no `@panva/jose`, no extra dep. Node 20+ stdlib `node:crypto` is sufficient.

### 2.3 Concrete TS `Identity` class

```typescript
// typescript/src/identity.ts
import { createPrivateKey, generateKeyPairSync } from "node:crypto";
import { existsSync, mkdirSync, openSync, readFileSync, writeFileSync, closeSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { homedir } from "node:os";
import { signerFromJWK, jwkToKeyID } from "web-bot-auth/crypto";
import type { Signer } from "http-message-sig";

const DEFAULT_KEY_PATH = resolve(homedir(), ".config", "wbauth", "key.pem");

// RFC 9421 Appendix B.1.4 test key — NEVER use in production.
const TEST_KEY_JWK = {
  kty: "OKP" as const,
  crv: "Ed25519" as const,
  d: "n4Ni-HpISpVObnQMW0wOhCKROaIKqKtW_2ZYb2p9KcU",
  x: "JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bs",
};

export interface IdentityOptions {
  signatureAgentUrl: string;
  userAgent?: string;
}

export interface KeyPair {
  privateJwk: JsonWebKey;  // includes "d", used to mint signer
  publicJwk: JsonWebKey;   // {kty, crv, x, kid} — what exportJwks returns per-key
  kid: string;              // JWK thumbprint per RFC 7638
  signer: Signer;           // pre-resolved web-bot-auth Signer
}

export class Identity {
  private _active: KeyPair;
  private _retiring: KeyPair | null;
  readonly signatureAgentUrl: string;
  readonly userAgent: string | undefined;

  private constructor(active: KeyPair, opts: IdentityOptions, retiring: KeyPair | null = null) {
    if (!opts.signatureAgentUrl.startsWith("https://")) {
      throw new Error(`signatureAgentUrl must be https://, got: ${opts.signatureAgentUrl}`);
    }
    this._active = active;
    this._retiring = retiring;
    this.signatureAgentUrl = opts.signatureAgentUrl;
    this.userAgent = opts.userAgent;
  }

  get kid(): string { return this._active.kid; }
  _signer(): Signer { return this._active.signer; }  // module-internal, used by sign()

  exportJwks(): { keys: JsonWebKey[] } {
    const keys = [this._active.publicJwk];
    if (this._retiring) keys.push(this._retiring.publicJwk);
    return { keys };
  }

  async rotate(newPath: string = DEFAULT_KEY_PATH): Promise<Identity> {
    const newPair = await generateKeypairTo(newPath);
    return new Identity(newPair, { signatureAgentUrl: this.signatureAgentUrl, userAgent: this.userAgent }, this._active);
  }

  static async loadOrGenerate(path: string = DEFAULT_KEY_PATH, opts: IdentityOptions): Promise<Identity> {
    const resolved = resolve(path.replace(/^~/, homedir()));
    const pair = existsSync(resolved) ? await loadKeypair(resolved) : await generateKeypairTo(resolved);
    return new Identity(pair, opts);
  }

  static async fromTestKey(signatureAgentUrl: string): Promise<Identity> {
    const pair = await keyPairFromJwk(TEST_KEY_JWK);
    return new Identity(pair, { signatureAgentUrl });
  }

  // Redaction (mirror Python IDENT-08).
  toString(): string { return `Identity(kid=${this.kid}, sig_agent=${this.signatureAgentUrl}, private_key=REDACTED)`; }
  // Node REPL inspection
  [Symbol.for("nodejs.util.inspect.custom")](): string { return this.toString(); }
}

// ---- helpers (module-private) ----
async function keyPairFromJwk(privateJwk: JsonWebKey): Promise<KeyPair> {
  const publicOnly: JsonWebKey = { kty: privateJwk.kty, crv: privateJwk.crv, x: privateJwk.x };
  const kid = await jwkToKeyID(publicOnly);
  const signer = await signerFromJWK(privateJwk);
  return { privateJwk, publicJwk: { ...publicOnly, kid }, kid, signer };
}

async function loadKeypair(path: string): Promise<KeyPair> {
  // POSIX permission check (mirror Python — refuse wider-than-0o600).
  if (process.platform !== "win32") {
    const mode = statSync(path).mode & 0o777;
    if ((mode & 0o077) !== 0) {
      throw new Error(`Key file ${path} has mode ${mode.toString(8)}; expected 0o600. Fix: chmod 600 ${path}`);
    }
  } else {
    process.emitWarning(`Windows: file permissions on ${path} cannot be enforced via POSIX mode.`);
  }
  const pem = readFileSync(path, "utf8");
  const jwk = createPrivateKey(pem).export({ format: "jwk" }) as JsonWebKey;
  if (jwk.kty !== "OKP" || jwk.crv !== "Ed25519") {
    throw new TypeError(`Expected Ed25519, got kty=${jwk.kty}, crv=${jwk.crv}`);
  }
  return keyPairFromJwk(jwk);
}

async function generateKeypairTo(path: string): Promise<KeyPair> {
  const dir = dirname(path);
  mkdirSync(dir, { recursive: true });
  if (existsSync(path)) throw new Error(`Key already exists at ${path}; refuse overwrite`);
  const { privateKey } = generateKeyPairSync("ed25519");
  const pem = privateKey.export({ format: "pem", type: "pkcs8" }) as string;
  // Race-free 0o600 creation: openSync with O_WRONLY|O_CREAT|O_EXCL + mode.
  const fd = openSync(path, "wx", 0o600);  // "wx" = O_WRONLY|O_CREAT|O_EXCL
  try { writeFileSync(fd, pem); } finally { closeSync(fd); }
  const jwk = privateKey.export({ format: "jwk" }) as JsonWebKey;
  return keyPairFromJwk(jwk);
}
```

**Notes on this implementation:**

1. **Cross-language file format match.** Python writes via `serialization.PrivateFormat.PKCS8 + NoEncryption`; this writes via Node's `{ format: "pem", type: "pkcs8" }` (no encryption). Both produce identical PKCS8 NoEncryption PEM. **Verified**: the same PEM file Python wrote for the test key produces the same JWK in Node. Round-trip safe.

2. **`fs.openSync(path, "wx", 0o600)` is the Node equivalent of Python's `os.open(path, O_WRONLY|O_CREAT|O_EXCL, 0o600)`.** The `"wx"` flag = "write, fail if exists" = `O_WRONLY|O_CREAT|O_EXCL`. The mode arg is honored on POSIX. Race-free.

3. **`jwkToKeyID`** is exported by `web-bot-auth/crypto` (it's the re-export of `jsonwebkey-thumbprint`). Returns the same RFC 7638 base64url-no-pad thumbprint Python computes. **Verified**: Python kid for the test key = `poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U`; the README of `web-bot-auth` (line 50 of dist) shows `Ed25519Signer.keyid` produces the same string for the same key.

4. **Why `_signer()` is exposed module-internally.** The `signer.ts` calls `identity._signer()` to get the resolved `Signer` object. Underscore-prefix matches Python's `_active` convention; in TS this is just naming — there's no real privacy. If we want stricter encapsulation, use a `WeakMap` or a `friend` symbol; not worth the complexity for v1.

5. **Redaction.** Override `toString()` AND register `Symbol.for("nodejs.util.inspect.custom")` so `console.log(identity)` shows REDACTED. Mirrors Python `__repr__`.

6. **No CLI in TS (deferred).** `Identity.loadOrGenerate` works programmatically. Users who want a CLI run the Python `wbauth keygen` (single-file format = single source of truth).

---

## §3 — `createSignedFetch` (≤50 LOC)

```typescript
// typescript/src/adapters/fetch.ts
// Drop-in fetch wrapper. Signs every outgoing request via wbauth.sign().
// Stateless: holds only `identity` ref. Mirrors Python WebBotAuth (httpx_auth.py).
import { sign } from "../signer.js";
import { ensureContentDigest } from "./_utils.js";
import type { Identity } from "../identity.js";

export function createSignedFetch(identity: Identity): typeof fetch {
  return async function signedFetch(
    input: RequestInfo | URL,
    init: RequestInit = {},
  ): Promise<Response> {
    // Resolve url + method.
    const req = new Request(input, init);
    const method = req.method;
    const url = req.url;

    // Read body bytes if any. Request consumes its body once; clone first.
    let body: Uint8Array | null = null;
    if (req.body) {
      const buf = await req.clone().arrayBuffer();
      body = buf.byteLength > 0 ? new Uint8Array(buf) : null;
    }

    // Build mutable headers dict from the Request.
    const headers: Record<string, string> = {};
    req.headers.forEach((value, key) => { headers[key] = value; });

    // Auto-content-digest for POST/PUT/PATCH (mirror Python ensure_content_digest).
    ensureContentDigest(method, headers, body);

    // Sign via wbauth.sign() — mutates `headers` to add Signature*, Signature-Agent.
    await sign({ method, url, headers, body }, identity);

    // Conditional UA (mirror Python adapter behavior).
    if (identity.userAgent && !Object.keys(headers).some(k => k.toLowerCase() === "user-agent")) {
      headers["User-Agent"] = identity.userAgent;
    }

    // Build the actual outgoing fetch with signed headers.
    return fetch(url, { ...init, method, headers, body: body ?? undefined });
  };
}
```

**LOC:** ~32 lines of code (excluding comments + imports). Well under 50.

**Compatible with `typeof fetch`:** Returns `(input, init?) => Promise<Response>`, matching the global `fetch` signature.

```typescript
// typescript/src/adapters/_utils.ts (mirror Python _utils.py)
const DIGEST_METHODS = new Set(["POST", "PUT", "PATCH"]);

export function ensureContentDigest(
  method: string,
  headers: Record<string, string>,
  body: Uint8Array | null,
): void {
  if (!body || body.byteLength === 0) return;
  if (!DIGEST_METHODS.has(method.toUpperCase())) return;
  if (Object.keys(headers).some(k => k.toLowerCase() === "content-digest")) return;
  // SHA-256 over body bytes. Use Web Crypto for cross-runtime compat.
  const hash = require("node:crypto").createHash("sha256").update(body).digest("base64");
  headers["Content-Digest"] = `sha-256=:${hash}:`;
}
```

**LOC:** ~12 lines. Note: keep `node:crypto` import as `require()` form to avoid an `await import` in a sync function. (Or convert to async — but Python's `ensure_content_digest` is sync, and matching the Python interface keeps mental model consistent.) Alternative: top-level `import { createHash } from "node:crypto"` and remove the `require`. Planner picks based on bundler emit.

---

## §4 — `applyTo(page, identity)` + Vitest Mock Pattern (≤50 LOC)

### 4.1 `applyTo` — concrete code

```typescript
// typescript/src/adapters/playwright.ts
// Async helper: registers page.route("**/*", handler) signing every request.
// PITFALL: Call attach BEFORE the first goto/click that should produce signed requests.
// PITFALL: page.route covers sub-frames by default; for Service-Worker sites,
//          set serviceWorkers="block" on the BrowserContext (Playwright option).
import type { Page, Route, Request as PWRequest } from "playwright";
import { sign } from "../signer.js";
import { ensureContentDigest } from "./_utils.js";
import type { Identity } from "../identity.js";

export async function applyTo(page: Page, identity: Identity): Promise<void> {
  await page.route("**/*", async (route: Route, request: PWRequest) => {
    const headers = await request.allHeaders();  // Record<string,string>
    const postData = request.postDataBuffer();
    const body = postData ? new Uint8Array(postData) : null;

    ensureContentDigest(request.method(), headers, body);

    await sign(
      { method: request.method(), url: request.url(), headers, body },
      identity,
    );

    if (identity.userAgent && !Object.keys(headers).some(k => k.toLowerCase() === "user-agent")) {
      headers["User-Agent"] = identity.userAgent;
    }

    await route.continue({ headers });
  });
}
```

**LOC:** ~22 lines. Well under 50.

### 4.2 Vitest mock pattern (no live browser; mirrors Python AsyncMock pattern)

The Python tests use `unittest.mock.AsyncMock` for `Route`/`Request`/`Page`. For vitest the equivalent is `vi.fn()` returning resolved promises. Pattern:

```typescript
// typescript/tests/adapters/playwright.test.ts
import { describe, expect, it, vi } from "vitest";
import { Identity } from "../../src/identity.js";
import { applyTo } from "../../src/adapters/playwright.js";

function fakePage() {
  // Captures the handler that applyTo registers, so we can invoke it manually.
  let registeredHandler: ((route: any, request: any) => Promise<void>) | null = null;
  const route = vi.fn(async (pattern: string, handler: any) => {
    registeredHandler = handler;
  });
  return {
    page: { route } as any,
    invoke: async (mockRoute: any, mockRequest: any) => {
      if (!registeredHandler) throw new Error("applyTo did not call page.route");
      await registeredHandler(mockRoute, mockRequest);
    },
  };
}

describe("applyTo", () => {
  it("signs the request and calls route.continue with signed headers", async () => {
    const identity = await Identity.fromTestKey("https://example.com/agent.json");
    const { page, invoke } = fakePage();

    await applyTo(page, identity);
    expect(page.route).toHaveBeenCalledWith("**/*", expect.any(Function));

    // Build mock Route and Request.
    const continueSpy = vi.fn(async () => {});
    const mockRoute = { continue: continueSpy };
    const mockRequest = {
      method: () => "GET",
      url: () => "https://crawltest.com/cdn-cgi/web-bot-auth",
      allHeaders: async () => ({}),
      postDataBuffer: () => null,
    };

    await invoke(mockRoute, mockRequest);

    expect(continueSpy).toHaveBeenCalledOnce();
    const [{ headers }] = continueSpy.mock.calls[0]!;
    expect(headers["Signature"]).toMatch(/^sig1=:.+:$/);
    expect(headers["Signature-Input"]).toContain('tag="web-bot-auth"');
    expect(headers["Signature-Agent"]).toBe('"https://example.com/agent.json"');
  });
});
```

**Key insight (mirror Python):** The handler closure that `applyTo` registers is captured by the fake `page.route`, then **invoked** with mock Route + Request. No browser binary, no `@playwright/test` runtime — just types. This pattern is the TS twin of `python/tests/test_adapters_playwright.py` (Phase 2 Plan 01).

### 4.3 Vector conformance test for adapters (mirror Python pattern)

To assert byte-equal headers vs `spec/test-vectors/01-basic-get/expected.json`, the test must inject the vector's fixed `created`/`nonce`. The Python conformance test patches the adapter-module-local `sign` symbol. In TS, the cleanest equivalent is **vi.mock** of the signer module:

```typescript
// typescript/tests/adapters/conformance.test.ts
import { describe, expect, it, vi } from "vitest";
import { Identity } from "../../src/identity.js";
import { loadAllVectors } from "../helpers.js";

// Use a real signer call but with vector-fixed created/nonce/label.
import * as signerModule from "../../src/signer.js";
const realSign = signerModule.sign;

describe("createSignedFetch — byte-equal vs vector 01", () => {
  it("produces byte-equal Signature, Signature-Input, Signature-Agent", async () => {
    const v = loadAllVectors().find(x => x.name === "01-basic-get")!;
    const identity = await Identity.fromTestKey(v.input.identity.signature_agent_url);

    // Patch sign to inject vector's fixed created/nonce/label.
    const spy = vi.spyOn(signerModule, "sign").mockImplementation((req, id, opts) => {
      return realSign(req, id, {
        ...opts,
        created: new Date(v.input.signing_params.created * 1000),
        expiresAfterSeconds: v.input.signing_params.expires_after_seconds,
        nonce: v.input.signing_params.nonce,
        label: v.input.signing_params.label,
      });
    });

    // Mock global fetch to capture outgoing headers.
    const captured: Record<string, string> = {};
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, init) => {
      const h = (init?.headers ?? {}) as Record<string, string>;
      Object.assign(captured, h);
      return new Response(null, { status: 200 });
    });

    // Re-import createSignedFetch AFTER spy is in place so it picks up the patched sign.
    const { createSignedFetch } = await import("../../src/adapters/fetch.js");
    const sf = createSignedFetch(identity);
    await sf(v.input.request.url);

    expect(captured["Signature-Input"]).toBe(v.expected.signature_input_value);
    expect(captured["Signature"]).toBe(v.expected.signature_value);
    expect(captured["Signature-Agent"]).toBe(v.expected.signature_agent_value);

    spy.mockRestore();
    fetchSpy.mockRestore();
  });
});
```

**Caveat about `vi.mock` vs `vi.spyOn`:** Because `adapters/fetch.ts` imports `sign` at module load, you may need `vi.mock("../../src/signer.js", ...)` instead of `vi.spyOn` to ensure the adapter gets the patched function. The planner should pick whichever vitest pattern the existing `tests/vectors.test.ts` style accommodates most cleanly. Both are well-documented vitest patterns. [CITED: vitest.dev/api/vi.html#vi-mock]

---

## §5 — Cross-Language Identity Round-Trip Test (D-66)

**Canonical fixture location:** Generate at runtime in a test fixture; do **NOT** check a real PEM key into the repo (even a test key carries footgun risk). Use the existing `spec/test-vectors/01-basic-get/input.json` private_key_jwk as the source-of-truth source key.

### 5.1 Python side (already shipped; just document)

```bash
# Run once per CI to materialize a PEM keyfile from the test JWK
$ python -c "
import base64, os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

d = base64.urlsafe_b64decode('n4Ni-HpISpVObnQMW0wOhCKROaIKqKtW_2ZYb2p9KcU' + '==')
key = Ed25519PrivateKey.from_private_bytes(d)
pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
fd = os.open('/tmp/wbauth-roundtrip.pem', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
os.write(fd, pem); os.close(fd)
"
```

### 5.2 TS test reads the same file

```typescript
// typescript/tests/identity-roundtrip.test.ts
import { describe, expect, it, beforeAll } from "vitest";
import { execSync } from "node:child_process";
import { unlinkSync, existsSync } from "node:fs";
import { Identity } from "../src/identity.js";

const KEY_PATH = "/tmp/wbauth-roundtrip.pem";

describe("cross-language Identity round-trip (D-66)", () => {
  beforeAll(() => {
    if (existsSync(KEY_PATH)) unlinkSync(KEY_PATH);
    // Materialize the test-key PEM via Python (proves the file format is what Python writes).
    execSync(`python3 -c "
import base64, os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
d = base64.urlsafe_b64decode('n4Ni-HpISpVObnQMW0wOhCKROaIKqKtW_2ZYb2p9KcU' + '==')
key = Ed25519PrivateKey.from_private_bytes(d)
pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
fd = os.open('${KEY_PATH}', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
os.write(fd, pem); os.close(fd)
"`);
  });

  it("loads Python-written PEM and produces same kid as the vector", async () => {
    const identity = await Identity.loadOrGenerate(KEY_PATH, {
      signatureAgentUrl: "https://http-message-signatures-example.research.cloudflare.com/",
    });
    expect(identity.kid).toBe("poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U");
  });

  it("signs vector 01 byte-equal vs Python-side expected.json", async () => {
    // ... uses identity loaded from PEM, asserts byte-equal vs expected.json
  });
});
```

**Implementation note:** This test gates on `python3` being present. CI already has Python (the Python SDK is in the same repo; CI runs both pytest and vitest). The `python3` invocation is hermetic (no third-party deps; uses only `cryptography` which is already a Phase 1 dep).

**Alternative:** Pre-generate the PEM file once and check it into `spec/test-vectors/00-roundtrip/` as `key.pem`. The planner should prefer **runtime generation** (above) because (1) it proves byte-equal Python→TS at every test run, and (2) check-in invites the foot-gun "this is just a test key, surely it's fine to use in prod" misuse pattern.

---

## §6 — `examples/browser_use_demo.py` (DIST-04)

### 6.1 Browser Use 2026 API surface (verified via Context7)

Browser Use v0.7+ exposes:

```python
from browser_use import Agent, Browser, BrowserSession, ChatBrowserUse
# Browser launches a Chromium under the hood; Browser.get_current_page() returns the active Playwright Page.
```

The agent is LLM-driven. Without `OPENAI_API_KEY` (or equivalent) the agent can't reason. **Mock-mode strategy:** skip `Agent` entirely; launch a `BrowserSession` directly, get the underlying Playwright `Page`, attach our signing helper, navigate to our Worker, and assert the signed request fired. This is a direct demo of `attach_signing` working in a Browser-Use-managed browser without needing an LLM.

### 6.2 Concrete `examples/browser_use_demo.py`

```python
"""Browser Use × wbauth demo (DIST-04).

What this demonstrates:
- attach_signing(page, identity) registers a signing handler on a page that
  Browser Use (v0.7+) is driving. Every outgoing request from that page carries
  Signature, Signature-Input, and Signature-Agent.
- Real-mode (with OPENAI_API_KEY): runs a live Browser Use Agent navigating to
  a benign target. The agent's HTTP requests are signed.
- Mock-mode (no OPENAI_API_KEY): skips the Agent and just opens a BrowserSession,
  attaches signing, navigates to our Worker, and prints the signed request.

Run:
    uv pip install browser-use playwright
    playwright install chromium
    # Real mode:  OPENAI_API_KEY=sk-... python examples/browser_use_demo.py
    # Mock mode:  python examples/browser_use_demo.py
"""
import asyncio
import os
from pathlib import Path

from wbauth import Identity, attach_signing

WORKER_URL = "https://wbauth.silov801.workers.dev/agents"
KEY_PATH = Path("~/.config/wbauth/key.pem").expanduser()


async def mock_mode():
    """Open a Playwright page directly via Browser Use's BrowserSession; show signed request."""
    from browser_use import BrowserSession, BrowserProfile
    profile = BrowserProfile(headless=True)
    session = BrowserSession(browser_profile=profile)
    await session.start()
    try:
        page = await session.get_current_page()
        identity = Identity.load_or_generate(
            KEY_PATH,
            signature_agent_url=f"https://wbauth.silov801.workers.dev/.well-known/http-message-signatures-directory/{_kid_or_placeholder()}",
        )
        await attach_signing(page, identity)
        # Log every signed outgoing request.
        page.on("request", lambda req: print(f"[signed] {req.method} {req.url} sig={req.headers.get('signature', '<none>')[:40]}..."))
        await page.goto(WORKER_URL)
        # Give the page a moment so the request log flushes.
        await asyncio.sleep(0.5)
        print(f"\n[demo] Identity kid: {identity.kid}")
        print("[demo] Signed request fired against Worker. Check Worker logs for verify pass/fail.")
    finally:
        await session.kill()


async def real_mode():
    """Run a live Browser Use Agent. Requires OPENAI_API_KEY (or other supported LLM)."""
    from browser_use import Agent, Browser, ChatBrowserUse
    browser = Browser()
    await browser.start()
    try:
        page = await browser.get_current_page()
        identity = Identity.load_or_generate(
            KEY_PATH,
            signature_agent_url=f"https://wbauth.silov801.workers.dev/.well-known/http-message-signatures-directory/{_kid_or_placeholder()}",
        )
        await attach_signing(page, identity)  # MUST come before agent.run()
        agent = Agent(
            task="Open https://example.com and report the page title.",
            llm=ChatBrowserUse(),  # uses OPENAI_API_KEY or BROWSER_USE_API_KEY env
            browser=browser,
        )
        result = await agent.run()
        print(f"[agent] result: {result}")
    finally:
        await browser.stop()


def _kid_or_placeholder() -> str:
    """Best-effort: load the identity to get the real kid; fall back to placeholder."""
    try:
        return Identity.load_or_generate(
            KEY_PATH, signature_agent_url="https://example.invalid/placeholder"
        ).kid
    except Exception:
        return "PLACEHOLDER_KID"


def main():
    if os.getenv("OPENAI_API_KEY") or os.getenv("BROWSER_USE_API_KEY"):
        print("[demo] Real mode (LLM key detected)")
        asyncio.run(real_mode())
    else:
        print("[demo] Mock mode (no LLM key — set OPENAI_API_KEY for real Agent)")
        asyncio.run(mock_mode())


if __name__ == "__main__":
    main()
```

**Notes:**

1. **`page.on("request", ...)` logging in mock-mode is what makes this useful as a demo even without the LLM.** The signed request hits our Worker; `worker logs --tail` then shows what was received.
2. **`attach_signing` MUST be called before `agent.run()`** (Pitfall 6 from Phase 2). Documented in the comment.
3. **`Browser` vs `BrowserSession`:** Per Context7, both work in 2026. `Agent` takes `browser=Browser(...)`; `BrowserSession` is the lower-level handle. We use whichever exposes `get_current_page()` cleanly. Plan 01 author should run-test which one works with current `browser-use` pip version.
4. **Skipping Cloudflare verifier round-trip per D-70.** Demo proves SDK API works; daily canary proves Cloudflare verifier accepts our signatures.

---

## §7 — `examples/stagehand_demo.ts` (DIST-05)

### 7.1 Stagehand v3.3+ API surface (verified via Context7)

```typescript
import { Stagehand } from "@browserbasehq/stagehand";

const stagehand = new Stagehand({
  env: "LOCAL",                      // launches local Chromium via Playwright
  model: "openai/gpt-4o",            // or "openai/gpt-5"
  modelClientOptions: { apiKey: process.env.OPENAI_API_KEY },
});

await stagehand.init();
const page = stagehand.context.pages()[0];  // raw Playwright Page
await page.goto("https://example.com");
await stagehand.act("click the login button");  // requires LLM
await stagehand.close();
```

**Key fact:** `stagehand.context.pages()[0]` returns the **raw Playwright Page**. That's the one we attach signing to.

### 7.2 Concrete `examples/stagehand_demo.ts`

```typescript
/**
 * Stagehand × wbauth demo (DIST-05).
 *
 * What this demonstrates:
 * - applyTo(page, identity) registers a signing handler on Stagehand's
 *   Playwright page. Every outgoing request carries Web Bot Auth signatures.
 * - Real-mode (with OPENAI_API_KEY): runs stagehand.act() with an LLM-driven step.
 * - Mock-mode (no OPENAI_API_KEY): just navigates to our Worker and logs the
 *   signed request via page.on("request", ...).
 *
 * Run:
 *   npm install @browserbasehq/stagehand wbauth playwright
 *   npx playwright install chromium
 *   # Real:  OPENAI_API_KEY=sk-... npx tsx examples/stagehand_demo.ts
 *   # Mock:  npx tsx examples/stagehand_demo.ts
 */
import { Stagehand } from "@browserbasehq/stagehand";
import { Identity, applyTo } from "wbauth";

const WORKER_URL = "https://wbauth.silov801.workers.dev/agents";
const KEY_PATH = `${process.env.HOME}/.config/wbauth/key.pem`;

async function main() {
  const hasLlmKey = !!process.env.OPENAI_API_KEY;
  console.log(`[demo] ${hasLlmKey ? "Real" : "Mock"} mode`);

  const stagehand = new Stagehand({
    env: "LOCAL",
    ...(hasLlmKey ? { model: "openai/gpt-4o" } : {}),
    modelClientOptions: hasLlmKey ? { apiKey: process.env.OPENAI_API_KEY } : undefined,
    localBrowserLaunchOptions: { headless: true },
  });
  await stagehand.init();

  try {
    const page = stagehand.context.pages()[0]!;
    const identity = await Identity.loadOrGenerate(KEY_PATH, {
      signatureAgentUrl: `https://wbauth.silov801.workers.dev/.well-known/http-message-signatures-directory/${await previewKid(KEY_PATH)}`,
    });

    // CRITICAL: attach BEFORE first navigation.
    await applyTo(page, identity);
    page.on("request", req => {
      const sig = req.headers()["signature"];
      if (sig) console.log(`[signed] ${req.method()} ${req.url()} sig=${sig.slice(0, 40)}...`);
    });

    if (hasLlmKey) {
      await page.goto("https://example.com");
      const result = await stagehand.observe("find the main heading");
      console.log("[stagehand] observed:", result);
    } else {
      await page.goto(WORKER_URL);
      await page.waitForTimeout(500);
      console.log(`\n[demo] Identity kid: ${identity.kid}`);
      console.log("[demo] Signed request fired against Worker.");
    }
  } finally {
    await stagehand.close();
  }
}

async function previewKid(path: string): Promise<string> {
  try {
    const id = await Identity.loadOrGenerate(path, { signatureAgentUrl: "https://example.invalid/placeholder" });
    return id.kid;
  } catch { return "PLACEHOLDER_KID"; }
}

main().catch(err => { console.error(err); process.exit(1); });
```

**Notes:**

1. **`stagehand.context.pages()[0]`** is the Playwright Page — confirmed via Context7 docs.
2. **`env: "LOCAL"`** launches local Chromium so this runs without Browserbase. Browserbase is documented as optional path in the docstring but not used by default.
3. **`applyTo` BEFORE first `page.goto`** (Pitfall 6).
4. **Without LLM:** uses `page.goto(WORKER_URL)` + `page.on("request")` — no `stagehand.act/observe/extract` calls (those all need LLM).
5. **Default model `openai/gpt-4o`** is the safe bet per Stagehand README. Could also use `openai/gpt-5` per their newer docs; pick one.

---

## §8 — `examples/openai_agents_demo.py` (DIST-06)

### 8.1 OpenAI Agents SDK custom-client pattern

The SDK uses `AsyncOpenAI` for its own LLM calls; we cannot inject a custom HTTPX client there at the level needed to sign requests TO openai.com (we don't want to anyway — OpenAI doesn't verify signatures).

**The right framing per CONTEXT.md D-67:** the demo shows an Agent with a `@function_tool` that uses `httpx.Client(auth=WebBotAuth(identity))` to make signed HTTP calls to **third-party** sites (e.g., `https://example.com`). The Agent's LLM-driven loop decides to call the tool; the tool emits one signed HTTP request via our SDK.

In mock-mode (no `OPENAI_API_KEY`), we just call the tool function directly without going through the Agent.

### 8.2 Concrete `examples/openai_agents_demo.py`

```python
"""OpenAI Agents SDK × wbauth demo (DIST-06).

What this demonstrates:
- WebBotAuth(identity) + httpx.Client used inside a @function_tool. The Agent's
  tool makes signed HTTP requests to a third-party URL.
- Real-mode (with OPENAI_API_KEY): runs Runner.run() with a real Agent that
  decides to call the tool.
- Mock-mode (no OPENAI_API_KEY): skips the Agent and calls the tool function
  directly to demonstrate the signed request goes out.

Run:
    uv pip install openai-agents httpx
    # Real:  OPENAI_API_KEY=sk-... python examples/openai_agents_demo.py
    # Mock:  python examples/openai_agents_demo.py
"""
import asyncio
import os
from pathlib import Path

import httpx
from wbauth import Identity, WebBotAuth

WORKER_URL = "https://wbauth.silov801.workers.dev/agents"
KEY_PATH = Path("~/.config/wbauth/key.pem").expanduser()


def make_identity() -> Identity:
    # Best-effort: derive kid from the key for the signature_agent_url.
    placeholder = Identity.load_or_generate(
        KEY_PATH, signature_agent_url="https://example.invalid/placeholder"
    )
    return Identity.load_or_generate(
        KEY_PATH,
        signature_agent_url=f"https://wbauth.silov801.workers.dev/.well-known/http-message-signatures-directory/{placeholder.kid}",
    )


def signed_get(url: str, identity: Identity) -> dict:
    """Single signed GET request via httpx + WebBotAuth."""
    with httpx.Client(auth=WebBotAuth(identity)) as client:
        resp = client.get(url, follow_redirects=True)
        return {
            "url": url,
            "status": resp.status_code,
            "kid": identity.kid,
            "signature_input_present": "signature-input" in {k.lower() for k in resp.request.headers},
        }


async def real_mode(identity: Identity):
    from agents import Agent, Runner, function_tool

    @function_tool
    def fetch_page(url: str) -> str:
        """Fetch a URL with a signed Web Bot Auth request and return a summary."""
        result = signed_get(url, identity)
        return f"GET {url} -> HTTP {result['status']} (signed with kid={result['kid']})"

    agent = Agent(
        name="WebBotAuthDemo",
        instructions=(
            "You demonstrate Web Bot Auth signed requests. When asked to fetch a URL, "
            "use the fetch_page tool. Always report the HTTP status."
        ),
        tools=[fetch_page],
    )
    result = await Runner.run(agent, "Fetch https://example.com and tell me the status.")
    print(f"[agent] {result.final_output}")


def mock_mode(identity: Identity):
    print("[demo] Calling signed_get directly (no LLM).")
    result = signed_get(WORKER_URL, identity)
    print(f"[demo] {result}")


def main():
    identity = make_identity()
    if os.getenv("OPENAI_API_KEY"):
        print("[demo] Real mode (OpenAI key detected)")
        asyncio.run(real_mode(identity))
    else:
        print("[demo] Mock mode (no OpenAI key)")
        mock_mode(identity)


if __name__ == "__main__":
    main()
```

**Notes:**

1. **Tool returns a string summary, not raw HTTP.** Agents SDK tools must return JSON-serializable types; string is the safest.
2. **Mock mode bypasses `Runner.run`** entirely — directly invokes `signed_get`. Demonstrates the SDK's API even when the LLM is unavailable.
3. **`WebBotAuth` (Phase 2 adapter) is the integration point.** We're not building anything new; we're showing how Phase 2's `httpx.Auth` adapter slots into Agents SDK tools.
4. **`Runner.run` is async; `signed_get` is sync.** Sync inside async tool is fine — httpx sync client works in an async context. If we wanted to be more idiomatic we could make the tool async with `httpx.AsyncClient(auth=WebBotAuth(identity))`; both adapters work.

---

## §9 — Vitest Scaffolding for Phase 4

### 9.1 New test files (extend Phase 1's `typescript/tests/` pattern)

```
typescript/tests/
├── helpers.ts                       # EXISTING (Phase 1) — vector loader
├── vectors.test.ts                  # EXISTING — Phase 1 cross-language vector tests
├── identity.test.ts                 # NEW — Identity unit tests (loadOrGenerate, fromTestKey, kid, exportJwks, rotate, redaction)
├── identity-roundtrip.test.ts       # NEW — D-66 cross-language Identity round-trip
├── signer.test.ts                   # NEW — sign() unit tests (mirror Python test_signer.py)
└── adapters/
    ├── fetch.test.ts                # NEW — createSignedFetch unit tests + conformance
    ├── playwright.test.ts           # NEW — applyTo with mocked Page/Route
    └── conformance.test.ts          # NEW — adapter byte-equal vs vector 01 (mirror Python test_adapter_conformance.py)
```

### 9.2 vitest.config.ts (no change required)

Existing config already discovers `tests/**/*.test.ts`. Adding `adapters/*.test.ts` files is auto-picked.

### 9.3 Multi-key vector (vector 04) — now extend coverage

`typescript/tests/vectors.test.ts` line 28–31 currently SKIPS multi-key vectors. With Phase 4's `Identity.rotate()` available, write a new test in `identity.test.ts` that:

1. Constructs `Identity.fromTestKey(...)`.
2. Calls `identity.rotate(newPath)` — the active key becomes the new generated one, the old test key becomes the retiring key.
3. Asserts `exportJwks()` returns `{keys: [active, retiring]}` with the retiring key kid matching the original test key kid (`poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U`).
4. Optionally extends to assert byte-equal vs vector 04's `expected.jwks_full`.

### 9.4 New devDependency: `vi.mock` of node-internal modules

If `node:crypto` mocking is needed (for testing the PEM→JWK error paths), use `vi.mock("node:crypto", ...)`. No new dep needed.

---

## §10 — `tsup` Build Audit for Phase 5 npm Publish Prep

Phase 4 doesn't publish (Phase 5 does), but the build must be clean so Phase 5 can `npm publish` without scrambling.

### 10.1 Current `tsup.config.ts` — what it does right

```typescript
{ entry: ["src/index.ts"], format: ["esm", "cjs"], dts: true, outExtension: ... , clean: true }
```

✅ Dual ESM + CJS
✅ Auto `.d.ts`
✅ Correct extensions matching `package.json` exports
✅ Clean build

### 10.2 Phase 4 changes to `tsup.config.ts`

If we want `wbauth/adapters` as a subpath export (D-74), add adapter entries:

```typescript
// typescript/tsup.config.ts
import { defineConfig } from "tsup";

export default defineConfig({
  entry: {
    index: "src/index.ts",
    "adapters/fetch": "src/adapters/fetch.ts",
    "adapters/playwright": "src/adapters/playwright.ts",
  },
  format: ["esm", "cjs"],
  dts: true,
  outExtension({ format }) { return format === "esm" ? { js: ".mjs" } : { js: ".js" }; },
  external: ["playwright"],  // peer dep — never bundle
  clean: true,
});
```

### 10.3 `package.json` exports field for subpath

```jsonc
{
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.mjs",
      "require": "./dist/index.js"
    },
    "./adapters/fetch": {
      "types": "./dist/adapters/fetch.d.ts",
      "import": "./dist/adapters/fetch.mjs",
      "require": "./dist/adapters/fetch.js"
    },
    "./adapters/playwright": {
      "types": "./dist/adapters/playwright.d.ts",
      "import": "./dist/adapters/playwright.mjs",
      "require": "./dist/adapters/playwright.js"
    }
  }
}
```

**Recommendation:** Per D-74, the planner should pick **flat root exports** (`import { sign, Identity, createSignedFetch, applyTo } from "wbauth"`) for v1 simplicity. Subpath exports (above) are a nice-to-have but add bundler-config complexity. **Default to flat.** Subpath can be added in v1.x if users want tree-shake-friendlier imports.

### 10.4 Phase 5 readiness checklist (don't do in Phase 4, but verify nothing prevents)

- [ ] `npm pack --dry-run` from `typescript/` shows ≤1MB tarball with only `dist/` + `README.md` + `package.json`
- [ ] `package.json` `version` bumped + `"prepublishOnly": "npm run build"` script added in Phase 5
- [ ] `npm publish --provenance` from GitHub Actions OIDC (no token rotation) — Phase 5 hardening
- [ ] No `private: true` on `typescript/package.json` (currently none — good)
- [ ] `files: ["dist"]` ensures only built artifacts ship (currently set — good)

---

## Architecture Patterns

### System Architecture Diagram

```
                          ┌─────────────────────────────┐
                          │  User code (TS or Python)   │
                          └──────────────┬──────────────┘
                                         │
                          ┌──────────────▼──────────────┐
                          │   Identity (single class    │
                          │   per language, shared      │
                          │   PKCS8 PEM file format)    │
                          └──────────────┬──────────────┘
                                         │ resolves Signer
                  ┌──────────────────────┴──────────────────────┐
                  ▼                                             ▼
        ┌─────────────────┐                           ┌─────────────────┐
        │  TS sign()      │                           │  Python sign()  │
        │  wraps          │                           │  wraps          │
        │  web-bot-auth   │                           │  http-message-  │
        │  signatureHdrs  │                           │  signatures     │
        └────────┬────────┘                           └────────┬────────┘
                 │                                             │
                 │  emits Signature, Signature-Input,          │
                 │  Signature-Agent (RFC 9421 + WBA)           │
                 │                                             │
                 │  ─── byte-equal oracle gate ───             │
                 │           spec/test-vectors/                │
                 ▼                                             ▼
   ┌─────────────────────────┐               ┌──────────────────────────┐
   │  TS adapters (Phase 4)  │               │  Python adapters (P2)    │
   │  ┌───────────────────┐  │               │  ┌────────────────────┐  │
   │  │ createSignedFetch │  │               │  │ WebBotAuth (httpx) │  │
   │  │     (fetch)       │  │               │  │ WebBotAuthAdapter  │  │
   │  ├───────────────────┤  │               │  │   (requests)       │  │
   │  │ applyTo           │  │               │  │ attach_signing     │  │
   │  │  (Playwright)     │  │               │  │   (Playwright)     │  │
   │  └───────────────────┘  │               │  └────────────────────┘  │
   └────────────┬────────────┘               └────────────┬─────────────┘
                │                                         │
                ▼                                         ▼
   ┌─────────────────────────────────────────────────────────────┐
   │   examples/ (Phase 4 deliverables)                         │
   │   ┌─────────────────────┐  ┌────────────────────────────┐  │
   │   │ stagehand_demo.ts   │  │ browser_use_demo.py        │  │
   │   │ (TS adapter)        │  │ openai_agents_demo.py      │  │
   │   └─────────────────────┘  │ (Python adapters)          │  │
   │                            └────────────────────────────┘  │
   └─────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure (delta from current)

```
typescript/
├── src/
│   ├── index.ts                       # MODIFIED: re-export sign, Identity, createSignedFetch, applyTo, types
│   ├── identity.ts                    # NEW: Identity class
│   ├── normalized-request.ts          # NEW: NormalizedRequest interface (mirror Python dataclass)
│   ├── signer.ts                      # NEW: sign(req, identity, opts) function
│   └── adapters/
│       ├── _utils.ts                  # NEW: ensureContentDigest helper
│       ├── fetch.ts                   # NEW: createSignedFetch (≤50 LOC)
│       └── playwright.ts              # NEW: applyTo (≤50 LOC)
├── tests/
│   ├── helpers.ts                     # EXISTING
│   ├── vectors.test.ts                # EXISTING (Phase 1)
│   ├── identity.test.ts               # NEW
│   ├── identity-roundtrip.test.ts     # NEW (D-66)
│   ├── signer.test.ts                 # NEW
│   └── adapters/
│       ├── fetch.test.ts              # NEW
│       ├── playwright.test.ts         # NEW
│       └── conformance.test.ts        # NEW
├── package.json                       # MODIFIED: + playwright as devDep + peerDep (optional)
├── tsconfig.json                      # NO CHANGE
├── tsup.config.ts                     # NO CHANGE (defer subpath exports per §10)
└── vitest.config.ts                   # NO CHANGE

examples/                              # NEW DIRECTORY at repo root
├── README.md                          # NEW: how to run each demo
├── browser_use_demo.py                # NEW (DIST-04)
├── stagehand_demo.ts                  # NEW (DIST-05)
└── openai_agents_demo.py              # NEW (DIST-06)
```

### Pattern 1: Adapter glue mirrors Python module-by-module
**What:** `adapters/fetch.ts` ↔ `python/.../adapters/httpx_auth.py`; `adapters/playwright.ts` ↔ `python/.../adapters/playwright.py`; `_utils.ts` ↔ `_utils.py`.
**When to use:** Any time Python ships an adapter behavior, the TS twin file mirrors filename + behavior.
**Why:** Cross-language consistency cuts cognitive load when bug-fixing in 6 months. The Python file is the spec; TS implements it.

### Pattern 2: Mock-mode bifurcation in examples
**What:** Each example has a `mock_mode()` function and a `real_mode()` function; `main()` dispatches based on env var presence.
**When to use:** Every demo script.
**Why:** CI smoke can run `python examples/browser_use_demo.py` and assert exit-0 without an LLM key. Demos remain runnable on a fresh box.

### Anti-Patterns to Avoid

- **Adding `jose` or `@panva/jose` for PEM↔JWK conversion.** Node 20+ stdlib `node:crypto` does it and is verified to produce identical bytes.
- **Adding `playwright` as a regular dep.** It's 200MB+ and most consumers won't use the Playwright adapter. Use peerDep.
- **Bundling Playwright into the tsup output.** The peerDep should be marked `external` in tsup config.
- **Live browser launches in CI.** Per D-65; mock everything.
- **Calling LLMs in CI.** Per D-67; mock-mode is the CI path.
- **Putting the Identity round-trip test in `python/tests/`.** It belongs in `typescript/tests/` because it's the TS side proving it can read what Python wrote. Symmetric coverage is unnecessary — Python proved it can read its own format in Phase 1.
- **Reimplementing JWK thumbprint in TS.** `jwkToKeyID` (re-export of `jsonwebkey-thumbprint`) is already a transitive dep of `web-bot-auth`. Use it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| RFC 9421 signing | Custom signature-base canonicalization in TS | `web-bot-auth/signatureHeaders` | Spec is subtle; Cloudflare maintains it. |
| Ed25519 keygen | Custom CSPRNG + curve math | `node:crypto generateKeyPairSync('ed25519')` | Stdlib uses libcrypto; audited. |
| PEM↔JWK for Ed25519 | Manual ASN.1 / DER parsing | `node:crypto createPrivateKey(pem).export({format:'jwk'})` | Stdlib, 1 line, verified byte-equal. |
| JWK thumbprint (RFC 7638) | Manual canonical JSON serialization | `jwkToKeyID` from `web-bot-auth/crypto` | Already a transitive dep; no new install. |
| RFC 9530 content-digest | Custom SHA-256 + structured-fields encoding | Mirror Python `_utils.py` line-by-line in TS | Tiny (~12 LOC) and Python is proven correct via vector 02. |
| Signature label string formatting | Custom regex parser of `Signature-Input` | Already done by `web-bot-auth` — we just pass `key` param | Don't re-canonicalize. |
| Race-free 0o600 file create | Custom sequence of `mkdir`/`stat`/`chmod`/`write` | `fs.openSync(path, "wx", 0o600)` | Single syscall; mirrors Python `O_EXCL`. |
| Playwright type definitions | Custom interfaces for `Page`/`Route` | `import type { Page, Route, Request } from "playwright"` | Types-only import, zero runtime cost. |

**Key insight:** TS Phase 4 should add **zero new runtime dependencies** beyond `web-bot-auth` (already present). Only `playwright` enters as devDep + peerDep. Everything else is Node stdlib + the existing dep tree. This is the strongest "ship and forget" posture.

## Common Pitfalls

### Pitfall 1: TS PEM→JWK using third-party libs may produce different `d` byte-format
**What goes wrong:** A naive `jose`-based PEM→JWK flow may produce a `d` value with different padding or different base64 variant than Python's `cryptography.serialization`.
**Why it happens:** Some libs use base64-with-padding, some use base64url-no-pad. JWK spec says base64url-no-pad, but enforcement varies.
**How to avoid:** Use `node:crypto createPrivateKey(pem).export({format:'jwk'})` — verified to produce base64url-no-pad matching Python.
**Warning signs:** Cross-language test fails with `kid` mismatch, or `signerFromJWK` throws "invalid key length."

### Pitfall 2: Vitest module-level `import { sign }` captures pre-mock reference
**What goes wrong:** Adapter file does `import { sign } from "../signer.js"` at top of file. Test does `vi.spyOn(signerModule, "sign", ...)`. Adapter still calls original because the import binding was resolved at module load.
**Why it happens:** ESM imports are bindings, not references — but when they're imported as named exports, the binding is to the original module's value at link time.
**How to avoid:** Either (a) use `vi.mock("../../src/signer.js", ...)` which hoists before module init, or (b) call sign via `signerModule.sign(...)` so the spy can intercept. Phase 2 Python solved the equivalent problem by patching `<adapter_module>.sign` (the local re-import). TS planner should pick the cleaner of the two patterns.
**Warning signs:** Test that asserts byte-equal vector headers passes for `sign()` direct calls but fails when going through `createSignedFetch`.

### Pitfall 3: `applyTo` handler registered AFTER first goto
**What goes wrong:** `await page.goto("https://example.com"); await applyTo(page, identity);` — the navigation request leaves unsigned.
**Why it happens:** `page.route` only intercepts requests that start AFTER registration.
**How to avoid:** Documented in the docstring; test in `playwright.test.ts` should explicitly assert handler was registered before any goto.
**Warning signs:** First request to a protected site 403s; subsequent requests work.

### Pitfall 4: `request.body` consumed by `new Request(input, init)` clone
**What goes wrong:** `createSignedFetch` builds `new Request(input, init)` to inspect method/headers, then later calls `fetch(url, { body })`. If body was a stream or `ReadableStream`, second consumption throws.
**Why it happens:** `Request` body is read-once; the `clone()` trick works for buffered bodies but not for true streams.
**How to avoid:** `await req.clone().arrayBuffer()` reads it eagerly. Document that `createSignedFetch` does NOT support streaming request bodies in v1 (mirrors Python `WebBotAuth(requires_request_body=True)`).
**Warning signs:** "ReadableStream is locked" error; or POST body silently dropped.

### Pitfall 5: Stagehand `LOCAL` env still requires Chromium installed
**What goes wrong:** User runs `npx tsx examples/stagehand_demo.ts` and gets "browserType.launch: Executable doesn't exist."
**Why it happens:** Playwright requires `npx playwright install chromium` to download the browser.
**How to avoid:** Document in the example header. The mock-mode also needs the browser, since Stagehand always launches one even in mock-mode.
**Warning signs:** Stagehand init fails with executable-not-found.

### Pitfall 6: `web-bot-auth` 0.1.3 default components depend on header presence
**What goes wrong:** TS sign() doesn't pre-set Signature-Agent before calling `signatureHeaders`. The lib then defaults to `["@authority"]` (without signature-agent), and the produced Signature-Input won't include the signature-agent component → byte-equal test fails vs Python.
**Why it happens:** `signatureHeaders` looks at the message's headers to decide its smart default.
**How to avoid:** Always set `request.headers["Signature-Agent"]` BEFORE calling `signatureHeaders` — already done in §1.4 line 24. Pattern matches Python `signer.py` line 143.
**Warning signs:** Vector 01 byte-equal assertion fails; produced Signature-Input is `'sig1=("@authority");...'` instead of `'sig1=("@authority" "signature-agent");...'`.

### Pitfall 7: Browser-use `BrowserSession` vs `Browser` API drift
**What goes wrong:** `browser-use` v0.7+ refactored the public surface; older docs say `Browser()` but newer flows use `BrowserSession()` or vice-versa.
**Why it happens:** Active library; v0.7 release in mid-2025 reorganized things.
**How to avoid:** Run `pip show browser-use` at example-write time and pick whichever class is documented in **the installed version's** README. Prefer the lower-level `BrowserSession` for mock-mode (more control), and `Agent + Browser` for real-mode.
**Warning signs:** `ImportError`, or `AttributeError: 'Browser' has no attribute 'get_current_page'`.

### Pitfall 8: Node `fs.openSync(path, "wx", 0o600)` mode arg ignored on Windows
**What goes wrong:** On Windows, the mode arg is silently no-op. File ends up with default ACL.
**Why it happens:** Windows doesn't have POSIX mode bits.
**How to avoid:** Mirror Python — emit a warning when `process.platform === "win32"`. Documented in §2.3 `loadKeypair`.
**Warning signs:** None at runtime; permissions are just wrong on Windows.

## Code Examples

All code examples in §1–§9 are verified against the installed library shapes (`node_modules/web-bot-auth/dist/index.d.ts`) and the existing Phase 1 test pattern (`typescript/tests/vectors.test.ts`). The examples in §6–§8 are bound to API documentation fetched via Context7 from `/cloudflare/web-bot-auth`, `/microsoft/playwright`, `/browser-use/browser-use`, `/browserbase/stagehand`, `/openai/openai-agents-python` (all High source reputation).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hand-roll RFC 9421 in TS | Use `web-bot-auth` 0.1.3 | Library matured Q1 2026 | Saves 1-2 weeks; eliminates spec-edge-case bugs. |
| `jose` / `@panva/jose` for PEM↔JWK | Node stdlib `node:crypto` `createPrivateKey(...).export({format:'jwk'})` | Node 18+ has it; Node 20 LTS standardized | Zero new dep; verified byte-equal output. |
| `node-fetch` / `axios` | Native global `fetch` | Node 18+ | Zero install; matches `typeof fetch` for drop-in. |
| Per-tier custom polling (browser → page → request) | Single `page.route("**/*", handler)` | Playwright stable since 2021 | One handler covers all subframes; sub-frame coverage is automatic. |
| Stagehand-only Browserbase | Stagehand `env: "LOCAL"` | Stagehand v3 added local mode | Demos run on a laptop without Browserbase account. |

**Deprecated/outdated:**
- TS 5.x → TS 6.x: `tsconfig` `ignoreDeprecations: "6.0"` already set in current config; benign.
- vitest 3 → vitest 4: API surface stable for our usage; no changes needed.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `playwright` peerDep + devDep is sufficient (users won't expect it as a regular dep) | §3, Stack | LOW — npm warns clearly on missing peer; users get clear error. |
| A2 | Stagehand v3.3+ exposes `stagehand.context.pages()[0]` as a raw Playwright Page that supports `page.route()` | §7 | LOW-MEDIUM — verified via Context7 docs for v3.x; if Stagehand wraps it differently in a 4.x release the example breaks. Smoke-test before phase commit. |
| A3 | Browser Use v0.7+ `BrowserSession.get_current_page()` returns a Playwright Page that supports `page.route()` | §6 | LOW-MEDIUM — verified via Context7 docs; Browser Use historically wraps Playwright thinly. Smoke-test in mock-mode before phase commit. |
| A4 | OpenAI Agents SDK `@function_tool` accepts a sync function that returns a string | §8 | LOW — verified via Context7 docs (multiple examples). |
| A5 | The `examples/` directory at repo root is the right location (CONTEXT specifies this path) | §6, §7, §8 | NONE — explicit in D-67. |
| A6 | Worker URL `https://wbauth.silov801.workers.dev/agents` is reachable in mock-mode demos | §6, §7 | LOW — Worker is deployed per Phase 3; verify `curl https://wbauth.silov801.workers.dev/agents` returns 200/4xx (not connection-refused) before phase commit. |
| A7 | `signerFromJWK` accepts the JWK shape `{kty:"OKP",crv:"Ed25519",d:..,x:..}` (no `kid`) | §1, §2 | NONE — verified in `node_modules/web-bot-auth/dist/index.d.ts` and via Cloudflare README example. |
| A8 | The TS `Identity.exportJwks()` JWK key ordering matches the Python `export_jwks()` byte-equal for vector 04 | §9 | MEDIUM — Python uses `serialization.PublicFormat.Raw` then base64url-no-pad; TS uses `node:crypto` JWK export. Both should produce same `x` value (verified for the test key). For multi-key vectors, key ordering in the `keys` array must be `[active, retiring]` in both languages — Python identity.py line 122 confirms; TS identity.ts in §2.3 confirms. Run vector 04 byte-equal in vitest to verify. |

## Open Questions

1. **Should `Identity.loadOrGenerate` accept an `existingJwksPath` for sidecar JWKS file?**
   - What we know: Python CLI `wbauth keygen --jwks-output` writes a sidecar JWKS file (Phase 3 D-51). The Identity object can recompute JWKS from the active keypair, so loading the sidecar is unnecessary for signing. But TS users who want to skip the recomputation might want it.
   - What's unclear: Whether any consumer actually needs this in v1.
   - Recommendation: **Skip in v1.** Keep TS Identity API minimal. If users ask, add `Identity.loadOrGenerate(path, { jwksPath, ... })` in v1.x.

2. **Should `createSignedFetch` accept a `nonce`/`created` override for testing?**
   - What we know: Python WebBotAuth doesn't expose this; tests use `monkeypatch` of the `sign` symbol.
   - What's unclear: Whether test ergonomics in TS warrant exposing it as an option.
   - Recommendation: **Don't expose.** Use `vi.mock` of the signer module (Pitfall 2) — same pattern as Python.

3. **Should the example demos pin specific framework versions?**
   - What we know: `package.json` for examples could pin `@browserbasehq/stagehand@3.3.0`, `browser-use==0.7.x`, `openai-agents==latest`.
   - What's unclear: How aggressively to pin. Tight pinning ages badly; loose pinning lets the example break.
   - Recommendation: **Use minimum versions in docstrings, not lockfiles.** The `examples/` dir does NOT have its own `package.json` or `pyproject.toml`. Add a top-level `examples/README.md` with `pip install browser-use>=0.7,<1` style minimum-version commands.

4. **Should `applyTo` be exposed at root or `wbauth/adapters/playwright`?**
   - What we know: D-74 leaves to Claude. Python uses flat `from wbauth import attach_signing`. CONTEXT.md §specifics shows TS `import { Identity, sign, createSignedFetch, applyTo } from "wbauth"` (root).
   - What's unclear: Whether sub-path imports like `import { applyTo } from "wbauth/adapters/playwright"` are also worth exposing for tree-shake.
   - Recommendation: **Flat root for v1.** Add subpath exports in v1.x if bundle-size complaints surface. Keeps tsup config simpler now.

5. **CRITICAL — Do we ship `examples/` to npm or only keep on GitHub?**
   - What we know: `examples/` at repo root, not under `typescript/`. Currently `typescript/package.json` has `files: ["dist"]` which means npm publish would NOT include `examples/`. Same for the eventual Python package via `pyproject.toml`'s default file selection.
   - What's unclear: Whether we want examples to be visible on npmjs.com (typical place users check before installing).
   - Recommendation: **Don't ship `examples/` in either package.** Link to the GitHub repo `examples/` directory from the README. Standard practice. Keeps the npm tarball small, satisfies HARDEN-01 "small ship surface."

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node ≥20 | TS SDK build, vitest | ✓ | 20+ (root engines) | None — required. |
| `web-bot-auth` 0.1.3 npm | TS sign() | ✓ | 0.1.3 (already installed in node_modules) | None — required. |
| `playwright` npm (≥1.59) | applyTo type import + adapter test mocks | ✓ | 1.59.1 latest | None for type imports; mock tests don't need browser. |
| `python3` with `cryptography` | Identity round-trip test (§5) | ✓ | Already in repo (Phase 1 dep) | Could bake the PEM as a static fixture file, but runtime gen is more honest. |
| `browser-use` pip pkg | `examples/browser_use_demo.py` execution only | UNKNOWN — needs install | n/a | Documented in example docstring; not a CI dep. |
| `@browserbasehq/stagehand` npm | `examples/stagehand_demo.ts` execution only | UNKNOWN — needs install | 3.3.0 | Documented in example docstring; not a CI dep. |
| `openai-agents` pip pkg | `examples/openai_agents_demo.py` execution only | UNKNOWN — needs install | n/a | Documented in example docstring; not a CI dep. |
| `chromium` browser binary | Examples that launch a browser | UNKNOWN — needs `playwright install chromium` | n/a | Documented in example docstring; not a CI dep. Mock-mode in CI: skip the demo execution entirely; vitest covers the adapter logic. |

**Missing dependencies with no fallback:** None blocking Phase 4 deliverables. The framework deps (browser-use, stagehand, openai-agents) are example-runner concerns, not core SDK concerns. Per D-70, examples are not required to pass full Cloudflare verification end-to-end; they demonstrate the SDK API surface.

**Missing dependencies with fallback:** Browser binaries — examples document `playwright install chromium`; if a CI smoke job wants to run them it must include that step. Phase 4 CI only needs to run vitest (no browser).

## Validation Architecture

> Skipped per `.planning/config.json` `workflow.nyquist_validation: false`.

## Security Domain

### Applicable ASVS Categories (Level 1, per `security_asvs_level: 1`)

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | YES | Web Bot Auth signing IS the authentication mechanism. Existing Phase 1 controls (Ed25519 via `web-bot-auth` library, never hand-roll) carry forward. TS adapter MUST NOT log signed headers (would leak Signature-Agent URL — non-secret but operationally sensitive) at INFO/DEBUG. |
| V3 Session Management | NO | No sessions; signature-per-request is stateless. |
| V4 Access Control | NO | SDK is a client; access control is the verifier's responsibility. |
| V5 Input Validation | YES | `Identity.loadOrGenerate(path, opts)` — `signatureAgentUrl` MUST be validated as `https://` (mirror Python `signer.py` line 99). PEM file content validated by Node `createPrivateKey` (rejects malformed). |
| V6 Cryptography | YES | Ed25519 via `node:crypto` (libcrypto-backed) and `web-bot-auth` (libcrypto-backed via WebCrypto Subtle API). **Never hand-roll.** `generateKeyPairSync('ed25519')` uses CSPRNG. PKCS8 NoEncryption format on disk; mode 0o600 enforced via `fs.openSync(path, "wx", 0o600)`. |
| V7 Error Handling & Logging | YES | `Identity.toString()` MUST return REDACTED — the TS Identity in §2.3 implements this via `toString()` + `Symbol.for("nodejs.util.inspect.custom")`. Adapter code MUST NOT log the request body or full headers at production log levels. |
| V8 Data Protection | YES | Private key never crosses module boundary except as `Signer` object (Web Crypto `CryptoKey` — non-extractable post-import via WebCrypto). The PEM file is the only persistence surface. |
| V9 Communication | YES | `signatureAgentUrl` MUST be `https://` — enforced in Identity ctor. Signed requests use whatever transport the user picks (we don't enforce TLS at fetch level — user's responsibility to use https). |

### Known Threat Patterns for {TS SDK + Node 20}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Pickle/serialization injection | T (tampering) | TS doesn't have Python pickle. JSON-only data flow. No mitigation needed beyond not introducing `eval`/`Function`. |
| Key file with permissive mode silently used | I (info disclosure) | `loadKeypair` checks `mode & 0o077` and throws on POSIX (mirror Python). Windows emits warning. |
| Race condition during keygen (TOCTOU on `path.exists`) | T | Use `fs.openSync(path, "wx", 0o600)` — single syscall = race-free. Mirrors Python `os.open(O_EXCL)`. |
| Private key in `console.log(identity)` | I | Override `toString` + `Symbol.for("nodejs.util.inspect.custom")` to return REDACTED. Mirror Python `__repr__`. |
| Body bytes leaked into logs via signed request | I | No logging in adapter glue; user's responsibility for app-level logging. Document in README: "wbauth never logs request bodies." |
| Replay attack on captured signed request | R (repudiation) | Signature includes `created`/`expires`/`nonce`; verifier (Cloudflare) enforces nonce uniqueness within window. Default `expiresAfterSeconds=60` minimizes replay window. |
| Downgrade attack on Signature-Agent URL (`http://`) | T | Identity ctor + sign() defensive re-check both reject non-`https://`. Two-layer guard. |
| Test key used in production | I (info disclosure) — test key is publicly known | Document loudly in `Identity.fromTestKey` docstring; production users use `Identity.loadOrGenerate`. |

## Sources

### Primary (HIGH confidence)
- `node_modules/web-bot-auth/dist/index.d.ts` (read 2026-05-10) — verified API surface
- `node_modules/web-bot-auth/README.md` (read 2026-05-10) — official sign/verify examples
- `node_modules/web-bot-auth/package.json` v0.1.3 (verified `npm view web-bot-auth version`)
- `python/src/wbauth/identity.py` — Python on-disk PEM format source-of-truth
- `python/src/wbauth/signer.py` — Python signer behavior to mirror
- `python/src/wbauth/adapters/{httpx_auth,requests_adapter,playwright,_utils}.py` — Phase 2 adapter shapes
- `spec/test-vectors/01-basic-get/{input,expected}.json` — byte-equal oracle
- `typescript/tests/vectors.test.ts` — existing TS pattern using `web-bot-auth` 0.1.3
- Live `node` execution proving `node:crypto createPrivateKey(pem).export({format:'jwk'})` produces JWK byte-identical to Python's persistence (run 2026-05-10)
- Context7 `/cloudflare/web-bot-auth` (Source Reputation: High; 145 snippets) — sign/verify API
- Context7 `/microsoft/playwright` (Source Reputation: High; 3839 snippets) — Page.route TS API

### Secondary (MEDIUM confidence)
- Context7 `/browser-use/browser-use` (Source Reputation: High; 494 snippets) — Browser Session API patterns
- Context7 `/browserbase/stagehand` (Source Reputation: High; 1481 snippets) — v3 init + Playwright integration
- Context7 `/openai/openai-agents-python` (Source Reputation: High; 913 snippets) — function_tool + Runner.run patterns
- `npm view <pkg>` for version verification of all listed deps

### Tertiary (LOW confidence)
- None — all critical claims verified against installed code or official docs.

## Metadata

**Confidence breakdown:**
- §1 web-bot-auth API: HIGH — verified against installed `dist/index.d.ts` + README + Context7
- §2 Identity (PEM cross-language): HIGH — verified live with Node + Python proving byte-equal JWK
- §3 createSignedFetch: HIGH — straightforward fetch wrapper, mirrors verified Python pattern
- §4 applyTo: HIGH — Playwright `page.route` API stable; mock pattern proven in Phase 2 Python
- §5 round-trip test: HIGH — design follows Python conformance pattern
- §6 Browser Use demo: MEDIUM — bound to current `browser-use` v0.7+ API; verified via Context7 but live install may differ slightly
- §7 Stagehand demo: MEDIUM — bound to current Stagehand v3.3 API; verified via Context7
- §8 OpenAI Agents demo: HIGH — `@function_tool` + `Runner.run` API is stable per multiple Context7 sources
- §9 Vitest scaffolding: HIGH — extends existing Phase 1 pattern
- §10 tsup audit: HIGH — current config is correct; subpath suggestion is optional
- Pitfalls: HIGH — direct ports of Phase 2 Python pitfalls plus 4 new TS-specific ones

**Research date:** 2026-05-10
**Valid until:** 2026-06-10 (30 days for stable libraries; framework demos may need re-verification if `browser-use` or `stagehand` ship a major version in the window)

---

*Phase: 04-typescript-sdk-framework-integrations*
*Researched: 2026-05-10*
