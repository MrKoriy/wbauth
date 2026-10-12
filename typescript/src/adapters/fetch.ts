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
 * - **Redirects** (`redirect: "follow"`, the default) are followed here, not
 *   by the underlying fetch, so each hop is re-signed for its own
 *   `@authority`. Native fetch would otherwise replay hop 1's signature to the
 *   redirect target. Method/body rewriting and cross-origin credential
 *   stripping follow the WHATWG fetch spec.
 *
 * - `hosts` / `shouldSign` restrict which hosts receive your identity
 *   (redirects to other hosts go out unsigned); plain-http requests are
 *   unsigned unless `allowInsecure: true`.
 *
 * v1 limitation: streaming bodies are buffered (`req.clone().arrayBuffer()`)
 * so Content-Digest can be computed.
 */

import type { Identity } from "../identity.js";
import { sign } from "../signer.js";
import {
	applyUserAgent,
	ensureContentDigest,
	makeSignDecider,
	type SignScopeOptions,
	stripSignatureHeaders,
} from "./_utils.js";

export interface SignedFetchOptions extends SignScopeOptions {
	/** Underlying fetch implementation. Defaults to `globalThis.fetch` at call time. */
	fetch?: typeof fetch;
	/** Maximum redirects followed (and re-signed). Default 20, like fetch. */
	maxRedirects?: number;
}

const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);
/** Request headers dropped when a redirect crosses origins (fetch spec §4.4). */
const CROSS_ORIGIN_STRIP = new Set([
	"authorization",
	"cookie",
	"proxy-authorization",
]);
/** Request-body headers dropped when a redirect turns the request into GET. */
const BODY_HEADERS = new Set([
	"content-type",
	"content-length",
	"content-encoding",
	"content-language",
	"content-location",
	"content-digest",
]);

function dropHeaders(headers: Record<string, string>, names: Set<string>) {
	for (const k of Object.keys(headers)) {
		if (names.has(k.toLowerCase())) delete headers[k];
	}
}

export function createSignedFetch(
	identity: Identity,
	options: SignedFetchOptions = {},
): typeof fetch {
	const decide = makeSignDecider(options);
	return async function signedFetch(
		input: RequestInfo | URL,
		init: RequestInit = {},
	): Promise<Response> {
		const req = new Request(input, init);
		let method = req.method;
		let url = req.url;

		let body: Uint8Array | null = null;
		if (req.body) {
			const buf = await req.clone().arrayBuffer();
			body = buf.byteLength > 0 ? new Uint8Array(buf) : null;
		}

		const baseHeaders: Record<string, string> = {};
		req.headers.forEach((value, key) => {
			baseHeaders[key] = value;
		});

		const redirectMode = init.redirect ?? req.redirect;
		const followHere = redirectMode === "follow";
		const maxRedirects = options.maxRedirects ?? 20;
		const doFetch = options.fetch ?? globalThis.fetch;

		for (let hop = 0; ; hop++) {
			const headers: Record<string, string> = { ...baseHeaders };
			if (decide(url)) {
				ensureContentDigest(method, headers, body);
				await sign({ method, url, headers, body }, identity);
			} else {
				// Out of scope (other host / plain http): never forward a signature.
				stripSignatureHeaders(headers);
			}
			applyUserAgent(headers, identity.userAgent);

			const outInit: RequestInit = {
				...init,
				method,
				headers,
				body: (body ?? undefined) as BodyInit | undefined,
				signal: init.signal ?? req.signal,
				redirect: followHere ? "manual" : redirectMode,
				credentials: init.credentials ?? req.credentials,
				cache: init.cache ?? req.cache,
				keepalive: init.keepalive ?? req.keepalive,
			};
			const integrity = init.integrity ?? req.integrity;
			if (integrity) outInit.integrity = integrity;
			const referrerPolicy = init.referrerPolicy ?? req.referrerPolicy;
			if (referrerPolicy) outInit.referrerPolicy = referrerPolicy;

			const res = await doFetch(url, outInit);
			if (!followHere || !REDIRECT_STATUSES.has(res.status)) return res;
			const location = res.headers.get("location");
			if (location === null) return res;
			if (hop >= maxRedirects) {
				throw new TypeError(`redirect count exceeded (${maxRedirects})`);
			}
			const next = new URL(location, url);
			if (next.protocol !== "http:" && next.protocol !== "https:") {
				throw new TypeError(`unsupported redirect scheme: ${next.protocol}`);
			}
			const upper = method.toUpperCase();
			if (
				(res.status === 303 && upper !== "GET" && upper !== "HEAD") ||
				((res.status === 301 || res.status === 302) && upper === "POST")
			) {
				method = "GET";
				body = null;
				dropHeaders(baseHeaders, BODY_HEADERS);
			}
			if (new URL(url).origin !== next.origin) {
				dropHeaders(baseHeaders, CROSS_ORIGIN_STRIP);
			}
			await res.body?.cancel().catch(() => {});
			url = next.href;
		}
	};
}
