// Audit v2 fixes: #4 redirects/SSRF, #5 PoP for extra keys, #6 blocklist,
// #7 contacts, #19 caching, #21 keyset pagination + ETag.
import { describe, it, expect, beforeAll, beforeEach } from "vitest";
import { env, SELF, applyD1Migrations, type D1Migration } from "cloudflare:test";
import { generateKeyPairSync, createHash } from "node:crypto";
import { signatureHeaders } from "web-bot-auth";
import { signerFromJWK } from "web-bot-auth/crypto";
import { findReservedField, isReservedName, normalizeName } from "../src/blocklist";
import { isForbiddenHost, verifyDomainOwnership } from "../src/domain";

const b64url = (b: Buffer) =>
  b.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const ORIGIN = "https://example.com";
const sigAgentFor = (kid: string) =>
  `${ORIGIN}/.well-known/http-message-signatures-directory/${kid}`;

function keypair() {
  const { privateKey, publicKey } = generateKeyPairSync("ed25519");
  const priv = privateKey.export({ format: "jwk" }) as { d: string; x: string };
  const pub = publicKey.export({ format: "jwk" }) as { crv: string; kty: string; x: string };
  const kid = b64url(
    createHash("sha256").update(JSON.stringify({ crv: pub.crv, kty: pub.kty, x: pub.x })).digest(),
  );
  return {
    kid,
    priv: { kty: "OKP", crv: "Ed25519", kid, x: priv.x, d: priv.d },
    pub: { kty: "OKP" as const, crv: "Ed25519" as const, kid, x: pub.x },
  };
}
type KP = ReturnType<typeof keypair>;

async function register(k: KP, extra: Record<string, unknown> = {}, keys = [k.pub]) {
  const ch = await SELF.fetch(`${ORIGIN}/register/challenge`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ kid: k.kid }),
  });
  const { challenge } = (await ch.json()) as { challenge: string };
  const body = {
    kid: k.kid,
    challenge,
    client_name: "agent-x",
    signature_agent_url: sigAgentFor(k.kid),
    keys: { keys },
    ...extra,
  };
  const json = JSON.stringify(body);
  const url = `${ORIGIN}/register/submit`;
  const headers: Record<string, string> = {
    "content-type": "application/json",
    "signature-agent": `"${body.signature_agent_url}"`,
    "content-digest": `sha-256=:${createHash("sha256").update(json).digest("base64")}:`,
  };
  const s = await signatureHeaders(
    { method: "POST", url, headers },
    await signerFromJWK(k.priv as unknown as JsonWebKey),
    {
      created: new Date(),
      expires: new Date(Date.now() + 60_000),
      components: ["@authority", "signature-agent", "content-digest"],
    },
  );
  headers.Signature = s.Signature;
  headers["Signature-Input"] = s["Signature-Input"];
  return SELF.fetch(url, { method: "POST", headers, body: json });
}

beforeAll(async () => {
  const m = JSON.parse((env as unknown as { TEST_MIGRATIONS: string }).TEST_MIGRATIONS) as D1Migration[];
  await applyD1Migrations(env.DB, m);
});
beforeEach(async () => {
  await env.DB.prepare("DELETE FROM agents").run();
  await env.DB.prepare("DELETE FROM registration_challenges").run();
  await env.DB.prepare("DELETE FROM ratelimit").run();
});

describe("#6 blocklist normalisation", () => {
  it.each(["G00gleBot", "g\u043E\u043Egle-bot", "Gооgle Bot", "0pena1-agent", "ＧｏｏｇｌｅＢｏｔ", "goo.gle_b0t", "Gõõgle-crawler"])(
    "blocks %s",
    (n) => expect(isReservedName(n)).not.toBeNull(),
  );
  it("normalises confusables and leet", () => {
    expect(normalizeName("Ｇ0０gle")).toContain("google");
    expect(normalizeName("0pena1")).toContain("openai");
  });
  it("keeps the false-positive guard", () => {
    expect(isReservedName("googlestyle-app")).toBeNull();
    expect(isReservedName("legit-bot")).toBeNull();
  });
  it("checks expected_user_agent and client_uri too", () => {
    expect(findReservedField({ client_name: "acme", expected_user_agent: "Mozilla/5.0 (compatible; Googlebot/2.1)" }))
      .toEqual({ field: "expected_user_agent", token: "google" });
    expect(findReservedField({ client_name: "acme", client_uri: "https://openai.com.evil.io/" }))
      .toEqual({ field: "client_uri", token: "openai" });
    expect(findReservedField({ client_name: "acme", client_uri: "https://googlestyle.app/" })).toBeNull();
  });
  it("registration rejects an impersonating User-Agent", async () => {
    const r = await register(keypair(), { expected_user_agent: "GPTBot/1.0 OpenAI-agent" });
    expect(r.status).toBe(422);
    expect(await r.json()).toMatchObject({ error: "reserved_name", field: "expected_user_agent" });
  });
});

describe("#4 domain verification", () => {
  const X = "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo";
  const KID = "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U";
  it("does not follow redirects", async () => {
    let init: RequestInit | undefined;
    const v = await verifyDomainOwnership("https://victim.example/jwks", KID, X, "https://dir.example",
      async (_u, i) => {
        init = i;
        return new Response(null, { status: 302, headers: { location: "https://evil.example/jwks" } });
      });
    expect(init?.redirect).toBe("manual");
    expect(v).toEqual({ verified: false, reason: "redirect_not_allowed" });
  });
  it.each(["127.0.0.1", "10.1.2.3", "169.254.169.254", "192.168.0.1", "localhost", "intranet", "[::1]", "metadata.internal"])(
    "refuses %s",
    async (h) => {
      expect(isForbiddenHost(h)).toBe(true);
      const v = await verifyDomainOwnership(`https://${h}/jwks`, KID, X, "https://dir.example",
        async () => { throw new Error("must not fetch"); });
      expect(v.reason).toBe("forbidden_host");
    },
  );
  it("allows public hosts", () => {
    expect(isForbiddenHost("agent.example.com")).toBe(false);
    expect(isForbiddenHost("8.8.8.8")).toBe(false);
  });
});

describe("#5 proof of possession for extra keys", () => {
  it("rejects a foreign key that was never proven", async () => {
    const me = keypair();
    const victim = keypair();
    const r = await register(me, {}, [me.pub, victim.pub]);
    expect(r.status).toBe(400);
    expect(await r.json()).toMatchObject({ error: "unproven_key", kid: victim.kid });
  });
  it("accepts an extra key that is itself registered (rotation)", async () => {
    const oldK = keypair();
    const newK = keypair();
    expect((await register(oldK)).status).toBe(201);
    expect((await register(newK, {}, [newK.pub, oldK.pub])).status).toBe(201);
    const jwks = (await (await SELF.fetch(sigAgentFor(newK.kid))).json()) as { keys: { kid: string }[] };
    expect(jwks.keys.map((k) => k.kid)).toEqual([newK.kid, oldK.kid]);
  });
});

describe("#7 contacts are private", () => {
  it("are not served by /agents/:kid or /static/all.json", async () => {
    const k = keypair();
    expect((await register(k, { contacts: ["ops@acme.example"] })).status).toBe(201);
    const card = await (await SELF.fetch(`${ORIGIN}/agents/${k.kid}`)).text();
    const all = await (await SELF.fetch(`${ORIGIN}/static/all.json`)).text();
    expect(card).not.toContain("ops@acme.example");
    expect(card).not.toContain("contacts");
    expect(all).not.toContain("ops@acme.example");
    const row = await env.DB.prepare("SELECT contacts FROM agents WHERE kid = ?").bind(k.kid).first<{ contacts: string }>();
    expect(row?.contacts).toContain("ops@acme.example");
  });
});

describe("#21 keyset pagination + ETag", () => {
  async function seed(n: number) {
    const stmt = env.DB.prepare(
      `INSERT INTO agents (kid, client_name, signature_agent_url, keys, created_at, last_updated)
       VALUES (?1, 'a', 'https://a.example/', '{"keys":[]}', ?2, ?2)`,
    );
    await env.DB.batch(
      Array.from({ length: n }, (_, i) => stmt.bind(`k${String(i).padStart(4, "0")}`, 1000 + Math.floor(i / 3))),
    );
  }
  it("walks every row exactly once via next_cursor", async () => {
    await seed(123);
    const seen: string[] = [];
    let cursor: string | null = null;
    let pages = 0;
    do {
      const url: string = `${ORIGIN}/agents?bust=${pages}-${Date.now()}${cursor ? `&cursor=${cursor}` : ""}`;
      const body = (await (await SELF.fetch(url)).json()) as {
        next_cursor: string | null;
        agents: { kid: string }[];
      };
      seen.push(...body.agents.map((a) => a.kid));
      cursor = body.next_cursor;
      pages++;
    } while (cursor && pages < 10);
    expect(pages).toBe(3);
    expect(new Set(seen).size).toBe(123);
  });
  it("snapshot is paginated too", async () => {
    await seed(5);
    const body = (await (await SELF.fetch(`${ORIGIN}/static/all.json?bust=${Date.now()}`)).json()) as {
      count: number;
      next_cursor: string | null;
    };
    expect(body).toMatchObject({ count: 5, next_cursor: null });
  });
  it("garbage cursor falls back to the first page", async () => {
    const r = await SELF.fetch(`${ORIGIN}/agents?cursor=%%%`);
    expect(r.status).toBe(200);
  });
  it("If-None-Match returns 304", async () => {
    const url = `${ORIGIN}/.well-known/http-message-signatures-directory`;
    const first = await SELF.fetch(url);
    const etag = first.headers.get("etag");
    await first.arrayBuffer();
    expect(etag).toMatch(/^"[0-9a-f]{32}"$/);
    const second = await SELF.fetch(url, { headers: { "if-none-match": etag as string } });
    expect(second.status).toBe(304);
  });
});

describe("#19 in-isolate cache", () => {
  it("second read is served from memory even without the Cache API", async () => {
    const url = `${ORIGIN}/agents`;
    await (await SELF.fetch(url)).arrayBuffer();
    const r = await SELF.fetch(url);
    await r.arrayBuffer();
    expect(r.headers.get("x-edge-cache")).toBe("HIT");
  });
});
