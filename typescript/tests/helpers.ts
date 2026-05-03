import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// typescript/tests/helpers.ts → repo root is two levels up.
const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
export const VECTORS_DIR = resolve(REPO_ROOT, "spec", "test-vectors");

export interface VectorInput {
  name: string;
  description: string;
  request: {
    method: string;
    url: string;
    headers: Record<string, string>;
    body: string | null;
  };
  identity: {
    private_key_jwk: JsonWebKey;
    retiring_key_jwk?: JsonWebKey;
    signature_agent_url: string;
  };
  signing_params: {
    created: number;
    expires_after_seconds: number;
    nonce: string;
    label: string;
    covered_components: string[];
  };
}

export interface VectorExpected {
  kid: string;
  signature_input_value: string;
  signature_value: string;
  signature_agent_value: string;
  jwks_kid_thumbprint: string;
  jwks_full?: { keys: JsonWebKey[] };
}

export interface Vector {
  name: string;
  input: VectorInput;
  expected: VectorExpected;
}

export function loadAllVectors(): Vector[] {
  return readdirSync(VECTORS_DIR)
    .filter((name) => statSync(resolve(VECTORS_DIR, name)).isDirectory())
    .filter((name) => existsSync(resolve(VECTORS_DIR, name, "input.json")))
    .map((name) => ({
      name,
      input: JSON.parse(readFileSync(resolve(VECTORS_DIR, name, "input.json"), "utf-8")),
      expected: JSON.parse(readFileSync(resolve(VECTORS_DIR, name, "expected.json"), "utf-8")),
    }));
}
