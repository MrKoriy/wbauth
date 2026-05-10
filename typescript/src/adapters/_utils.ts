/**
 * Shared adapter helpers (internal — not part of the public surface).
 *
 * Mirror python/src/wbauth/adapters/_utils.py. The signer auto-includes
 * `content-digest` in covered components for POST/PUT/PATCH with a body;
 * adapters call ensureContentDigest() before sign() so that precondition
 * is met. RFC 9530 sha-256 in structured-fields form (`sha-256=:<b64>:`).
 */
import { createHash } from "node:crypto";

const DIGEST_METHODS = new Set(["POST", "PUT", "PATCH"]);

/**
 * Mutate `headers` in place to add Content-Digest when warranted. No-op if:
 * - body is null/empty,
 * - method is not POST/PUT/PATCH,
 * - the request already carries a Content-Digest header (case-insensitive).
 */
export function ensureContentDigest(
	method: string,
	headers: Record<string, string>,
	body: Uint8Array | null,
): void {
	if (!body || body.byteLength === 0) return;
	if (!DIGEST_METHODS.has(method.toUpperCase())) return;
	if (Object.keys(headers).some((k) => k.toLowerCase() === "content-digest")) {
		return;
	}
	const b64 = createHash("sha256").update(body).digest("base64");
	headers["Content-Digest"] = `sha-256=:${b64}:`;
}
