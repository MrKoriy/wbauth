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
    | "redirect_not_allowed"
    | "forbidden_host"
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

// Hosts we refuse to fetch (SSRF guard): loopback, RFC 1918, link-local,
// CGNAT, ULA, metadata endpoints and bare/internal names.
export function isForbiddenHost(hostname: string): boolean {
  const h = hostname.toLowerCase().replace(/^\[|\]$/g, "").replace(/\.$/, "");
  if (!h.includes(".") && !h.includes(":")) return true; // single-label / intranet
  if (h === "localhost" || h.endsWith(".localhost") || h.endsWith(".local") || h.endsWith(".internal")) {
    return true;
  }
  const v4 = h.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (v4) {
    const [a, b] = [Number(v4[1]), Number(v4[2])];
    return (
      a === 0 || a === 10 || a === 127 || a >= 224 ||
      (a === 100 && b >= 64 && b <= 127) ||
      (a === 169 && b === 254) ||
      (a === 172 && b >= 16 && b <= 31) ||
      (a === 192 && b === 168) ||
      (a === 198 && (b === 18 || b === 19))
    );
  }
  if (h.includes(":")) {
    return (
      h === "::" || h === "::1" || h.startsWith("fc") || h.startsWith("fd") ||
      h.startsWith("fe80") || h.startsWith("::ffff:")
    );
  }
  return false;
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
  if (u.protocol !== "https:" || isForbiddenHost(u.hostname)) {
    return { verified: false, reason: "forbidden_host" };
  }
  let res: Response;
  try {
    res = await fetcher(signatureAgentUrl, {
      headers: {
        accept:
          "application/http-message-signatures-directory+json, application/json",
      },
      // Never follow redirects: an open redirect on the claimed domain would
      // otherwise let an attacker "prove" ownership with a JWKS hosted
      // anywhere (audit #4). The JWKS must be served at the exact URL.
      redirect: "manual",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    return { verified: false, reason: "unreachable" };
  }
  if (res.status >= 300 && res.status < 400) {
    return { verified: false, reason: "redirect_not_allowed" };
  }
  if (res.redirected || (res.url && res.url !== "" && new URL(res.url).origin !== u.origin)) {
    return { verified: false, reason: "redirect_not_allowed" };
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
