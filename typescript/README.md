# wb-auth — Web Bot Auth for TypeScript

[![npm](https://img.shields.io/npm/v/wb-auth?style=flat-square&color=111111&label=npm)](https://www.npmjs.com/package/wb-auth)

Ed25519 [RFC 9421](https://www.rfc-editor.org/rfc/rfc9421) request signing with the IETF
Web Bot Auth profile. Byte-identical to the Python SDK (`pip install wbauth`).

```bash
npm install wb-auth
```

Node ≥ 20. Ships ESM (`import`) and CommonJS (`require`) builds with types.

## Sign `fetch`

```ts
import { Identity, createSignedFetch } from "wb-auth";

const identity = await Identity.loadOrGenerate("~/.config/wbauth/key.pem", {
  signatureAgentUrl: "https://agent.example.com/.well-known/http-message-signatures-directory",
  userAgent: "ExampleAgent/1.0 (+https://agent.example.com)",
});

const signedFetch = createSignedFetch(identity);
await signedFetch("https://example.com/articles/42");
```

- POST/PUT/PATCH bodies get a `Content-Digest` (RFC 9530) that is covered by the signature.
- Retries are safe: stale `Signature*` headers are replaced, never merged.
- `signal`, `redirect`, `credentials`, … from a `Request` input are preserved.

## Sign a Playwright page

```ts
import { chromium } from "playwright";
import { Identity, applyTo } from "wb-auth";

const page = await (await chromium.launch()).newPage();
// Only sign requests to the sites you target — third parties never see your identity.
await applyTo(page, identity, { hosts: ["example.com", "*.example.com"] });
await page.goto("https://example.com");
```

## Low-level

```ts
import { sign } from "wb-auth";

const headers: Record<string, string> = {};
await sign({ method: "GET", url: "https://example.com/", headers, body: null }, identity);
// headers now has Signature, Signature-Input, Signature-Agent
```

`sign()` throws if a POST/PUT/PATCH body has no `Content-Digest` header
(use `createSignedFetch`/`applyTo`, which add it automatically).

## Keys

`Identity.loadOrGenerate(path, opts)` creates an Ed25519 key with mode `0600`
and refuses to load keys readable by others. `identity.exportJwks()` returns
the public JWKS to publish; `identity.rotate()` keeps the previous key in the
JWKS during the overlap window.

See the [repository README](../README.md) for the policy inspector (Python),
CLI and the hosted JWKS directory.
