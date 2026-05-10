/**
 * wbauth: Web Bot Auth (RFC 9421) TypeScript SDK — Phase 4 public surface.
 *
 * Per CONTEXT D-74: flat root exports. Subpath exports (`wbauth/adapters`)
 * are a v1.x optimization, not required for Phase 4.
 *
 * Quickstart:
 *   import { Identity, createSignedFetch } from "wbauth";
 *   const id = await Identity.loadOrGenerate("./key.pem", {
 *     signatureAgentUrl: "https://example.com/.well-known/.../<kid>",
 *   });
 *   const sf = createSignedFetch(id);
 *   const res = await sf("https://api.example.com/data");
 */
export { sign } from "./signer.js";
export type { SignatureHeaders, SignOptions } from "./signer.js";
export { Identity, DEFAULT_KEY_PATH } from "./identity.js";
export type { IdentityOptions, KeyPair } from "./identity.js";
export type { NormalizedRequest } from "./normalized-request.js";
export { createSignedFetch } from "./adapters/fetch.js";
export { applyTo } from "./adapters/playwright.js";

export const VERSION = "0.1.0";
