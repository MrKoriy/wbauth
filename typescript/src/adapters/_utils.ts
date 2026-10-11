/**
 * Shared adapter helpers (internal — not part of the public surface).
 *
 * Mirror python/src/wbauth/adapters/_utils.py. The signer auto-includes
 * `content-digest` in covered components for any request with a body;
 * adapters call ensureContentDigest() before sign() so that precondition
 * is met. RFC 9530 sha-256 in structured-fields form (`sha-256=:<b64>:`).
 */
import { createHash } from "node:crypto";

/** Default UAs injected by HTTP stacks; an Identity UA should replace them. */
const LIBRARY_DEFAULT_UA = /^(node|undici|node-fetch)(\/|$)/i;

function findHeader(
	headers: Record<string, string>,
	name: string,
): string | undefined {
	const n = name.toLowerCase();
	return Object.keys(headers).find((k) => k.toLowerCase() === n);
}

/**
 * Mutate `headers` in place to add Content-Digest when warranted. No-op if:
 * - body is null/empty,
 * - the request already carries a Content-Digest header (case-insensitive).
 */
export function ensureContentDigest(
	method: string,
	headers: Record<string, string>,
	body: Uint8Array | null,
): void {
	if (!body || body.byteLength === 0) return;
	void method; // any method with a body is covered (DELETE, QUERY, …)
	if (findHeader(headers, "content-digest")) return;
	const b64 = createHash("sha256").update(body).digest("base64");
	headers["Content-Digest"] = `sha-256=:${b64}:`;
}

/**
 * Apply the Identity's User-Agent unless the caller explicitly set a
 * non-library UA. Library defaults (node, undici) are replaced.
 */
export function applyUserAgent(
	headers: Record<string, string>,
	userAgent: string | undefined,
): void {
	if (!userAgent) return;
	const key = findHeader(headers, "user-agent");
	if (key === undefined) {
		headers["User-Agent"] = userAgent;
		return;
	}
	if (LIBRARY_DEFAULT_UA.test(headers[key] ?? "")) {
		delete headers[key];
		headers["User-Agent"] = userAgent;
	}
}

/**
 * Host allow-list matcher. Entries are exact hostnames (`api.example.com`)
 * or wildcard subdomains (`*.example.com`, which also matches `example.com`).
 */
export function hostMatches(
	hostname: string,
	allow: readonly string[],
): boolean {
	const h = hostname.toLowerCase().replace(/\.$/, "");
	return allow.some((raw) => {
		const a = raw.toLowerCase().replace(/\.$/, "");
		if (a.startsWith("*.")) {
			const base = a.slice(2);
			return h === base || h.endsWith(`.${base}`);
		}
		return h === a;
	});
}
