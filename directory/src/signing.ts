// Lazy signer init from the DIRECTORY_PRIVATE_JWK secret (D-42).
//
// The secret is a JSON-stringified JWK with all 5 fields (kty, crv, kid, d, x).
// We parse once per isolate, instantiate the Ed25519 signer once per isolate,
// and reuse both for every read-endpoint signature.
//
// NOTE on imports: web-bot-auth 0.1.3 only exposes two subpath exports
// ("." and "./crypto"). The `directoryResponseHeaders` symbol is re-exported
// from the main entry (it lives in the http-message-sig dependency); the
// `signerFromJWK` symbol is exported from the `/crypto` subpath.
import type { Signer } from "web-bot-auth";
import { signerFromJWK } from "web-bot-auth/crypto";

type DirectoryJwk = {
  kty: string;
  crv: string;
  kid: string;
  x: string;
  d: string;
};

let cachedSigner: Signer | null = null;
let cachedDirectoryJwk: DirectoryJwk | null = null;

export async function getDirectorySigner(privateJwkJson: string): Promise<Signer> {
  if (!cachedSigner) {
    cachedDirectoryJwk = JSON.parse(privateJwkJson) as DirectoryJwk;
    cachedSigner = await signerFromJWK(cachedDirectoryJwk as unknown as JsonWebKey);
  }
  return cachedSigner;
}

/**
 * Public JWKS view of the directory's own key (no `d` field).
 *
 * Per Open Question #1: this is what the no-kid root well-known endpoint
 * returns so external verifiers can discover the directory's signing key.
 */
export function getDirectoryPublicJwks(privateJwkJson: string): {
  keys: Array<{ kty: string; crv: string; kid: string; x: string }>;
} {
  if (!cachedDirectoryJwk) {
    cachedDirectoryJwk = JSON.parse(privateJwkJson) as DirectoryJwk;
  }
  const { kty, crv, kid, x } = cachedDirectoryJwk;
  return { keys: [{ kty, crv, kid, x }] };
}
