// Domain-ownership proof for signature_agent_url (2026-10 audit).
//
// Key ownership alone does not prove that the registrant controls the
// domain in `signature_agent_url` / `client_uri` — anyone could register
// "https://openai.com/...". An agent is `domain_verified` only when:
//   (a) the URL is this directory's own hosted JWKS for the kid, or
//   (b) the URL serves a JWKS that contains the registered Ed25519 key (`x`).
export type Fetcher = (input: string, init?: RequestInit) => Promise<Response>;

export interface DomainVerification {
  verified: boolean;
  reason:
    | "hosted_by_directory"
    | "jwks_contains_key"
    | "key_not_published"
    | "invalid_jwks"
    | "unreachable"
    | `http_${number}`;
}

const MAX_BYTES = 64 * 1024;
const TIMEOUT_MS = 3000;

async function readCapped(res: Response, cap: number): Promise<string> {
  const reader = res.body?.getReader();
  if (!reader) return "";
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > cap) {
      await reader.cancel();
      throw new Error("too_large");
    }
    chunks.push(value);
  }
  const buf = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) {
    buf.set(c, off);
    off += c.byteLength;
  }
  return new TextDecoder().decode(buf);
}

export async function verifyDomainOwnership(
  signatureAgentUrl: string,
  kid: string,
  x: string,
  directoryOrigin: string,
  fetcher: Fetcher = (u, i) => fetch(u, i),
): Promise<DomainVerification> {
  const u = new URL(signatureAgentUrl);
  if (
    u.origin === directoryOrigin &&
    u.pathname === `/.well-known/http-message-signatures-directory/${kid}`
  ) {
    return { verified: true, reason: "hosted_by_directory" };
  }
  let res: Response;
  try {
    res = await fetcher(signatureAgentUrl, {
      headers: {
        accept:
          "application/http-message-signatures-directory+json, application/json",
      },
      redirect: "follow",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    return { verified: false, reason: "unreachable" };
  }
  if (!res.ok) return { verified: false, reason: `http_${res.status}` };
  let data: unknown;
  try {
    data = JSON.parse(await readCapped(res, MAX_BYTES));
  } catch {
    return { verified: false, reason: "invalid_jwks" };
  }
  const keys = (data as { keys?: unknown })?.keys;
  if (!Array.isArray(keys)) return { verified: false, reason: "invalid_jwks" };
  const hit = keys.some(
    (k) =>
      k &&
      typeof k === "object" &&
      (k as { kty?: string }).kty === "OKP" &&
      (k as { crv?: string }).crv === "Ed25519" &&
      (k as { x?: string }).x === x,
  );
  return hit
    ? { verified: true, reason: "jwks_contains_key" }
    : { verified: false, reason: "key_not_published" };
}
