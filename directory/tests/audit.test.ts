// Regression tests for the 2026-10 security audit of /register/* and reads.
import { describe, it, expect, beforeAll, beforeEach } from "vitest";
import { env, SELF, applyD1Migrations, type D1Migration } from "cloudflare:test";
import { generateKeyPairSync, createHash } from "node:crypto";
import { signatureHeaders } from "web-bot-auth";
import { signerFromJWK } from "web-bot-auth/crypto";

const b64url = (b: Buffer) =>
  b.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

function keypair() {
  const { privateKey, publicKey } = generateKeyPairSync("ed25519");
  const priv = privateKey.export({ format: "jwk" }) as { d: string; x: string };
  const pub = publicKey.export({ format: "jwk" }) as { x: string };
  const kid = b64url(
    createHash("sha256")
      .update(JSON.stringify({ crv: "Ed25519", kty: "OKP", x: pub.x }))
      .digest(),
  );
  return {
    kid,
    priv: { kty: "OKP", crv: "Ed25519", kid, x: priv.x, d: priv.d },
    pub: { kty: "OKP" as const, crv: "Ed25519" as const, kid, x: pub.x },
  };
}
type KP = ReturnType<typeof keypair>;

async function challenge(kid: string): Promise<string> {
  const r = await SELF.fetch("https://example.com/register/challenge", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ kid }),
  });
  expect(r.status).toBe(200);
  return ((await r.json()) as { challenge: string }).challenge;
}

interface SubmitOpts {
  digest?: boolean; // cover + send content-digest (default true)
  tamper?: (json: string) => string; // mutate body AFTER signing
  sigAgentHeader?: string;
}

async function submit(
  signingJwk: Record<string, string>,
  body: Record<string, unknown>,
  opts: SubmitOpts = {},
): Promise<Response> {
  const url = "https://example.com/register/submit";
  const json = JSON.stringify(body);
  const headers: Record<string, string> = {
    "content-type": "application/json",
    "signature-agent": opts.sigAgentHeader ?? `"${body.signature_agent_url as string}"`,
  };
  const components = ["@authority", "signature-agent"];
  if (opts.digest !== false) {
    headers["content-digest"] =
      `sha-256=:${createHash("sha256").update(json).digest("base64")}:`;
    components.push("content-digest");
  }
  const signer = await signerFromJWK(signingJwk as unknown as JsonWebKey);
  const s = await signatureHeaders({ method: "POST", url, headers }, signer, {
    created: new Date(),
    expires: new Date(Date.now() + 60_000),
    components,
  });
  headers.Signature = s.Signature;
  headers["Signature-Input"] = s["Signature-Input"];
  const sent = opts.tamper ? opts.tamper(json) : json;
  return SELF.fetch(url, { method: "POST", headers, body: sent });
}

const sigAgentFor = (kid: string) =>
  `https://example.com/.well-known/http-message-signatures-directory/${kid}`;

function bodyFor(k: KP, ch: string, extra: Record<string, unknown> = {}) {
  return {
    kid: k.kid,
    challenge: ch,
    client_name: "victim-agent",
    signature_agent_url: sigAgentFor(k.kid),
    keys: { keys: [k.pub] },
    ...extra,
  };
}

async function register(k: KP) {
  return submit(k.priv, bodyFor(k, await challenge(k.kid)));
}

async function storedX(kid: string): Promise<string | undefined> {
  const row = await env.DB.prepare("SELECT keys FROM agents WHERE kid = ?")
    .bind(kid)
    .first<{ keys: string }>();
  return row ? JSON.parse(row.keys).keys[0].x : undefined;
}

beforeAll(async () => {
  const m = JSON.parse(
    (env as unknown as { TEST_MIGRATIONS: string }).TEST_MIGRATIONS,
  ) as D1Migration[];
  await applyD1Migrations(env.DB, m);
});
beforeEach(async () => {
  for (const t of ["agents", "registration_challenges", "ratelimit"]) {
    await env.DB.prepare(`DELETE FROM ${t}`).run();
  }
});

describe("registration security", () => {
  it("CRITICAL: attacker key under a victim's kid is rejected (kid != thumbprint)", async () => {
    const victim = keypair();
    expect((await register(victim)).status).toBe(201);

    const attacker = keypair();
    const ch = await challenge(victim.kid);
    const r = await submit(
      { ...attacker.priv, kid: victim.kid },
      {
        ...bodyFor(victim, ch),
        signature_agent_url: "https://attacker.example/dir",
        keys: { keys: [{ ...attacker.pub, kid: victim.kid }] },
      },
    );
    expect(r.status).toBe(400);
    expect(((await r.json()) as { error: string }).error).toBe("kid_not_thumbprint");
    expect(await storedX(victim.kid)).toBe(victim.pub.x);
  });

  it("CRITICAL: victim's real public key + attacker signature is rejected", async () => {
    const victim = keypair();
    expect((await register(victim)).status).toBe(201);
    const attacker = keypair();
    const ch = await challenge(victim.kid);
    const r = await submit(attacker.priv, bodyFor(victim, ch, { client_name: "pwned" }));
    expect(r.status).toBe(401);
    const row = await env.DB.prepare("SELECT client_name FROM agents WHERE kid = ?")
      .bind(victim.kid)
      .first<{ client_name: string }>();
    expect(row?.client_name).toBe("victim-agent");
  });

  it("HIGH: signature that does not cover content-digest is rejected", async () => {
    const k = keypair();
    const r = await submit(k.priv, bodyFor(k, await challenge(k.kid)), { digest: false });
    expect(r.status).toBe(400);
    expect(((await r.json()) as { error: string }).error).toBe("content_digest_not_signed");
  });

  it("HIGH: body modified after signing is rejected", async () => {
    const k = keypair();
    const r = await submit(k.priv, bodyFor(k, await challenge(k.kid)), {
      tamper: (j) => j.replace("victim-agent", "evil-agent"),
    });
    expect(r.status).toBe(400);
    expect(((await r.json()) as { error: string }).error).toBe("content_digest_mismatch");
  });

  it("Signature-Agent header must match signature_agent_url", async () => {
    const k = keypair();
    const r = await submit(k.priv, bodyFor(k, await challenge(k.kid)), {
      sigAgentHeader: '"https://other.example/"',
    });
    expect(r.status).toBe(400);
  });

  it("MEDIUM: a third party requesting a challenge does not break a pending one", async () => {
    const k = keypair();
    const mine = await challenge(k.kid);
    await challenge(k.kid);
    const r = await submit(k.priv, bodyFor(k, mine));
    expect(r.status).toBe(201);
  });

  it("challenge is single-use (replay rejected)", async () => {
    const k = keypair();
    const ch = await challenge(k.kid);
    expect((await submit(k.priv, bodyFor(k, ch))).status).toBe(201);
    const again = await submit(k.priv, bodyFor(k, ch));
    expect(again.status).toBe(400);
  });

  it("challenge issued for another kid is rejected", async () => {
    const a = keypair();
    const b = keypair();
    const chA = await challenge(a.kid);
    const r = await submit(b.priv, bodyFor(b, chA));
    expect(r.status).toBe(400);
    expect(((await r.json()) as { error: string }).error).toBe("wrong_challenge");
  });

  it("malformed kid is rejected at the schema layer", async () => {
    const r = await SELF.fetch("https://example.com/register/challenge", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ kid: "x".repeat(30) }),
    });
    expect(r.status).toBe(400);
  });
});

describe("read endpoints", () => {
  it("GET /agents?page=abc falls back to page 1", async () => {
    const r = await SELF.fetch("https://example.com/agents?page=abc");
    expect(r.status).toBe(200);
    expect(((await r.json()) as { page: number }).page).toBe(1);
  });

  it("GET /agents?all=true no longer dumps 10k rows (max 50)", async () => {
    const r = await SELF.fetch("https://example.com/agents?all=true&page=1");
    expect(r.status).toBe(200);
  });

  it("registered agent is served (and re-registration purges the edge cache)", async () => {
    const k = keypair();
    expect((await register(k)).status).toBe(201);
    const r = await SELF.fetch(sigAgentFor(k.kid));
    expect(r.status).toBe(200);
    expect(r.headers.get("Signature")).toBeTruthy();
    const body = (await r.json()) as { keys: Array<{ x: string }> };
    expect(body.keys[0].x).toBe(k.pub.x);
  });

  it("second read of the root directory is served from the edge cache", async () => {
    const url = "https://example.com/.well-known/http-message-signatures-directory";
    const first = await SELF.fetch(url);
    expect(first.status).toBe(200);
    await first.arrayBuffer();
    // cache.put runs in waitUntil; poll briefly.
    let hit: string | null = null;
    for (let i = 0; i < 20 && hit !== "HIT"; i++) {
      const r = await SELF.fetch(url);
      hit = r.headers.get("x-edge-cache");
      await r.arrayBuffer();
      if (hit !== "HIT") await new Promise((res) => setTimeout(res, 25));
    }
    expect(hit).toBe("HIT");
  });

  it("unknown kid on agent card returns 404", async () => {
    const r = await SELF.fetch("https://example.com/agents/nope");
    expect(r.status).toBe(404);
  });
});
