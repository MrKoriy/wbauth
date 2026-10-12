/**
 * Origin-side verification of Web Bot Auth signatures — mirror of
 * python/src/wbauth/verifier.py.
 *
 *   const verifier = new Verifier();
 *   const agent = await verifier.verify(request);   // WHATWG Request
 *
 * Checks: tag="web-bot-auth", alg=ed25519, created/expires window (with skew,
 * ≤ 3600 s), @authority covered, signature-agent covered when sent,
 * content-digest covered AND matching the body, nonce not replayed, key
 * resolved from the Signature-Agent directory (thumbprint must equal keyid).
 */
import {
	createHash,
	createPublicKey,
	verify as cryptoVerify,
} from "node:crypto";
import { thumbprint } from "./identity.js";
import {
	MAX_EXPIRES_SECONDS,
	normalizeAuthority,
	WEB_BOT_AUTH_TAG,
} from "./signer.js";

export const DIRECTORY_PATH = "/.well-known/http-message-signatures-directory";
const DIRECTORY_MAX_BYTES = 64 * 1024;

export class VerificationError extends Error {
	override name = "VerificationError";
}

export interface VerifiedAgent {
	kid: string;
	signatureAgentUrl: string | null;
	label: string;
	created: number;
	expires: number;
	nonce: string | null;
	covered: string[];
	jwk: JsonWebKey;
}

export type KeyResolver = (
	kid: string,
	signatureAgent: string | null,
) => Promise<JsonWebKey | null | undefined>;

export interface VerifierOptions {
	keyResolver?: KeyResolver;
	/** fetch used for directory lookups (default globalThis.fetch). */
	fetch?: typeof fetch;
	/** Directory cache TTL in seconds (default 300). */
	jwksTtlSeconds?: number;
	/** Clock skew tolerance in seconds (default 5). */
	maxSkew?: number;
	requireNonce?: boolean;
	nonceStore?: NonceStore;
}

/** In-memory TTL set of seen nonces. Replace with a shared store in clusters. */
export class NonceStore {
	#seen = new Map<string, number>();
	constructor(private readonly maxSize = 100_000) {}
	seen(nonce: string, expiresAt: number): boolean {
		const now = Date.now() / 1000;
		if (this.#seen.size >= this.maxSize) {
			for (const [n, e] of this.#seen) if (e <= now) this.#seen.delete(n);
			for (const n of [...this.#seen.keys()].slice(
				0,
				Math.ceil(this.maxSize / 10),
			)) {
				if (this.#seen.size < this.maxSize) break;
				this.#seen.delete(n);
			}
		}
		const prev = this.#seen.get(nonce);
		if (prev !== undefined && prev > now) return true;
		this.#seen.set(nonce, expiresAt);
		return false;
	}
}

// ---------- Structured-field parsing (profile subset) ----------

const SF_STRING = String.raw`"(?:[^"\\]|\\.)*"`;
const PARAM = String.raw`;\s*([a-z*][a-z0-9_.*-]*)(?:=(${SF_STRING}|-?\d+(?:\.\d+)?|\?[01]|[A-Za-z*][^;,\s]*))?`;
const SIG_INPUT_RE = new RegExp(
	String.raw`\s*([a-z*][a-z0-9_.*-]*)=(\((?:\s*${SF_STRING}(?:;[^\s)"]+)*)*\s*\))((?:${PARAM})*)`,
	"y",
);

const unquote = (v: string) =>
	v.startsWith('"') ? v.slice(1, -1).replace(/\\(.)/g, "$1") : v;

interface ParsedInput {
	label: string;
	rawParams: string;
	components: string[];
	params: Record<string, string | number | boolean>;
}

export function parseSignatureInput(value: string): ParsedInput[] {
	const out: ParsedInput[] = [];
	let pos = 0;
	while (pos < value.length) {
		SIG_INPUT_RE.lastIndex = pos;
		const m = SIG_INPUT_RE.exec(value);
		if (!m) throw new VerificationError("malformed Signature-Input");
		const [, label = "", inner = "", rest = ""] = m;
		if (/"\s*;/.test(inner))
			throw new VerificationError("component parameters are not supported");
		const params: Record<string, string | number | boolean> = {};
		for (const p of rest.matchAll(new RegExp(PARAM, "g"))) {
			const k = p[1] as string;
			const v = p[2];
			params[k] =
				v === undefined
					? true
					: v.startsWith('"')
						? unquote(v)
						: /^-?\d+$/.test(v)
							? Number(v)
							: v;
		}
		out.push({
			label,
			rawParams: inner + rest,
			components: [...inner.matchAll(new RegExp(SF_STRING, "g"))].map((x) =>
				unquote(x[0]),
			),
			params,
		});
		pos = SIG_INPUT_RE.lastIndex;
		while (pos < value.length && (value[pos] === " " || value[pos] === ","))
			pos++;
	}
	return out;
}

function parseSignature(value: string): Map<string, Buffer> {
	const out = new Map<string, Buffer>();
	for (const m of value.matchAll(
		/\s*([a-z*][a-z0-9_.*-]*)=:([A-Za-z0-9+/=]*):/g,
	)) {
		out.set(m[1] as string, Buffer.from(m[2] as string, "base64"));
	}
	return out;
}

function componentValue(
	name: string,
	req: { method: string; url: string },
	headers: Headers,
	authority?: string,
): string {
	const u = new URL(req.url);
	switch (name) {
		case "@authority":
			return authority ?? normalizeAuthority(req.url);
		case "@method":
			return req.method.toUpperCase();
		case "@scheme":
			return u.protocol.slice(0, -1);
		case "@target-uri":
			return u.href;
		case "@path":
			return u.pathname || "/";
		case "@query":
			return u.search || "?";
	}
	if (name.startsWith("@"))
		throw new VerificationError(`unsupported derived component ${name}`);
	const v = headers.get(name);
	if (v === null) throw new VerificationError(`covered header ${name} missing`);
	return v.trim();
}

function directoryUrl(signatureAgent: string): string {
	const u = new URL(signatureAgent);
	if (u.protocol !== "https:")
		throw new VerificationError("Signature-Agent must be https://");
	if (u.pathname === "/" || u.pathname === "") {
		u.pathname = DIRECTORY_PATH;
		u.search = "";
	}
	u.hash = "";
	return u.href;
}

export class Verifier {
	#opts: VerifierOptions;
	#nonces: NonceStore;
	#jwks = new Map<string, { until: number; keys: JsonWebKey[] }>();

	constructor(opts: VerifierOptions = {}) {
		this.#opts = opts;
		this.#nonces = opts.nonceStore ?? new NonceStore();
	}

	async #directoryKeys(url: string): Promise<JsonWebKey[]> {
		const hit = this.#jwks.get(url);
		if (hit && hit.until > Date.now()) return hit.keys;
		const f = this.#opts.fetch ?? globalThis.fetch;
		let res: Response;
		try {
			res = await f(url, {
				headers: {
					accept:
						"application/http-message-signatures-directory+json, application/json",
				},
				redirect: "error",
				signal: AbortSignal.timeout(3000),
			});
		} catch (e) {
			throw new VerificationError(`directory unreachable: ${String(e)}`);
		}
		if (res.status !== 200)
			throw new VerificationError(`directory ${url} answered ${res.status}`);
		const buf = await res.arrayBuffer();
		if (buf.byteLength > DIRECTORY_MAX_BYTES)
			throw new VerificationError("directory too large");
		let keys: unknown;
		try {
			keys = (JSON.parse(new TextDecoder().decode(buf)) as { keys?: unknown })
				.keys;
		} catch {
			throw new VerificationError("directory is not a JWKS");
		}
		if (!Array.isArray(keys))
			throw new VerificationError("directory is not a JWKS");
		this.#jwks.set(url, {
			until: Date.now() + (this.#opts.jwksTtlSeconds ?? 300) * 1000,
			keys,
		});
		return keys as JsonWebKey[];
	}

	async #resolve(
		kid: string,
		signatureAgent: string | null,
	): Promise<JsonWebKey> {
		if (this.#opts.keyResolver) {
			const jwk = await this.#opts.keyResolver(kid, signatureAgent);
			if (!jwk) throw new VerificationError(`unknown keyid ${kid}`);
			return jwk;
		}
		if (!signatureAgent)
			throw new VerificationError(
				"no Signature-Agent and no keyResolver configured",
			);
		for (const k of await this.#directoryKeys(directoryUrl(signatureAgent))) {
			if (
				k &&
				k.kty === "OKP" &&
				k.crv === "Ed25519" &&
				k.x &&
				thumbprint(k) === kid
			)
				return k;
		}
		throw new VerificationError(
			`keyid ${kid} not published by ${signatureAgent}`,
		);
	}

	/**
	 * Verify a WHATWG Request (body is read from a clone). `authority`
	 * overrides the value derived from the URL (e.g. behind a proxy).
	 */
	async verify(
		request: Request,
		opts: { authority?: string; now?: number } = {},
	): Promise<VerifiedAgent> {
		const h = request.headers;
		const sigInput = h.get("signature-input");
		const sigHeader = h.get("signature");
		if (!sigInput || !sigHeader)
			throw new VerificationError("request is not signed");
		const sigs = parseSignature(sigHeader);
		const cand = parseSignatureInput(sigInput).find(
			(c) => c.params.tag === WEB_BOT_AUTH_TAG,
		);
		if (!cand)
			throw new VerificationError('no signature with tag="web-bot-auth"');
		const { label, rawParams, components, params } = cand;
		const raw = sigs.get(label);
		if (!raw) throw new VerificationError(`Signature has no ${label} member`);
		if ((params.alg ?? "ed25519") !== "ed25519")
			throw new VerificationError("only alg=ed25519 is supported");
		const { created, expires, keyid } = params;
		if (
			typeof created !== "number" ||
			typeof expires !== "number" ||
			typeof keyid !== "string"
		) {
			throw new VerificationError("created, expires and keyid are required");
		}
		const skew = this.#opts.maxSkew ?? 5;
		const now = opts.now ?? Date.now() / 1000;
		if (created > now + skew)
			throw new VerificationError("signature created in the future");
		if (expires < now - skew) throw new VerificationError("signature expired");
		if (expires <= created || expires - created > MAX_EXPIRES_SECONDS) {
			throw new VerificationError("invalid validity window");
		}
		if (!components.includes("@authority"))
			throw new VerificationError("@authority must be covered");
		let signatureAgent: string | null = null;
		const sa = h.get("signature-agent");
		if (sa !== null) {
			if (!components.includes("signature-agent")) {
				throw new VerificationError("Signature-Agent sent but not covered");
			}
			signatureAgent = unquote(sa.trim());
		}
		const body = request.body
			? new Uint8Array(await request.clone().arrayBuffer())
			: new Uint8Array();
		if (body.byteLength > 0) {
			if (!components.includes("content-digest")) {
				throw new VerificationError(
					"request has a body but content-digest is not covered",
				);
			}
			const m = /(?:^|,)\s*sha-256=:([A-Za-z0-9+/=]+):/.exec(
				h.get("content-digest") ?? "",
			);
			const actual = createHash("sha256").update(body).digest("base64");
			if (!m || m[1] !== actual)
				throw new VerificationError("Content-Digest does not match the body");
		}
		const nonce = typeof params.nonce === "string" ? params.nonce : null;
		if (this.#opts.requireNonce && !nonce)
			throw new VerificationError("nonce required");

		const base = [
			...components.map(
				(c) => `"${c}": ${componentValue(c, request, h, opts.authority)}`,
			),
			`"@signature-params": ${rawParams}`,
		].join("\n");
		const jwk = await this.#resolve(keyid, signatureAgent);
		let ok = false;
		try {
			const key = createPublicKey({
				key: { kty: "OKP", crv: "Ed25519", x: jwk.x as string },
				format: "jwk",
			});
			ok = cryptoVerify(null, Buffer.from(base, "utf8"), key, raw);
		} catch {
			ok = false;
		}
		if (!ok) throw new VerificationError("signature does not verify");
		if (nonce && this.#nonces.seen(nonce, expires + skew))
			throw new VerificationError("nonce replayed");
		return {
			kid: keyid,
			signatureAgentUrl: signatureAgent,
			label,
			created,
			expires,
			nonce,
			covered: components,
			jwk,
		};
	}
}

/**
 * Fetch-style middleware helper (Hono, itty-router, Workers, Bun, Deno…):
 * returns the verified agent, `null` for unsigned requests, or a 401
 * `Response` when `required` and verification fails.
 */
export function createVerifierMiddleware(
	opts: VerifierOptions & { required?: boolean } = {},
) {
	const verifier = new Verifier(opts);
	return async (request: Request): Promise<VerifiedAgent | null | Response> => {
		const signed = request.headers.has("signature-input");
		if (!signed && !opts.required) return null;
		try {
			if (!signed) throw new VerificationError("request is not signed");
			return await verifier.verify(request);
		} catch (e) {
			if (!opts.required) return null;
			return new Response(
				JSON.stringify({
					error: "web_bot_auth",
					reason: String((e as Error).message),
				}),
				{
					status: 401,
					headers: { "content-type": "application/json" },
				},
			);
		}
	};
}
