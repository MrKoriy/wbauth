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
	const b64 = createHash("sha256").update(body).digest("base64");
	const key = findHeader(headers, "content-digest");
	if (key !== undefined) {
		const m = /(?:^|,)\s*sha-256=:([A-Za-z0-9+/=]+):/.exec(headers[key] ?? "");
		// Caller's own digest (other algorithm) or still correct → keep.
		if (m === null || m[1] === b64) return;
		delete headers[key]; // stale digest (e.g. previous redirect hop)
	}
	headers["Content-Digest"] = `sha-256=:${b64}:`;
}

const SIGNATURE_HEADERS = new Set([
	"signature",
	"signature-input",
	"signature-agent",
]);

/** Remove Signature / Signature-Input / Signature-Agent in any casing. */
export function stripSignatureHeaders(headers: Record<string, string>): void {
	for (const k of Object.keys(headers)) {
		if (SIGNATURE_HEADERS.has(k.toLowerCase())) delete headers[k];
	}
}

export interface SignScopeOptions {
	/** Only sign requests to these hosts (`example.com`, `*.example.com`). */
	hosts?: readonly string[];
	/** Custom predicate; takes precedence over `hosts`. */
	shouldSign?: (url: URL) => boolean;
	/** Also sign plain `http://` requests (off by default: replayable in clear text). */
	allowInsecure?: boolean;
}

/** The shared "sign this URL?" predicate used by every adapter. */
export function makeSignDecider(
	opts: SignScopeOptions = {},
): (raw: string) => boolean {
	return (raw: string) => {
		let u: URL;
		try {
			u = new URL(raw);
		} catch {
			return false;
		}
		if (u.protocol !== "https:" && u.protocol !== "http:") return false;
		if (!u.hostname) return false;
		if (u.protocol === "http:" && !opts.allowInsecure) return false;
		if (opts.shouldSign) return opts.shouldSign(u);
		if (opts.hosts) return hostMatches(u.hostname, opts.hosts);
		return true;
	};
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
