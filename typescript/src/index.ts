/**
 * wbauth: Web Bot Auth (RFC 9421) TypeScript SDK — Phase 4 public surface.
 *
 * Per CONTEXT D-74: flat root exports. Subpath exports (`wb-auth/adapters`)
 * are a v1.x optimization, not required for Phase 4.
 *
 * Quickstart:
 *   import { Identity, createSignedFetch } from "wb-auth";
 *   const id = await Identity.loadOrGenerate("./key.pem", {
 *     signatureAgentUrl: "https://example.com/.well-known/.../<kid>",
 *   });
 *   const sf = createSignedFetch(id);
 *   const res = await sf("https://api.example.com/data");
 */

export type { SignScopeOptions } from "./adapters/_utils.js";
export type { SignedFetchOptions } from "./adapters/fetch.js";
export { createSignedFetch } from "./adapters/fetch.js";
export type { ApplyToOptions } from "./adapters/playwright.js";
export { applyTo } from "./adapters/playwright.js";
export type {
	Ed25519SignerBackend,
	IdentityOptions,
	KeyOptions,
	KeyPair,
	PublicJwk,
	Signer,
} from "./identity.js";
export {
	DEFAULT_KEY_PATH,
	Identity,
	KEY_PASSWORD_ENV,
	thumbprint,
	validateSignatureAgentUrl,
} from "./identity.js";
export type { NormalizedRequest } from "./normalized-request.js";
export type { SignatureHeaders, SignOptions } from "./signer.js";
export { normalizeAuthority, sign } from "./signer.js";
export type {
	KeyResolver,
	VerifiedAgent,
	VerifierOptions,
} from "./verifier.js";
export {
	createVerifierMiddleware,
	NonceStore,
	VerificationError,
	Verifier,
} from "./verifier.js";

export const VERSION = "0.4.0";
