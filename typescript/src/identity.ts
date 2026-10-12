/**
 * Identity, KeyPair, and key-file helpers for the wbauth TypeScript SDK.
 *
 * Mirrors python/src/wbauth/identity.py — same on-disk format (PKCS8 PEM at
 * 0o600, optionally passphrase-encrypted), same kid (RFC 7638 JWK
 * thumbprint), same multi-key rotation semantics (active + retiring, in
 * memory via `rotate()` or persisted via `rotateKeyring()`), same REDACTED
 * repr (IDENT-08).
 *
 * Key material is held in ECMAScript `#private` fields and only as a
 * non-extractable `KeyObject`/`Signer`, so `JSON.stringify(identity)`,
 * `structuredClone`, spreading or `Object.entries` never expose `d`.
 */

import {
	createHash,
	createPrivateKey,
	createPublicKey,
	sign as cryptoSign,
	generateKeyPairSync,
	type KeyObject,
} from "node:crypto";
import { mkdir, open, readFile, rename, stat } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";

// ---------- Module constants ----------

/** Default path for the active signing key. Matches Python DEFAULT_KEY_PATH. */
export const DEFAULT_KEY_PATH = resolve(
	homedir(),
	".config",
	"wbauth",
	"key.pem",
);

/** Environment variable holding the passphrase for encrypted PEM key files. */
export const KEY_PASSWORD_ENV = "WBAUTH_KEY_PASSWORD";
export const KEYRING_ACTIVE = "active.pem";
export const KEYRING_RETIRING = "retiring.pem";

/**
 * RFC 9421 Appendix B.1.4 publicly-known test key — NEVER use in production.
 */
const TEST_KEY_JWK: import("node:crypto").JsonWebKey = {
	kty: "OKP",
	crv: "Ed25519",
	d: "n4Ni-HpISpVObnQMW0wOhCKROaIKqKtW_2ZYb2p9KcU",
	x: "JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bs",
};

let warnedWindows = false;

// ---------- Public types ----------

export interface IdentityOptions {
	/** Stable HTTPS URL where this agent's JWKS is published. Must start with `https://`. */
	signatureAgentUrl: string;
	/** Optional User-Agent string adapters inject when caller did not supply one. */
	userAgent?: string;
}

export interface KeyOptions {
	/** Passphrase for an encrypted PEM. Defaults to `$WBAUTH_KEY_PASSWORD`. */
	password?: string;
}

/** Public JWK of one key ({kty, crv, x, kid}). */
export type PublicJwk = JsonWebKey & { kid: string };

/**
 * Pluggable Ed25519 signing backend (local key, KMS, HSM, keychain).
 * `sign` receives the RFC 9421 signature base as UTF-8 bytes and must return
 * the raw 64-byte Ed25519 signature.
 */
export interface Ed25519SignerBackend {
	/** Public key as a JWK ({kty:"OKP", crv:"Ed25519", x}). */
	publicJwk: JsonWebKey;
	sign(data: Uint8Array): Uint8Array | Promise<Uint8Array>;
}

/** Signer handed to `sign()` (structurally compatible with web-bot-auth's). */
export interface Signer {
	alg: "ed25519";
	keyid: string;
	sign(data: string): Promise<Uint8Array>;
}

/** Public view of a key pair. Private material is never exposed. */
export interface KeyPair {
	publicJwk: PublicJwk;
	kid: string;
	signer: Signer;
}

// ---------- Validation ----------

/**
 * Validate a Signature-Agent URL: absolute https:// with a host, printable
 * ASCII only, no spaces/quotes/backslashes (it is emitted as an RFC 8941
 * sf-string and must not break the header or the signature base).
 */
export function validateSignatureAgentUrl(url: string): string {
	if (typeof url !== "string" || !url.startsWith("https://")) {
		throw new Error(`signatureAgentUrl must be https://, got: ${String(url)}`);
	}
	for (const ch of url) {
		const c = ch.charCodeAt(0);
		if (c < 0x21 || c > 0x7e || ch === '"' || ch === "\\") {
			throw new Error(
				`signatureAgentUrl must be printable ASCII without spaces, quotes or backslashes, got: ${JSON.stringify(url)}`,
			);
		}
	}
	let host = "";
	try {
		host = new URL(url).hostname;
	} catch {
		/* handled below */
	}
	if (!host) throw new Error(`signatureAgentUrl has no host: ${url}`);
	return url;
}

function validateUserAgent(ua: string | undefined): string | undefined {
	if (
		ua !== undefined &&
		[...ua].some((c) => c.charCodeAt(0) < 0x20 || c.charCodeAt(0) === 0x7f)
	) {
		throw new Error(
			`userAgent must not contain control characters: ${JSON.stringify(ua)}`,
		);
	}
	return ua;
}

// ---------- Identity class ----------

export class Identity {
	#active: KeyPair;
	#retiring: KeyPair | null;
	readonly #signatureAgentUrl: string;
	readonly #userAgent: string | undefined;

	private constructor(
		active: KeyPair,
		opts: IdentityOptions,
		retiring: KeyPair | null = null,
	) {
		this.#signatureAgentUrl = validateSignatureAgentUrl(opts.signatureAgentUrl);
		this.#userAgent = validateUserAgent(opts.userAgent);
		this.#active = active;
		this.#retiring = retiring;
	}

	// ---------- Public read-only API ----------

	get signatureAgentUrl(): string {
		return this.#signatureAgentUrl;
	}

	get userAgent(): string | undefined {
		return this.#userAgent;
	}

	/** The active key's kid (used as `keyid=` param in Signature-Input). */
	get kid(): string {
		return this.#active.kid;
	}

	/** The active key's public JWK (copy; never contains private material). */
	get publicJwk(): PublicJwk {
		return { ...this.#active.publicJwk };
	}

	/** Module-internal: returns the active Signer for sign() to use. */
	_signer(): Signer {
		return this.#active.signer;
	}

	/** Public JWKS: active first, then the retiring key (if any). */
	exportJwks(): { keys: PublicJwk[] } {
		const keys: PublicJwk[] = [{ ...this.#active.publicJwk }];
		if (this.#retiring) keys.push({ ...this.#retiring.publicJwk });
		return { keys };
	}

	/**
	 * IDENT-07: generate a new active key, demote current to retiring.
	 * In-memory only — use `rotateKeyring()` to persist. The default path is
	 * a fresh timestamped file next to DEFAULT_KEY_PATH (never collides).
	 */
	async rotate(newPath?: string, keyOpts: KeyOptions = {}): Promise<Identity> {
		const path = newPath
			? expandUser(newPath)
			: join(
					dirname(DEFAULT_KEY_PATH),
					`key-${Math.floor(Date.now() / 1000)}.pem`,
				);
		const newPair = await generateKeypairTo(path, keyOpts);
		return new Identity(newPair, this.#opts(), this.#active);
	}

	/**
	 * Persisted rotation: `<dir>/active.pem` → `retiring.pem` (replacing the
	 * previous retiring key), then a fresh `active.pem` is generated.
	 */
	async rotateKeyring(
		dir: string,
		keyOpts: KeyOptions = {},
	): Promise<Identity> {
		const d = expandUser(dir);
		const active = join(d, KEYRING_ACTIVE);
		const retiring = join(d, KEYRING_RETIRING);
		await stat(active);
		await rename(active, retiring);
		let pair: KeyPair;
		try {
			pair = await generateKeypairTo(active, keyOpts);
		} catch (e) {
			await rename(retiring, active);
			throw e;
		}
		return new Identity(
			pair,
			this.#opts(),
			await loadKeypair(retiring, keyOpts),
		);
	}

	#opts(): IdentityOptions {
		return {
			signatureAgentUrl: this.#signatureAgentUrl,
			userAgent: this.#userAgent,
		};
	}

	// ---------- Constructors ----------

	/**
	 * Loads `path` if it exists, generates a fresh key there otherwise.
	 * Concurrent first starts are safe: the loser of the O_EXCL race loads the
	 * winner's key. `retiringPath` optionally loads the previous key.
	 */
	static async loadOrGenerate(
		path: string = DEFAULT_KEY_PATH,
		opts: IdentityOptions & KeyOptions & { retiringPath?: string },
	): Promise<Identity> {
		validateSignatureAgentUrl(opts.signatureAgentUrl);
		const resolved = expandUser(path);
		let pair: KeyPair | null = null;
		if (!(await exists(resolved))) {
			try {
				pair = await generateKeypairTo(resolved, opts);
			} catch (e) {
				if (
					(e as NodeJS.ErrnoException).code !== "EEXIST" &&
					!(await exists(resolved))
				)
					throw e;
			}
		}
		pair ??= await loadKeypair(resolved, opts);
		let retiring: KeyPair | null = null;
		if (opts.retiringPath && (await exists(expandUser(opts.retiringPath)))) {
			retiring = await loadKeypair(expandUser(opts.retiringPath), opts);
		}
		return new Identity(pair, opts, retiring);
	}

	/** Load an existing key; never creates one. */
	static async load(
		path: string,
		opts: IdentityOptions & KeyOptions,
	): Promise<Identity> {
		return new Identity(await loadKeypair(expandUser(path), opts), opts);
	}

	/** Generate a new key at `path`; never overwrites. */
	static async generate(
		path: string,
		opts: IdentityOptions & KeyOptions,
	): Promise<Identity> {
		validateSignatureAgentUrl(opts.signatureAgentUrl);
		return new Identity(await generateKeypairTo(expandUser(path), opts), opts);
	}

	/** `<dir>/active.pem` (+ `retiring.pem`), generating active on first use. */
	static async loadKeyring(
		dir: string,
		opts: IdentityOptions & KeyOptions,
	): Promise<Identity> {
		const d = expandUser(dir);
		return Identity.loadOrGenerate(join(d, KEYRING_ACTIVE), {
			...opts,
			retiringPath: join(d, KEYRING_RETIRING),
		});
	}

	/** Wrap an external signer (KMS, HSM, keychain). */
	static async fromSigner(
		backend: Ed25519SignerBackend,
		opts: IdentityOptions,
	): Promise<Identity> {
		const jwk = backend.publicJwk;
		if (jwk.kty !== "OKP" || jwk.crv !== "Ed25519" || !jwk.x) {
			throw new TypeError("fromSigner: publicJwk must be an Ed25519 OKP JWK");
		}
		const kid = thumbprint(jwk);
		const enc = new TextEncoder();
		return new Identity(
			{
				kid,
				publicJwk: { kty: "OKP", crv: "Ed25519", x: jwk.x, kid },
				signer: {
					alg: "ed25519",
					keyid: kid,
					sign: async (data: string) => backend.sign(enc.encode(data)),
				},
			},
			opts,
		);
	}

	/** RFC 9421 Appendix B.1.4 test key. NEVER use in production. */
	static async fromTestKey(
		signatureAgentUrl: string,
		opts: Omit<IdentityOptions, "signatureAgentUrl"> = {},
	): Promise<Identity> {
		const key = createPrivateKey({ key: TEST_KEY_JWK, format: "jwk" });
		return new Identity(keyPairFromKeyObject(key), {
			...opts,
			signatureAgentUrl,
		});
	}

	// ---------- Redaction guarantees (IDENT-08) ----------

	toString(): string {
		return `<Identity REDACTED kid='${this.kid}' sig_agent='${this.#signatureAgentUrl}'>`;
	}

	/** JSON.stringify(identity) → public data only. */
	toJSON(): {
		kid: string;
		signatureAgentUrl: string;
		userAgent?: string;
		jwks: { keys: PublicJwk[] };
	} {
		return {
			kid: this.kid,
			signatureAgentUrl: this.#signatureAgentUrl,
			...(this.#userAgent !== undefined ? { userAgent: this.#userAgent } : {}),
			jwks: this.exportJwks(),
		};
	}

	/** util.inspect / console.log render the same REDACTED form (IDENT-08). */
	[Symbol.for("nodejs.util.inspect.custom")](): string {
		return this.toString();
	}
}

// ---------- Helpers (module-private) ----------

function expandUser(path: string): string {
	// Only "~" and "~/…" mean the current user's home; "~other" is left alone.
	if (path === "~") return homedir();
	if (path.startsWith("~/") || path.startsWith("~\\")) {
		return resolve(homedir(), path.slice(2));
	}
	return resolve(path);
}

async function exists(path: string): Promise<boolean> {
	try {
		await stat(path);
		return true;
	} catch {
		return false;
	}
}

function b64url(buf: Buffer): string {
	return buf
		.toString("base64")
		.replace(/\+/g, "-")
		.replace(/\//g, "_")
		.replace(/=+$/, "");
}

/** RFC 7638 thumbprint of an Ed25519 OKP JWK. */
export function thumbprint(jwk: JsonWebKey): string {
	const canonical = JSON.stringify({ crv: jwk.crv, kty: jwk.kty, x: jwk.x });
	return b64url(createHash("sha256").update(canonical).digest());
}

function keyPairFromKeyObject(privateKey: KeyObject): KeyPair {
	const pub = createPublicKey(privateKey).export({
		format: "jwk",
	}) as JsonWebKey;
	if (pub.kty !== "OKP" || pub.crv !== "Ed25519") {
		throw new TypeError(`Expected Ed25519, got kty=${pub.kty}, crv=${pub.crv}`);
	}
	const kid = thumbprint(pub);
	return {
		kid,
		publicJwk: { kty: "OKP", crv: "Ed25519", x: pub.x as string, kid },
		signer: {
			alg: "ed25519",
			keyid: kid,
			// Sync node:crypto Ed25519 — no WebCrypto import / promise hop.
			sign: async (data: string) =>
				new Uint8Array(cryptoSign(null, Buffer.from(data, "utf8"), privateKey)),
		},
	};
}

function passwordFor(opts: KeyOptions): string | undefined {
	return opts.password ?? (process.env[KEY_PASSWORD_ENV] || undefined);
}

async function loadKeypair(
	path: string,
	opts: KeyOptions = {},
): Promise<KeyPair> {
	if (process.platform !== "win32") {
		const mode = (await stat(path)).mode & 0o777;
		if ((mode & 0o077) !== 0) {
			throw new Error(
				`Key file ${path} has mode 0o${mode.toString(8)}; expected 0o600. Fix: chmod 600 ${path}`,
			);
		}
	} else if (!warnedWindows) {
		warnedWindows = true;
		process.emitWarning(
			`Windows detected — file permissions on ${path} cannot be enforced via POSIX mode. Use NTFS ACLs or store the key in a per-user secrets vault.`,
		);
	}
	const pem = await readFile(path, "utf8");
	const encrypted = pem.includes("ENCRYPTED");
	const passphrase = passwordFor(opts);
	if (encrypted && !passphrase) {
		throw new TypeError(
			`Key file ${path} is encrypted; pass { password } or set $${KEY_PASSWORD_ENV}`,
		);
	}
	const key = createPrivateKey(
		encrypted ? { key: pem, format: "pem", passphrase } : pem,
	);
	return keyPairFromKeyObject(key);
}

async function generateKeypairTo(
	path: string,
	opts: KeyOptions = {},
): Promise<KeyPair> {
	await mkdir(dirname(path), { recursive: true });
	if (await exists(path)) {
		const err = new Error(
			`Key already exists at ${path}; refuse overwrite`,
		) as NodeJS.ErrnoException;
		err.code = "EEXIST";
		throw err;
	}
	const { privateKey } = generateKeyPairSync("ed25519");
	const passphrase = passwordFor(opts);
	const pem = privateKey.export(
		passphrase
			? { format: "pem", type: "pkcs8", cipher: "aes-256-cbc", passphrase }
			: { format: "pem", type: "pkcs8" },
	) as string;
	// Race-free 0o600 creation: "wx" = O_WRONLY|O_CREAT|O_EXCL.
	const fh = await open(path, "wx", 0o600);
	try {
		await fh.writeFile(pem);
		await fh.sync();
	} finally {
		await fh.close();
	}
	return keyPairFromKeyObject(privateKey);
}
