// End-to-end handler tests via the Hono app.
//
// Covers:
//  - GET /healthz
//  - POST /register/challenge happy + invalid-body
//  - POST /register/submit happy path + nonce-burn-before-response (T-03-02 regression)
//  - GET /agents/{kid} 404
//  - GET /agents (empty paginated list)
//  - GET /.well-known/.../<kid> 404
//  - GET /.well-known/http-message-signatures-directory (root: directory's own JWKS)
import { describe, it, expect, beforeAll, beforeEach } from "vitest";
import {
  env,
  SELF,
  applyD1Migrations,
  type D1Migration,
} from "cloudflare:test";
import { generateKeyPairSync, createHash } from "node:crypto";
import { signatureHeaders } from "web-bot-auth";
import { signerFromJWK } from "web-bot-auth/crypto";

function b64url(buf: Buffer): string {
  return buf
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function makeAgentKeypair(): {
  jwk: { kty: "OKP"; crv: "Ed25519"; kid: string; x: string; d: string };
  publicJwk: { kty: "OKP"; crv: "Ed25519"; kid: string; x: string };
} {
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
    jwk: {
      kty: "OKP",
      crv: "Ed25519",
      kid,
      x: priv.x,
      d: priv.d,
    },
    publicJwk: { kty: "OKP", crv: "Ed25519", kid, x: pub.x },
  };
}

beforeAll(async () => {
  const migrations = JSON.parse(
    (env as unknown as { TEST_MIGRATIONS: string }).TEST_MIGRATIONS,
  ) as D1Migration[];
  await applyD1Migrations(env.DB, migrations);
});

beforeEach(async () => {
  // Drop everything between tests so they don't see each other's writes.
  await env.DB.prepare("DELETE FROM agents").run();
  await env.DB.prepare("DELETE FROM registration_challenges").run();
  await env.DB.prepare("DELETE FROM ratelimit").run();
});

describe("GET /healthz", () => {
  it("returns {ok:true}", async () => {
    const r = await SELF.fetch("https://example.com/healthz");
    expect(r.status).toBe(200);
    expect(await r.json()).toEqual({ ok: true });
  });
});

describe("POST /register/challenge", () => {
  it("returns {challenge, expires_at} for a valid kid", async () => {
    const { publicJwk } = makeAgentKeypair();
    const r = await SELF.fetch("https://example.com/register/challenge", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ kid: publicJwk.kid }),
    });
    expect(r.status).toBe(200);
    const body = (await r.json()) as { challenge: string; expires_at: number };
    expect(body.challenge).toMatch(/^[0-9a-f]{32}$/);
    expect(body.expires_at).toBeGreaterThan(Math.floor(Date.now() / 1000));
  });

  it("rejects missing kid with 400", async () => {
    const r = await SELF.fetch("https://example.com/register/challenge", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(r.status).toBe(400);
  });
});

describe("GET /agents/{unknown-kid}", () => {
  it("returns 404", async () => {
    const r = await SELF.fetch("https://example.com/agents/no-such-kid");
    expect(r.status).toBe(404);
  });
});

describe("GET /agents (empty)", () => {
  it("returns {page:1, count:0, agents:[]}", async () => {
    const r = await SELF.fetch("https://example.com/agents");
    expect(r.status).toBe(200);
    const body = (await r.json()) as {
      page: number;
      count: number;
      agents: unknown[];
    };
    expect(body.page).toBe(1);
    expect(body.count).toBe(0);
    expect(body.agents).toEqual([]);
  });
});

describe("GET /.well-known/http-message-signatures-directory (root)", () => {
  it("returns the directory's own JWKS (1 key) with Signature header", async () => {
    const r = await SELF.fetch(
      "https://example.com/.well-known/http-message-signatures-directory",
    );
    expect(r.status).toBe(200);
    expect(r.headers.get("content-type")).toBe(
      "application/http-message-signatures-directory+json",
    );
    expect(r.headers.get("cache-control")).toBe("public, max-age=300");
    expect(r.headers.get("cache-control")).not.toContain("immutable");
    expect(r.headers.get("Signature")).toBeTruthy();
    expect(r.headers.get("Signature-Input")).toBeTruthy();
    const body = (await r.json()) as {
      keys: Array<{ kty: string; crv: string; kid: string; x: string }>;
    };
    expect(body.keys).toHaveLength(1);
    expect(body.keys[0].kty).toBe("OKP");
    expect(body.keys[0].crv).toBe("Ed25519");
  });
});

describe("GET /.well-known/.../{unknown-kid}", () => {
  it("returns 404", async () => {
    const r = await SELF.fetch(
      "https://example.com/.well-known/http-message-signatures-directory/unknown-kid",
    );
    expect(r.status).toBe(404);
  });
});

describe("POST /register/submit (happy + nonce-burn regression)", () => {
  it("verifies the signed submit, persists the agent, and deletes the nonce BEFORE returning 201", async () => {
    const { jwk, publicJwk } = makeAgentKeypair();

    // Step 1 — challenge.
    const c1 = await SELF.fetch("https://example.com/register/challenge", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ kid: publicJwk.kid }),
    });
    const { challenge } = (await c1.json()) as { challenge: string };

    // Step 2 — build the submit body and sign the POST.
    const submitUrl = "https://example.com/register/submit";
    const sigAgent = `https://example.com/.well-known/http-message-signatures-directory/${publicJwk.kid}`;
    const body = {
      kid: publicJwk.kid,
      challenge,
      client_name: "test-agent",
      signature_agent_url: sigAgent,
      keys: { keys: [publicJwk] },
    };
    const bodyJson = JSON.stringify(body);

    const signer = await signerFromJWK(jwk as unknown as JsonWebKey);
    const headers: Record<string, string> = {
      "content-type": "application/json",
      "signature-agent": `"${sigAgent}"`,
    };
    const sigHeaders = await signatureHeaders(
      { method: "POST", url: submitUrl, headers },
      signer,
      {
        created: new Date(),
        expires: new Date(Date.now() + 60_000),
      },
    );
    headers["Signature"] = sigHeaders["Signature"];
    headers["Signature-Input"] = sigHeaders["Signature-Input"];

    const r = await SELF.fetch(submitUrl, {
      method: "POST",
      headers,
      body: bodyJson,
    });
    if (r.status !== 201) {
      // Surface the worker's error message for debugging when a regression breaks signing.
      throw new Error(
        `expected 201, got ${r.status}: ${await r.text()}`,
      );
    }
    const out = (await r.json()) as { kid: string; directory_url: string };
    expect(out.kid).toBe(publicJwk.kid);
    expect(out.directory_url).toBe(sigAgent);

    // T-03-02 regression: by the time the 201 is observed, the nonce must
    // have been deleted from registration_challenges. The await on the
    // response above strictly happens-after the worker's DELETE because the
    // handler awaits the DELETE before constructing the 201 response.
    const ch = await env.DB.prepare(
      `SELECT 1 FROM registration_challenges WHERE kid = ?`,
    )
      .bind(publicJwk.kid)
      .first();
    expect(ch).toBeNull();

    // Agent row should now exist.
    const agent = await env.DB.prepare(
      `SELECT client_name FROM agents WHERE kid = ?`,
    )
      .bind(publicJwk.kid)
      .first<{ client_name: string }>();
    expect(agent?.client_name).toBe("test-agent");
  });
});
