// Direct exercise of web-bot-auth verify on a request signed in-process.
//
// This catches regressions where the verifier integration breaks (e.g. a
// future web-bot-auth bump changes the API shape) before they can sneak
// into the /register/submit path.
import { describe, it, expect } from "vitest";
import { generateKeyPairSync, createHash } from "node:crypto";
import { signatureHeaders, verify } from "web-bot-auth";
import { signerFromJWK, verifierFromJWK } from "web-bot-auth/crypto";

function b64url(buf: Buffer): string {
  return buf
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function makeKeypair() {
  const { privateKey, publicKey } = generateKeyPairSync("ed25519");
  const priv = privateKey.export({ format: "jwk" }) as {
    kty: string;
    crv: string;
    d: string;
    x: string;
  };
  const pub = publicKey.export({ format: "jwk" }) as {
    kty: string;
    crv: string;
    x: string;
  };
  const canonical = JSON.stringify({ crv: pub.crv, kty: pub.kty, x: pub.x });
  const kid = b64url(createHash("sha256").update(canonical).digest());
  return {
    full: { kty: "OKP", crv: "Ed25519", kid, x: priv.x, d: priv.d },
    publicJwk: { kty: "OKP", crv: "Ed25519", kid, x: pub.x },
  };
}

describe("web-bot-auth verify integration", () => {
  it("happy path: sign a Request, then verify it succeeds", async () => {
    const { full, publicJwk } = makeKeypair();
    const url = "https://example.com/register/submit";
    const sigAgent = "https://example.com/.well-known/http-message-signatures-directory/" + publicJwk.kid;
    const headers: Record<string, string> = {
      "content-type": "application/json",
      "signature-agent": `"${sigAgent}"`,
    };
    const signer = await signerFromJWK(full as unknown as JsonWebKey);
    const sig = await signatureHeaders(
      { method: "POST", url, headers },
      signer,
      { created: new Date(), expires: new Date(Date.now() + 60_000) },
    );
    headers["Signature"] = sig["Signature"];
    headers["Signature-Input"] = sig["Signature-Input"];

    const req = new Request(url, {
      method: "POST",
      headers,
      body: JSON.stringify({ ping: "pong" }),
    });
    const verifier = await verifierFromJWK(publicJwk as unknown as JsonWebKey);
    await expect(verify(req, verifier)).resolves.toBeUndefined();
  });

  it("signature_invalid: tampered Signature header rejects", async () => {
    const { full, publicJwk } = makeKeypair();
    const url = "https://example.com/register/submit";
    const sigAgent = "https://example.com/.well-known/http-message-signatures-directory/" + publicJwk.kid;
    const headers: Record<string, string> = {
      "content-type": "application/json",
      "signature-agent": `"${sigAgent}"`,
    };
    const signer = await signerFromJWK(full as unknown as JsonWebKey);
    const sig = await signatureHeaders(
      { method: "POST", url, headers },
      signer,
      { created: new Date(), expires: new Date(Date.now() + 60_000) },
    );
    // Flip the FIRST char of the base64 signature blob deterministically.
    // (The base64 alphabet is [A-Za-z0-9+/=]; XOR-rotating into a guaranteed
    // different alphabet member yields a syntactically valid but
    // cryptographically wrong signature.)
    const tampered = sig["Signature"].replace(
      /=:([A-Za-z0-9+/=]+):/,
      (_m, b64: string) => {
        const swap: Record<string, string> = {
          A: "B",
          B: "A",
          a: "b",
          b: "a",
          "0": "1",
          "1": "0",
          "+": "/",
          "/": "+",
          "=": "z",
        };
        const first = b64[0];
        const replaced = swap[first] ?? (first === "z" ? "y" : "z");
        return `=:${replaced}${b64.slice(1)}:`;
      },
    );
    expect(tampered).not.toBe(sig["Signature"]);
    headers["Signature"] = tampered;
    headers["Signature-Input"] = sig["Signature-Input"];

    const req = new Request(url, { method: "POST", headers });
    const verifier = await verifierFromJWK(publicJwk as unknown as JsonWebKey);
    await expect(verify(req, verifier)).rejects.toBeDefined();
  });
});
