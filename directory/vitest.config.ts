// vitest config for the Phase 3 directory worker.
//
// Uses @cloudflare/vitest-pool-workers via the v0.15.x `cloudflareTest`
// vite plugin entrypoint. Boots a real Workers runtime per test with a
// fresh, in-memory D1 binding pointed at the wbauth-directory schema.
//
// Migrations are read at config-load time via `readD1Migrations()` (Node
// side) and surfaced to test files via vitest's `provide`/`inject` channel
// so each test file can call `applyD1Migrations(env.DB, migrations)` from
// inside the worker isolate.
//
// We also synthesize a fresh Ed25519 JWK at config-load time and inject it
// as the DIRECTORY_PRIVATE_JWK binding so signed read-endpoint tests work
// without a real Cloudflare secret.
import { resolve } from "node:path";
import { generateKeyPairSync, createHash } from "node:crypto";
import {
  cloudflareTest,
  readD1Migrations,
} from "@cloudflare/vitest-pool-workers";
import { defineConfig } from "vitest/config";

function b64url(buf: Buffer): string {
  return buf
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function makeDirectoryJwk(): string {
  const { privateKey, publicKey } = generateKeyPairSync("ed25519");
  const privJwk = privateKey.export({ format: "jwk" }) as {
    kty: string;
    crv: string;
    d: string;
    x: string;
  };
  const pubJwk = publicKey.export({ format: "jwk" }) as {
    kty: string;
    crv: string;
    x: string;
  };
  const canonical = JSON.stringify({
    crv: pubJwk.crv,
    kty: pubJwk.kty,
    x: pubJwk.x,
  });
  const kid = b64url(createHash("sha256").update(canonical).digest());
  return JSON.stringify({
    kty: privJwk.kty,
    crv: privJwk.crv,
    kid,
    d: privJwk.d,
    x: privJwk.x,
  });
}

const TEST_DIRECTORY_JWK = makeDirectoryJwk();
const migrationsPromise = readD1Migrations(
  resolve(__dirname, "./migrations"),
);

export default defineConfig(async () => {
  const migrations = await migrationsPromise;
  return {
    plugins: [
      cloudflareTest({
        wrangler: { configPath: "./wrangler.jsonc" },
        miniflare: {
          bindings: {
            DIRECTORY_PRIVATE_JWK: TEST_DIRECTORY_JWK,
            // Inject migrations as a JSON-serializable binding so the worker
            // isolate can read them via `env.TEST_MIGRATIONS` and pass to
            // `applyD1Migrations`. (vitest's `provide` channel is not yet
            // wired through the cloudflareTest plugin in 0.15.x.)
            TEST_MIGRATIONS: JSON.stringify(migrations),
          },
        },
      }),
    ],
  };
});
