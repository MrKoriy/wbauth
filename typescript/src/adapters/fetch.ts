/**
 * createSignedFetch — drop-in `fetch` wrapper that signs every outgoing request.
 *
 * Mirrors python/src/wbauth/adapters/httpx_auth.py. Stateless: closure over
 * `identity` only. Returns a function whose signature matches `typeof fetch`,
 * so user code can swap `fetch` for `signedFetch` without other changes.
 *
 * v1 limitation (Pitfall 4): streaming bodies are NOT supported. The adapter
 * reads the full body via `req.clone().arrayBuffer()` to compute Content-Digest.
 */

import type { Identity } from "../identity.js";
import { sign } from "../signer.js";
import { ensureContentDigest } from "./_utils.js";

export function createSignedFetch(identity: Identity): typeof fetch {
	return async function signedFetch(
		input: RequestInfo | URL,
		init: RequestInit = {},
	): Promise<Response> {
		const req = new Request(input, init);
		const method = req.method;
		const url = req.url;

		// Read body once — Request consumes its body stream; clone first.
		let body: Uint8Array | null = null;
		if (req.body) {
			const buf = await req.clone().arrayBuffer();
			body = buf.byteLength > 0 ? new Uint8Array(buf) : null;
		}

		// Build mutable headers dict from the Request.
		const headers: Record<string, string> = {};
		req.headers.forEach((value, key) => {
			headers[key] = value;
		});

		// Auto-Content-Digest BEFORE sign() (mirror Python ordering — fulfills
		// signer's content-digest precondition for POST/PUT/PATCH + body).
		ensureContentDigest(method, headers, body);

		// Sign — mutates `headers` to add Signature, Signature-Input, Signature-Agent.
		await sign({ method, url, headers, body }, identity);

		// Conditional UA injection (mirror Python adapter behavior).
		if (
			identity.userAgent &&
			!Object.keys(headers).some((k) => k.toLowerCase() === "user-agent")
		) {
			headers["User-Agent"] = identity.userAgent;
		}

		// Cast body: Uint8Array is a valid BodyInit at runtime (web fetch spec)
		// but DOM typing wants ArrayBufferView/string/Blob etc. The cast is safe.
		return fetch(url, {
			...init,
			method,
			headers,
			body: (body ?? undefined) as BodyInit | undefined,
		});
	};
}
