/**
 * createSignedFetch — drop-in `fetch` wrapper that signs every outgoing request.
 *
 * Mirrors python/src/wbauth/adapters/httpx_auth.py. Stateless: closure over
 * `identity` only. Returns a function whose signature matches `typeof fetch`,
 * so user code can swap `fetch` for `signedFetch` without other changes.
 *
 * - Request-object inputs keep their `signal`, `redirect`, `credentials`,
 *   `cache`, `keepalive`, `integrity` and `referrerPolicy`.
 * - Re-sending an already signed request (retry wrappers) produces exactly one
 *   fresh signature — stale Signature* headers are replaced, never merged.
 *
 * v1 limitation: streaming bodies are buffered (`req.clone().arrayBuffer()`)
 * so Content-Digest can be computed.
 */

import type { Identity } from "../identity.js";
import { sign } from "../signer.js";
import { applyUserAgent, ensureContentDigest } from "./_utils.js";

export interface SignedFetchOptions {
	/** Underlying fetch implementation. Defaults to `globalThis.fetch` at call time. */
	fetch?: typeof fetch;
}

export function createSignedFetch(
	identity: Identity,
	options: SignedFetchOptions = {},
): typeof fetch {
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

		// Mutable header dict (Headers already lower-cases + de-duplicates).
		const headers: Record<string, string> = {};
		req.headers.forEach((value, key) => {
			headers[key] = value;
		});

		// Auto-Content-Digest BEFORE sign() (signer precondition for POST/PUT/PATCH + body).
		ensureContentDigest(method, headers, body);

		// Sign — replaces stale Signature* headers, then writes fresh ones.
		await sign({ method, url, headers, body }, identity);
		applyUserAgent(headers, identity.userAgent);

		const outInit: RequestInit = {
			...init,
			method,
			headers,
			// Uint8Array is a valid BodyInit at runtime; DOM typings disagree.
			body: (body ?? undefined) as BodyInit | undefined,
			signal: init.signal ?? req.signal,
			redirect: init.redirect ?? req.redirect,
			credentials: init.credentials ?? req.credentials,
			cache: init.cache ?? req.cache,
			keepalive: init.keepalive ?? req.keepalive,
		};
		const integrity = init.integrity ?? req.integrity;
		if (integrity) outInit.integrity = integrity;
		const referrerPolicy = init.referrerPolicy ?? req.referrerPolicy;
		if (referrerPolicy) outInit.referrerPolicy = referrerPolicy;

		const doFetch = options.fetch ?? globalThis.fetch;
		return doFetch(url, outInit);
	};
}
