/**
 * Cross-language Identity round-trip (D-66 / D-60).
 *
 * Proves the canonical "single key file, two SDKs" guarantee:
 *   1. Python writes a PKCS8 NoEncryption PEM via `cryptography.serialization`
 *      (mirrors `python/src/wbauth/identity.py` lines 282-293 exactly — same
 *      Encoding.PEM + PrivateFormat.PKCS8 + NoEncryption + 0o600 O_EXCL open).
 *   2. TS Identity.loadOrGenerate reads it via Node stdlib `createPrivateKey`.
 *   3. The resulting Identity has the canonical RFC 7638 thumbprint kid for
 *      the IETF Web Bot Auth Appendix B.1.4 test key:
 *      `poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U`.
 *   4. Signing vector 01 with this PEM-loaded Identity produces byte-equal
 *      Signature, Signature-Input, and Signature-Agent vs
 *      `spec/test-vectors/01-basic-get/expected.json` — i.e. exactly what a
 *      JWK-loaded Identity would produce.
 *
 * If this test fails, D-60 is broken: keys minted by `wbauth keygen` (Python)
 * cannot be used by TS users, contradicting the value claim.
 *
 * Environment: requires `python3` + `cryptography` on the path of the python
 * workspace (`cd python && uv run python3 ...`). macOS dev + Linux CI both
 * have this (Phase 1 dep). Windows CI is not supported (Pitfall 8 / POSIX
 * `/tmp` + 0o600 mode bits). The test is silently skipped if `uv` or
 * cryptography is unavailable, so the suite stays green on contributor
 * machines without the python venv.
 */
import { describe, expect, it, beforeAll, afterAll } from "vitest";
import { execSync } from "node:child_process";
import { unlinkSync, existsSync } from "node:fs";
import { Identity } from "../src/identity.js";
import { sign } from "../src/signer.js";
import { loadAllVectors } from "./helpers.js";

const KEY_PATH = "/tmp/wbauth-roundtrip.pem";
const v01 = loadAllVectors().find((v) => v.name === "01-basic-get");
if (!v01) throw new Error("vector 01-basic-get not found");

/**
 * Detect whether `cd ../python && uv run python3` can import `cryptography`.
 * If not, the round-trip tests are skipped. This keeps the suite green on
 * contributor machines that have not run `uv sync` in the python workspace.
 */
function pythonAvailable(): boolean {
  try {
    execSync(
      'cd ../python && uv run python3 -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey"',
      { stdio: "pipe" },
    );
    return true;
  } catch {
    return false;
  }
}

const pythonOK = pythonAvailable();
const describeIfPython = pythonOK ? describe : describe.skip;

beforeAll(() => {
  if (!pythonOK) return;
  if (existsSync(KEY_PATH)) unlinkSync(KEY_PATH);
  // Materialize the RFC 9421 Appendix B.1.4 test key as a PKCS8 NoEncryption
  // PEM via Python — this is precisely the on-disk format that
  // `python/src/wbauth/identity.py::_generate_keypair_to` writes (lines
  // 282-293). Using `cd ../python && uv run python3` so `cryptography` from
  // the python workspace venv is on path. The script body is a hard-coded
  // literal — no test/user input is interpolated, so there is no
  // command-injection surface (T-04-02-02).
  execSync(
    `cd ../python && uv run python3 -c "
import base64, os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
d = base64.urlsafe_b64decode('n4Ni-HpISpVObnQMW0wOhCKROaIKqKtW_2ZYb2p9KcU' + '==')
key = Ed25519PrivateKey.from_private_bytes(d)
pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
fd = os.open('${KEY_PATH}', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
os.write(fd, pem); os.close(fd)
"`,
    { stdio: "pipe" },
  );
});

afterAll(() => {
  if (existsSync(KEY_PATH)) unlinkSync(KEY_PATH);
});

describeIfPython("cross-language Identity round-trip (D-66)", () => {
  it("loads Python-written PKCS8 PEM and produces canonical RFC 7638 kid", async () => {
    const identity = await Identity.loadOrGenerate(KEY_PATH, {
      signatureAgentUrl: v01.input.identity.signature_agent_url,
    });
    expect(identity.kid).toBe("poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U");
  });

  it("signs vector 01 byte-equal vs Python's expected.json output", async () => {
    const identity = await Identity.loadOrGenerate(KEY_PATH, {
      signatureAgentUrl: v01.input.identity.signature_agent_url,
    });
    const out = await sign(
      {
        method: v01.input.request.method,
        url: v01.input.request.url,
        headers: { ...v01.input.request.headers },
        body: null,
      },
      identity,
      {
        created: new Date(v01.input.signing_params.created * 1000),
        expiresAfterSeconds: v01.input.signing_params.expires_after_seconds,
        nonce: v01.input.signing_params.nonce,
        label: v01.input.signing_params.label,
      },
    );
    expect(out.signatureInput).toBe(v01.expected.signature_input_value);
    expect(out.signature).toBe(v01.expected.signature_value);
    expect(out.signatureAgent).toBe(v01.expected.signature_agent_value);
  });
});
