/**
 * NormalizedRequest — the structural input to wbauth.sign().
 *
 * Mirrors python/src/wbauth/normalized_request.py. The Web Bot Auth signer
 * does not care which HTTP client produced the request; it only needs the
 * five fields below. Adapter glue (createSignedFetch, applyTo) constructs
 * a NormalizedRequest from its native request type and hands it to sign().
 *
 * The `headers` dict is mutated in place by sign() — Signature, Signature-Input,
 * and Signature-Agent are written back so the caller can read them out.
 */
export interface NormalizedRequest {
	/** HTTP method ("GET" | "POST" | "PUT" | "PATCH" | "DELETE" | ...). */
	method: string;
	/** Absolute URL — must be https:// for production targets. */
	url: string;
	/** Mutable header dict. sign() writes Signature, Signature-Input, Signature-Agent. */
	headers: Record<string, string>;
	/** Body bytes for content-digest computation; null/undefined for bodiless methods. */
	body: Uint8Array | null;
}
