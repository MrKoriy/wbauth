/**
 * Adapter byte-equal conformance vs vector 01 (Phase 4 Plan 01 Task 3).
 *
 * Cross-language oracle gate (D-64): the TS adapter `createSignedFetch`
 * must produce Signature, Signature-Input, and Signature-Agent that are
 * byte-identical to what python/src/wbauth/adapters/httpx_auth.py emits
 * for the same `spec/test-vectors/01-basic-get/input.json` request.
 *
 * Implementation note: `adapters/fetch.ts` has a top-level `import { sign }`,
 * so vi.spyOn cannot intercept at runtime (Pitfall 2). We use vi.mock — it
 * is hoisted by vitest before module init — to inject vector-fixed
 * created/nonce/label into every sign() call.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Identity } from "../../src/identity.js";
import { loadAllVectors } from "../helpers.js";

const v01 = loadAllVectors().find((x) => x.name === "01-basic-get");
if (!v01) {
  throw new Error("Vector 01-basic-get missing — required for conformance test");
}
const vector = v01;

// Hoisted mock — replaces "../../src/signer.js" before adapters/fetch.ts links.
// Delegate to the real sign() but inject vector-fixed signing params so the
// produced headers are reproducible and byte-comparable to the expected.json.
vi.mock("../../src/signer.js", async () => {
  const actual =
    await vi.importActual<typeof import("../../src/signer.js")>(
      "../../src/signer.js",
    );
  return {
    ...actual,
    sign: (
      req: Parameters<typeof actual.sign>[0],
      id: Parameters<typeof actual.sign>[1],
      opts: Parameters<typeof actual.sign>[2] = {},
    ) =>
      actual.sign(req, id, {
        ...opts,
        created: new Date(vector.input.signing_params.created * 1000),
        expiresAfterSeconds: vector.input.signing_params.expires_after_seconds,
        nonce: vector.input.signing_params.nonce,
        label: vector.input.signing_params.label,
      }),
  };
});

// Import AFTER vi.mock so adapter binds to the patched sign.
const { createSignedFetch } = await import("../../src/adapters/fetch.js");

describe("adapter conformance — byte-equal vs vector 01", () => {
  let captured: { url: string; init?: RequestInit }[] = [];
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    captured = [];
    fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (url, init) => {
        captured.push({ url: String(url), init });
        return new Response(null, { status: 200 });
      });
  });

  afterEach(() => fetchSpy.mockRestore());

  it("createSignedFetch produces byte-equal headers vs spec/test-vectors/01-basic-get/expected.json", async () => {
    const id = await Identity.fromTestKey(
      vector.input.identity.signature_agent_url,
    );
    const sf = createSignedFetch(id);
    await sf(vector.input.request.url);
    const h = (captured[0]!.init?.headers ?? {}) as Record<string, string>;
    expect(h["Signature-Input"]).toBe(vector.expected.signature_input_value);
    expect(h["Signature"]).toBe(vector.expected.signature_value);
    expect(h["Signature-Agent"]).toBe(vector.expected.signature_agent_value);
  });
});
