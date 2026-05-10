/**
 * Pure-function signer for Web Bot Auth (RFC 9421).
 *
 * Mirrors python/src/wbauth/signer.py — same defaults (Ed25519, tag=
 * "web-bot-auth", expires=created+60s, covered components ["@authority",
 * "signature-agent"] + "content-digest" for bodies).
 *
 * The function delegates all RFC 9421 mechanics (signing-base canonicalization,
 * structured-field encoding, Ed25519 signing) to `web-bot-auth` 0.1.3's
 * `signatureHeaders`. We only own the Web Bot Auth profile glue: pre-setting
 * Signature-Agent (Pitfall 6), picking covered components, defaulting expires.
 */
import {
  signatureHeaders,
  type SignatureParams,
} from "web-bot-auth";
import type { Identity } from "./identity.js";
import type { NormalizedRequest } from "./normalized-request.js";

// ---------- Module constants (HARD-CODED — typos = silent verifier reject) ----------

/** IETF Web Bot Auth profile mandate. NEVER change. Pitfall 6. */
const WEB_BOT_AUTH_TAG = "web-bot-auth";
/** Canonical Signature label. Most verifier examples assume "sig1". */
const DEFAULT_LABEL = "sig1";
/** Default expires window. 60s leaves NTP-skew + network-latency headroom. */
const DEFAULT_EXPIRES_SECONDS = 60;
/** Methods that may carry a body and therefore want content-digest covered. */
const DIGEST_METHODS = new Set(["POST", "PUT", "PATCH"]);
// WEB_BOT_AUTH_TAG is enforced internally by web-bot-auth's signatureHeaders;
// we keep the constant for greppability of the profile invariant.
void WEB_BOT_AUTH_TAG;

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
  /** Anti-replay nonce. Defaults to web-bot-auth's `generateNonce()` (64-byte b64). */
  nonce?: string;
  /** Signature label (the `sig1=` prefix). Defaults to "sig1". */
  label?: string;
}

// ---------- Components selector (mirror Python `_components_for`) ----------

function componentsFor(method: string, hasBody: boolean): string[] {
  const base = ["@authority", "signature-agent"];
  if (hasBody && DIGEST_METHODS.has(method.toUpperCase())) {
    base.push("content-digest");
  }
  return base;
}

// ---------- Public API ----------

/**
 * Sign a NormalizedRequest with the Web Bot Auth profile.
 *
 * Mutates `request.headers` in place: writes Signature-Agent BEFORE building
 * the signing base (Pitfall 6 — without pre-set, web-bot-auth defaults to
 * `["@authority"]` only and silently breaks byte-equality with the Python
 * signer). After signatureHeaders returns, also writes Signature and
 * Signature-Input back into `request.headers`.
 *
 * @returns the same three values as a typed dataclass for callers that prefer
 * a return value over header inspection.
 */
export async function sign(
  request: NormalizedRequest,
  identity: Identity,
  opts: SignOptions = {},
): Promise<SignatureHeaders> {
  // 1. Defensive https:// check — Identity ctor enforces it too, but a future
  // bypassed ctor would otherwise leak http://. Pitfall 1.
  if (!identity.signatureAgentUrl.startsWith("https://")) {
    throw new Error(
      `signatureAgentUrl must be https://, got: ${identity.signatureAgentUrl}`,
    );
  }

  // 2. Set Signature-Agent header (RFC 8941 string in double quotes).
  // CRITICAL: must be set BEFORE signatureHeaders inspects the message,
  // otherwise web-bot-auth picks REQUEST_COMPONENTS_WITHOUT_SIGNATURE_AGENT.
  const signatureAgentHeader = `"${identity.signatureAgentUrl}"`;
  request.headers["Signature-Agent"] = signatureAgentHeader;

  // 3. Defaults.
  const created = opts.created ?? new Date();
  const expiresAfterSeconds =
    opts.expiresAfterSeconds ?? DEFAULT_EXPIRES_SECONDS;
  const expires = new Date(created.getTime() + expiresAfterSeconds * 1000);
  const label = opts.label ?? DEFAULT_LABEL;

  // 4. Components based on body presence.
  const hasBody = request.body !== null && request.body !== undefined;
  const components = componentsFor(request.method, hasBody);

  // 5. Build a Web `Request` for web-bot-auth's `signatureHeaders`.
  const headers = new Headers();
  for (const [k, v] of Object.entries(request.headers)) headers.set(k, v);
  const init: RequestInit = { method: request.method, headers };
  if (hasBody) init.body = request.body!;
  const req = new Request(request.url, init);

  // 6. Delegate to web-bot-auth. The signer is the active key's pre-resolved
  // Signer (cached in Identity at construction time).
  const params: SignatureParams = {
    created,
    expires,
    key: label,
    components,
    ...(opts.nonce !== undefined ? { nonce: opts.nonce } : {}),
  };
  const result = await signatureHeaders(req, identity._signer(), params);

  // 7. Mutate request.headers (mirror Python signer behavior).
  request.headers["Signature"] = result.Signature;
  request.headers["Signature-Input"] = result["Signature-Input"];

  return {
    signature: result.Signature,
    signatureInput: result["Signature-Input"],
    signatureAgent: signatureAgentHeader,
  };
}
