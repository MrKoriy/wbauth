/**
 * sign() unit tests (Phase 4 Plan 01 Task 2).
 *
 * Mirrors python/tests/test_signer.py. The most important assertion is the
 * vector 01 byte-equal test — it gates the cross-language oracle (D-64).
 */
import { describe, expect, it } from "vitest";
import { Identity } from "../src/identity.js";
import { sign } from "../src/signer.js";
import { loadAllVectors } from "./helpers.js";

const v01 = loadAllVectors().find((x) => x.name === "01-basic-get");
if (!v01) {
  throw new Error("Vector 01-basic-get missing — required for cross-language oracle test");
}
// Help TypeScript narrow `v01` past the existence check above.
const vector = v01;

describe("sign (signer.ts)", () => {
  it("rejects non-https signatureAgentUrl defensively (even if Identity bypassed)", async () => {
    // Cannot construct Identity with http://, so simulate via shape stub.
    const fake = {
      signatureAgentUrl: "http://insecure/",
      _signer: () => ({}) as never,
    } as unknown as Identity;
    await expect(
      sign({ method: "GET", url: "https://x/", headers: {}, body: null }, fake),
    ).rejects.toThrow(/https:\/\//);
  });

  it("vector 01 (cross-language oracle): byte-equal Signature, Signature-Input, Signature-Agent", async () => {
    const id = await Identity.fromTestKey(vector.input.identity.signature_agent_url);
    const out = await sign(
      {
        method: vector.input.request.method,
        url: vector.input.request.url,
        headers: { ...vector.input.request.headers },
        body: null,
      },
      id,
      {
        created: new Date(vector.input.signing_params.created * 1000),
        expiresAfterSeconds: vector.input.signing_params.expires_after_seconds,
        nonce: vector.input.signing_params.nonce,
        label: vector.input.signing_params.label,
      },
    );
    expect(out.signatureInput).toBe(vector.expected.signature_input_value);
    expect(out.signature).toBe(vector.expected.signature_value);
    expect(out.signatureAgent).toBe(vector.expected.signature_agent_value);
  });

  it("default expires = created + 60s", async () => {
    const id = await Identity.fromTestKey("https://example.com/agent.json");
    const created = new Date("2026-05-10T00:00:00Z");
    const out = await sign(
      { method: "GET", url: "https://x/", headers: {}, body: null },
      id,
      { created },
    );
    const m = out.signatureInput.match(/expires=(\d+)/);
    expect(m).not.toBeNull();
    expect(Number(m![1])).toBe(Math.floor(created.getTime() / 1000) + 60);
  });

  it("POST with body adds content-digest to covered components", async () => {
    const id = await Identity.fromTestKey("https://example.com/agent.json");
    const body = new TextEncoder().encode("hello");
    const headers: Record<string, string> = {
      // Caller already supplied Content-Digest matching the body — the signer
      // will include "content-digest" in covered components for POST + body.
      "Content-Digest": "sha-256=:LPJNul+wow4m6DsqxbninhsWHlwfp0JecwQzYpOLmCQ=:",
    };
    const out = await sign(
      { method: "POST", url: "https://x/", headers, body },
      id,
    );
    expect(out.signatureInput).toContain("content-digest");
  });
});
