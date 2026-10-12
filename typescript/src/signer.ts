/**
 * Pure-function signer for Web Bot Auth (RFC 9421).
 *
 * Mirrors python/src/wbauth/signer.py byte-for-byte — same defaults
 * (Ed25519, tag="web-bot-auth", expires=created+60s, covered components
 * ["@authority", "signature-agent"] + "content-digest" for bodies, 64-byte
 * base64 nonce).
 *
 * The profile is fixed, so the RFC 9421 signature base is built directly
 * (no WHATWG `Request` construction, no body copy, no generic
 * structured-field serializer). Cross-language vectors in spec/test-vectors
 * pin the exact bytes.
 */
import { randomBytes } from "node:crypto";
import type { Identity } from "./identity.js";
import { validateSignatureAgentUrl } from "./identity.js";
import type { NormalizedRequest } from "./normalized-request.js";

// ---------- Module constants (HARD-CODED — typos = silent verifier reject) ----------

/** IETF Web Bot Auth profile mandate. NEVER change. */
export const WEB_BOT_AUTH_TAG = "web-bot-auth";
/** Canonical Signature label. */
const DEFAULT_LABEL = "sig1";
/** Default expires window. 60s leaves NTP-skew + network-latency headroom. */
const DEFAULT_EXPIRES_SECONDS = 60;
/** Hard upper bound on the validity window (parity with Python). */
export const MAX_EXPIRES_SECONDS = 3600;
/** Random bytes in the default nonce (base64) — web-bot-auth's NONCE_LENGTH_IN_BYTES. */
export const NONCE_BYTES = 64;

const SF_KEY_RE = /^[a-z*][a-z0-9_\-.*]*$/;
const DEFAULT_PORTS: Record<string, string> = {
	"https:": "443",
	"http:": "80",
};

// ---------- Public types ----------

export interface SignatureHeaders {
	signature: string;
	signatureInput: string;
	signatureAgent: string;
}

export interface SignOptions {
	/** Signing timestamp. Defaults to `new Date()`. Override for vector reproducibility. */
	created?: Date;
	/** Validity window in seconds. Defaults to 60. */
	expiresAfterSeconds?: number;
	/** Anti-replay nonce. Defaults to 64 random bytes, base64. */
	nonce?: string;
	/** Signature label (the `sig1=` prefix). Defaults to "sig1". */
	label?: string;
}

// ---------- Helpers ----------

/** RFC 8941 sf-string (printable ASCII only). */
export function sfString(value: string): string {
	for (const ch of value) {
		const c = ch.charCodeAt(0);
		if (c < 0x20 || c > 0x7e) {
			throw new Error(
				`value is not a valid structured-field string: ${JSON.stringify(value)}`,
			);
		}
	}
	return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

/** RFC 9421 §2.2.3 `@authority`: lower-case host, no userinfo, no default port. */
export function normalizeAuthority(url: string): string {
	const u = new URL(url);
	if (!u.hostname) throw new Error(`URL has no host: ${url}`);
	const host = u.hostname.toLowerCase();
	const port =
		u.port && u.port !== DEFAULT_PORTS[u.protocol] ? `:${u.port}` : "";
	return `${host}${port}`;
}

function componentsFor(hasBody: boolean): string[] {
	return hasBody
		? ["@authority", "signature-agent", "content-digest"]
		: ["@authority", "signature-agent"];
}

/** Headers regenerated on every sign() call. */
const RESIGN_HEADERS = ["signature", "signature-input", "signature-agent"];

function getHeader(
	headers: Record<string, string>,
	name: string,
): string | undefined {
	const n = name.toLowerCase();
	const k = Object.keys(headers).find((key) => key.toLowerCase() === n);
	return k === undefined ? undefined : headers[k];
}

function removeHeaders(headers: Record<string, string>, names: string[]): void {
	for (const k of Object.keys(headers)) {
		if (names.includes(k.toLowerCase())) delete headers[k];
	}
}

// ---------- Public API ----------

/**
 * Sign a NormalizedRequest with the Web Bot Auth profile.
 *
 * Mutates `request.headers` in place (Signature-Agent, Signature-Input,
 * Signature) and returns the same three values.
 */
export async function sign(
	request: NormalizedRequest,
	identity: Identity,
	opts: SignOptions = {},
): Promise<SignatureHeaders> {
	validateSignatureAgentUrl(identity.signatureAgentUrl);

	const expiresAfterSeconds =
		opts.expiresAfterSeconds ?? DEFAULT_EXPIRES_SECONDS;
	if (
		typeof expiresAfterSeconds !== "number" ||
		!Number.isFinite(expiresAfterSeconds) ||
		expiresAfterSeconds <= 0 ||
		expiresAfterSeconds > MAX_EXPIRES_SECONDS
	) {
		throw new RangeError(
			`expiresAfterSeconds must be a number in (0, ${MAX_EXPIRES_SECONDS}], got: ${expiresAfterSeconds}`,
		);
	}
	const label = opts.label ?? DEFAULT_LABEL;
	if (!SF_KEY_RE.test(label)) {
		throw new Error(
			`label must be an RFC 8941 key, got: ${JSON.stringify(label)}`,
		);
	}

	// Drop stale signature headers in ANY casing (retries / redirects).
	removeHeaders(request.headers, RESIGN_HEADERS);
	const signatureAgentHeader = sfString(identity.signatureAgentUrl);
	request.headers["Signature-Agent"] = signatureAgentHeader;

	const created = Math.floor((opts.created ?? new Date()).getTime() / 1000);
	const expires = created + Math.floor(expiresAfterSeconds);
	const nonce = opts.nonce ?? randomBytes(NONCE_BYTES).toString("base64");

	const hasBody = request.body != null && request.body.byteLength > 0;
	const components = componentsFor(hasBody);
	const values: Record<string, string> = {
		"@authority": normalizeAuthority(request.url),
		"signature-agent": signatureAgentHeader,
	};
	if (hasBody) {
		const cd = getHeader(request.headers, "content-digest");
		if (cd === undefined) {
			throw new Error(
				'Covered header field "content-digest" not found in the message. ' +
					"Call ensureContentDigest() or use createSignedFetch()/applyTo(), which add it automatically.",
			);
		}
		values["content-digest"] = cd.trim();
	}

	const signer = identity._signer();
	const params =
		`(${components.map((c) => `"${c}"`).join(" ")})` +
		`;created=${created}` +
		`;keyid=${sfString(signer.keyid)}` +
		`;alg="ed25519"` +
		`;expires=${expires}` +
		`;nonce=${sfString(nonce)}` +
		`;tag=${sfString(WEB_BOT_AUTH_TAG)}`;
	const base = `${components.map((c) => `"${c}": ${values[c]}`).join("\n")}\n"@signature-params": ${params}`;
	const raw = await signer.sign(base);

	const signatureInput = `${label}=${params}`;
	const signature = `${label}=:${Buffer.from(raw).toString("base64")}:`;
	request.headers["Signature-Input"] = signatureInput;
	request.headers.Signature = signature;
	return { signature, signatureInput, signatureAgent: signatureAgentHeader };
}
