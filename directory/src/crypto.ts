// Small crypto helpers shared by the register route (WebCrypto only).

function b64urlEncode(bytes: ArrayBuffer): string {
  let bin = "";
  for (const b of new Uint8Array(bytes)) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64Encode(bytes: ArrayBuffer): string {
  let bin = "";
  for (const b of new Uint8Array(bytes)) bin += String.fromCharCode(b);
  return btoa(bin);
}

/**
 * RFC 7638 JWK thumbprint (SHA-256, base64url) for an Ed25519 OKP key.
 * Required members in lexicographic order: crv, kty, x.
 */
export async function okpThumbprint(jwk: { crv: string; kty: string; x: string }): Promise<string> {
  const canonical = JSON.stringify({ crv: jwk.crv, kty: jwk.kty, x: jwk.x });
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical));
  return b64urlEncode(digest);
}

/** RFC 9530 sha-256 value of `body`, standard base64 (no structured-field colons). */
export async function sha256B64(body: ArrayBuffer): Promise<string> {
  return b64Encode(await crypto.subtle.digest("SHA-256", body));
}

/** Extract the `sha-256=:<b64>:` member of a Content-Digest header. */
export function parseSha256Digest(header: string | null | undefined): string | null {
  if (!header) return null;
  const m = /(?:^|,)\s*sha-256=:([A-Za-z0-9+/]+={0,2}):/.exec(header);
  return m ? m[1] : null;
}

/** Covered component identifiers of the first signature in Signature-Input. */
export function coveredComponents(signatureInput: string | null | undefined): string[] {
  if (!signatureInput) return [];
  const m = /^[^=]+=\(([^)]*)\)/.exec(signatureInput.trim());
  if (!m) return [];
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1].toLowerCase());
}

/** Constant-time string comparison. */
export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
