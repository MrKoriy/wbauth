/**
 * Identity unit tests (Phase 4 Plan 01 Task 1).
 *
 * Mirrors python/tests/test_identity.py — same behaviors:
 * - fromTestKey produces the canonical RFC 9421 Appendix B.1.4 kid.
 * - Constructor rejects non-https signatureAgentUrl (defensive guard).
 * - loadOrGenerate creates a 0o600 PKCS8 PEM keyfile on first call,
 *   loads it on subsequent calls; same kid both times (D-60).
 * - loadOrGenerate refuses a key file with mode wider than 0o600 on POSIX.
 * - exportJwks returns the public-only JWK shape (no private "d" field).
 * - rotate produces a 2-key JWKS with the previous active demoted to retiring.
 * - toString and util.inspect both render REDACTED — never the raw key (IDENT-08).
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { chmodSync, existsSync, mkdtempSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { inspect } from "node:util";
import { Identity } from "../src/identity.js";

let tmp: string;

beforeEach(() => {
  tmp = mkdtempSync(join(tmpdir(), "wbauth-id-"));
});

afterEach(() => {
  rmSync(tmp, { recursive: true, force: true });
});

describe("Identity", () => {
  it("fromTestKey returns RFC 9421 Appendix B.1.4 test-key kid", async () => {
    const id = await Identity.fromTestKey("https://example.com/agent.json");
    expect(id.kid).toBe("poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U");
  });

  it("constructor rejects non-https signatureAgentUrl", async () => {
    await expect(Identity.fromTestKey("http://insecure/")).rejects.toThrow(
      /https:\/\//,
    );
  });

  it("loadOrGenerate creates 0o600 keyfile on first call, reloads same kid on second", async () => {
    const path = join(tmp, "key.pem");
    const id1 = await Identity.loadOrGenerate(path, {
      signatureAgentUrl: "https://example.com/agent.json",
    });
    expect(existsSync(path)).toBe(true);
    if (process.platform !== "win32") {
      expect(statSync(path).mode & 0o777).toBe(0o600);
    }
    const id2 = await Identity.loadOrGenerate(path, {
      signatureAgentUrl: "https://example.com/agent.json",
    });
    // Same key file → same kid (round-trip stable).
    expect(id2.kid).toBe(id1.kid);
  });

  it("loadOrGenerate refuses wider-than-0o600 keyfile on POSIX", async () => {
    if (process.platform === "win32") return;
    const path = join(tmp, "key.pem");
    await Identity.loadOrGenerate(path, {
      signatureAgentUrl: "https://example.com/agent.json",
    });
    chmodSync(path, 0o644);
    await expect(
      Identity.loadOrGenerate(path, {
        signatureAgentUrl: "https://example.com/agent.json",
      }),
    ).rejects.toThrow(/0o600|chmod 600|mode/);
  });

  it("exportJwks returns single key with public-only fields (no private 'd')", async () => {
    const id = await Identity.fromTestKey("https://example.com/agent.json");
    const jwks = id.exportJwks();
    expect(jwks.keys).toHaveLength(1);
    const k = jwks.keys[0]!;
    expect(k).toMatchObject({ kty: "OKP", crv: "Ed25519" });
    expect(k).not.toHaveProperty("d");
    expect(k).toHaveProperty("kid");
    expect((k as { kid: string }).kid).toBe(
      "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U",
    );
  });

  it("rotate produces 2-key JWKS [active, retiring] with original kid second", async () => {
    const path = join(tmp, "rotated.pem");
    const original = await Identity.fromTestKey("https://example.com/agent.json");
    const rotated = await original.rotate(path);
    const jwks = rotated.exportJwks();
    expect(jwks.keys).toHaveLength(2);
    // The retiring entry preserves the original kid (the test-key kid).
    expect((jwks.keys[1] as { kid: string }).kid).toBe(
      "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U",
    );
    // The new active key has a different kid.
    expect(rotated.kid).not.toBe(
      "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U",
    );
    expect((jwks.keys[0] as { kid: string }).kid).toBe(rotated.kid);
  });

  it("toString and util.inspect both render REDACTED — never raw key", async () => {
    const id = await Identity.fromTestKey("https://example.com/agent.json");
    const s = id.toString();
    expect(s).toContain("REDACTED");
    // The test-key 'd' value MUST NOT appear anywhere in the rendered repr.
    expect(s).not.toContain("n4Ni-HpISpVObnQMW0wOhCKROaIKqKtW_2ZYb2p9KcU");
    const inspected = inspect(id);
    expect(inspected).toContain("REDACTED");
    expect(inspected).not.toContain("n4Ni-HpISpVObnQMW0wOhCKROaIKqKtW_2ZYb2p9KcU");
  });
});
