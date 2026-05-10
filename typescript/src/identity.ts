/**
 * Identity, KeyPair, and key-file helpers for the wbauth TypeScript SDK.
 *
 * Mirrors python/src/wbauth/identity.py — same on-disk format (PKCS8
 * NoEncryption PEM at 0o600), same kid (RFC 7638 JWK thumbprint), same
 * multi-key rotation semantics (active + retiring), same REDACTED repr
 * (IDENT-08).
 *
 * Cross-language guarantee (D-60): the PEM file Python writes via
 * `Ed25519PrivateKey.private_bytes(PEM, PKCS8, NoEncryption)` is byte-equal
 * to what Node's `crypto.generateKeyPairSync('ed25519').privateKey.export({
 * format: 'pem', type: 'pkcs8' })` writes. Both runtimes can load each
 * other's keyfile and produce the same kid + signatures.
 *
 * Key implementation choice (Pitfall 1): PEM→JWK is done via Node 20+
 * stdlib `node:crypto.createPrivateKey(pem).export({format:'jwk'})`. We do
 * NOT use `jose` or any third-party JOSE library — the stdlib output is
 * verified byte-identical to what Python's cryptography library produces
 * for the same PKCS8 PEM (RESEARCH §2.2 live verification 2026-05-10).
 */
import {
  closeSync,
  existsSync,
  mkdirSync,
  openSync,
  readFileSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { homedir } from "node:os";
import { dirname, resolve } from "node:path";
import { createPrivateKey, generateKeyPairSync } from "node:crypto";
import type { Signer } from "http-message-sig";
import { signerFromJWK } from "web-bot-auth/crypto";

// ---------- Module constants ----------

/** Default path for the active signing key. Matches Python DEFAULT_KEY_PATH. */
export const DEFAULT_KEY_PATH = resolve(homedir(), ".config", "wbauth", "key.pem");

/**
 * RFC 9421 Appendix B.1.4 publicly-known test key — NEVER use in production.
 * The private "d" component is published in the RFC and known to everyone.
 * `Identity.fromTestKey()` returns an Identity using these bytes.
 */
const TEST_KEY_JWK: JsonWebKey = {
  kty: "OKP",
  crv: "Ed25519",
  d: "n4Ni-HpISpVObnQMW0wOhCKROaIKqKtW_2ZYb2p9KcU",
  x: "JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bs",
};

// ---------- Public types ----------

export interface IdentityOptions {
  /** Stable HTTPS URL where this agent's JWKS is published. Must start with `https://`. */
  signatureAgentUrl: string;
  /** Optional User-Agent string adapters inject when caller did not supply one. */
  userAgent?: string;
}

export interface KeyPair {
  /** Private JWK (includes "d") — used to mint the signer. Never logged. */
  privateJwk: JsonWebKey;
  /** Public JWK ({kty, crv, x, kid}) — what exportJwks returns per key. */
  publicJwk: JsonWebKey & { kid: string };
  /** RFC 7638 base64url-no-pad thumbprint of the public key. */
  kid: string;
  /** Pre-resolved web-bot-auth Signer (caches the imported CryptoKey). */
  signer: Signer;
}

// ---------- Identity class ----------

export class Identity {
  private _active: KeyPair;
  private _retiring: KeyPair | null;
  readonly signatureAgentUrl: string;
  readonly userAgent: string | undefined;

  private constructor(
    active: KeyPair,
    opts: IdentityOptions,
    retiring: KeyPair | null = null,
  ) {
    if (!opts.signatureAgentUrl.startsWith("https://")) {
      throw new Error(
        `signatureAgentUrl must be https://, got: ${opts.signatureAgentUrl}`,
      );
    }
    this._active = active;
    this._retiring = retiring;
    this.signatureAgentUrl = opts.signatureAgentUrl;
    this.userAgent = opts.userAgent;
  }

  // ---------- Public read-only API ----------

  /** The active key's kid (used as `keyid=` param in Signature-Input). */
  get kid(): string {
    return this._active.kid;
  }

  /** Module-internal: returns the resolved Signer for sign() to use. */
  _signer(): Signer {
    return this._active.signer;
  }

  /**
   * Export the public JWKS document.
   *
   * Returns `{keys: [active_jwk]}` if no retiring key is held, or
   * `{keys: [active_jwk, retiring_jwk]}` after a rotation. Active is always
   * first. Verifiers select by `kid`. Mirror of Python `export_jwks`.
   */
  exportJwks(): { keys: JsonWebKey[] } {
    const keys: JsonWebKey[] = [this._active.publicJwk];
    if (this._retiring) keys.push(this._retiring.publicJwk);
    return { keys };
  }

  /**
   * IDENT-07: generate a new active key, demote current to retiring.
   *
   * Returns a NEW Identity (immutable update — the old Identity is unchanged).
   * Any previously-retiring key is dropped (only one overlap window).
   */
  async rotate(newPath: string = DEFAULT_KEY_PATH): Promise<Identity> {
    const newPair = await generateKeypairTo(expandUser(newPath));
    return new Identity(
      newPair,
      { signatureAgentUrl: this.signatureAgentUrl, userAgent: this.userAgent },
      this._active,
    );
  }

  // ---------- Constructors ----------

  /**
   * Primary entry point. Loads `path` if it exists, generates a fresh key
   * there otherwise. The on-disk file is PKCS8 NoEncryption PEM at 0o600,
   * byte-equal to what Python's `Identity.load_or_generate` writes (D-60).
   */
  static async loadOrGenerate(
    path: string = DEFAULT_KEY_PATH,
    opts: IdentityOptions,
  ): Promise<Identity> {
    const resolved = expandUser(path);
    const pair = existsSync(resolved)
      ? await loadKeypair(resolved)
      : await generateKeypairTo(resolved);
    return new Identity(pair, opts);
  }

  /**
   * Construct from the RFC 9421 Appendix B.1.4 publicly-known test key.
   * For tests + Cloudflare debug smoke checks. NEVER use in production.
   * Does NOT write any file to disk.
   */
  static async fromTestKey(signatureAgentUrl: string): Promise<Identity> {
    const pair = await keyPairFromJwk(TEST_KEY_JWK);
    return new Identity(pair, { signatureAgentUrl });
  }

  // ---------- Redaction guarantees (IDENT-08) ----------

  toString(): string {
    return `<Identity REDACTED kid='${this.kid}' sig_agent='${this.signatureAgentUrl}'>`;
  }

  /** util.inspect / console.log render the same REDACTED form (IDENT-08). */
  [Symbol.for("nodejs.util.inspect.custom")](): string {
    return this.toString();
  }
}

// ---------- Helpers (module-private) ----------

function expandUser(path: string): string {
  return resolve(path.startsWith("~") ? path.replace(/^~/, homedir()) : path);
}

async function keyPairFromJwk(privateJwk: JsonWebKey): Promise<KeyPair> {
  const signer = await signerFromJWK(privateJwk);
  // signerFromJWK pre-computes the kid (RFC 7638 thumbprint) into signer.keyid.
  // Reuse it instead of calling jwkToKeyID separately (avoids the 3-arg helper).
  const kid = signer.keyid;
  const publicJwk: JsonWebKey & { kid: string } = {
    kty: privateJwk.kty,
    crv: privateJwk.crv,
    x: privateJwk.x,
    kid,
  };
  return { privateJwk, publicJwk, kid, signer };
}

async function loadKeypair(path: string): Promise<KeyPair> {
  // POSIX permission check (mirror Python — refuse wider-than-0o600).
  // Pitfall 8: Windows lacks POSIX mode bits → emit warning, do not enforce.
  if (process.platform !== "win32") {
    const mode = statSync(path).mode & 0o777;
    if ((mode & 0o077) !== 0) {
      throw new Error(
        `Key file ${path} has mode 0o${mode.toString(8)}; expected 0o600. Fix: chmod 600 ${path}`,
      );
    }
  } else {
    process.emitWarning(
      `Windows detected — file permissions on ${path} cannot be enforced via POSIX mode. Use NTFS ACLs or store the key in a per-user secrets vault.`,
    );
  }
  const pem = readFileSync(path, "utf8");
  const jwk = createPrivateKey(pem).export({ format: "jwk" }) as JsonWebKey;
  if (jwk.kty !== "OKP" || jwk.crv !== "Ed25519") {
    throw new TypeError(
      `Expected Ed25519, got kty=${jwk.kty}, crv=${jwk.crv}`,
    );
  }
  return keyPairFromJwk(jwk);
}

async function generateKeypairTo(path: string): Promise<KeyPair> {
  const dir = dirname(path);
  mkdirSync(dir, { recursive: true });
  if (existsSync(path)) {
    // Belt + suspenders: O_EXCL would catch this too, but raising here gives
    // a cleaner error than the low-level EEXIST.
    throw new Error(`Key already exists at ${path}; refuse overwrite`);
  }
  const { privateKey } = generateKeyPairSync("ed25519");
  const pem = privateKey.export({ format: "pem", type: "pkcs8" }) as string;
  // Race-free 0o600 creation: openSync with "wx" = O_WRONLY|O_CREAT|O_EXCL.
  // Mirrors Python `os.open(path, O_WRONLY|O_CREAT|O_EXCL, 0o600)`.
  const fd = openSync(path, "wx", 0o600);
  try {
    writeFileSync(fd, pem);
  } finally {
    closeSync(fd);
  }
  const jwk = privateKey.export({ format: "jwk" }) as JsonWebKey;
  return keyPairFromJwk(jwk);
}
