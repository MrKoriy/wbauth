// Domain-ownership proof + rate-limit hardening + UI (2026-10 audit).
import { describe, it, expect, beforeAll, beforeEach } from "vitest";
import { env, SELF, applyD1Migrations, type D1Migration } from "cloudflare:test";
import { generateKeyPairSync, createHash } from "node:crypto";
import { signatureHeaders } from "web-bot-auth";
import { signerFromJWK } from "web-bot-auth/crypto";
import { verifyDomainOwnership, type Fetcher } from "../src/domain";
import { checkAndIncrementRateLimit, ipBucket } from "../src/ratelimit";

const b64url = (b: Buffer) =>
  b.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

function keypair() {
  const { privateKey, publicKey } = generateKeyPairSync("ed25519");
  const priv = privateKey.export({ format: "jwk" }) as { d: string; x: string };
  const pub = publicKey.export({ format: "jwk" }) as { crv: string; kty: string; x: string };
  const kid = b64url(
    createHash("sha256")
      .update(JSON.stringify({ crv: pub.crv, kty: pub.kty, x: pub.x }))
      .digest(),
  );
  return {
    kid,
    priv: { kty: "OKP", crv: "Ed25519", kid, x: priv.x, d: priv.d },
    pub: { kty: "OKP" as const, crv: "Ed25519" as const, kid, x: pub.x },
  };
}

async function register(
  sigAgent: (kid: string, x: string) => string,
  name = "agent-x",
) {
  const k = keypair();
  const ch = await SELF.fetch("https://example.com/register/challenge", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ kid: k.kid }),
  });
  const { challenge } = (await ch.json()) as { challenge: string };
  const body = {
    kid: k.kid,
    challenge,
    client_name: name,
    signature_agent_url: sigAgent(k.kid, k.pub.x),
    keys: { keys: [k.pub] },
  };
  const json = JSON.stringify(body);
  const url = "https://example.com/register/submit";
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
  const r = await SELF.fetch(url, { method: "POST", headers, body: json });
  return { k, r };
}

beforeAll(async () => {
  const m = JSON.parse(
    (env as unknown as { TEST_MIGRATIONS: string }).TEST_MIGRATIONS,
  ) as D1Migration[];
  await applyD1Migrations(env.DB, m);
});
beforeEach(async () => {
  await env.DB.prepare("DELETE FROM agents").run();
  await env.DB.prepare("DELETE FROM registration_challenges").run();
  await env.DB.prepare("DELETE FROM ratelimit").run();
});

describe("verifyDomainOwnership", () => {
  const X = "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo";
  const KID = "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U";
  const json = (o: unknown, status = 200): Fetcher => async () =>
    new Response(JSON.stringify(o), { status });

  it("trusts the directory's own hosted URL", async () => {
    const v = await verifyDomainOwnership(
      `https://dir.example/.well-known/http-message-signatures-directory/${KID}`,
      KID, X, "https://dir.example",
      async () => { throw new Error("must not fetch"); },
    );
    expect(v).toEqual({ verified: true, reason: "hosted_by_directory" });
  });
  it("verifies when the domain publishes the key", async () => {
    const v = await verifyDomainOwnership("https://agent.example/d", KID, X, "https://dir.example",
      json({ keys: [{ kty: "OKP", crv: "Ed25519", x: X }] }));
    expect(v.verified).toBe(true);
  });
  it("rejects a JWKS that lacks the key (impersonation)", async () => {
    const v = await verifyDomainOwnership("https://openai.com/d", KID, X, "https://dir.example",
      json({ keys: [{ kty: "OKP", crv: "Ed25519", x: "other" }] }));
    expect(v).toEqual({ verified: false, reason: "key_not_published" });
  });
  it.each([
    [json({ keys: [] }, 404), "http_404"],
    [json("nope"), "invalid_jwks"],
    [(async () => new Response("{")) as Fetcher, "invalid_jwks"],
    [(async () => { throw new TypeError("dns"); }) as Fetcher, "unreachable"],
    [(async () => new Response("x".repeat(70_000))) as Fetcher, "invalid_jwks"],
  ])("fails closed (%#)", async (f, reason) => {
    const v = await verifyDomainOwnership("https://a.example/d", KID, X, "https://dir.example", f);
    expect(v).toEqual({ verified: false, reason });
  });
});

describe("registration marks domain verification", () => {
  it("self-hosted directory URL → domain_verified=true", async () => {
    const { k, r } = await register(
      (kid) => `https://example.com/.well-known/http-message-signatures-directory/${kid}`,
    );
    expect(r.status).toBe(201);
    expect(((await r.json()) as { domain_verified: boolean }).domain_verified).toBe(true);
    const card = (await (await SELF.fetch(`https://example.com/agents/${k.kid}`)).json()) as {
      domain_verified: boolean;
    };
    expect(card.domain_verified).toBe(true);
  });

  it("foreign domain that publishes the key → domain_verified=true", async () => {
    const { r } = await register((_kid, x) => `https://jwks.test/${x}`);
    const out = (await r.json()) as { domain_verified: boolean; domain_verification: string };
    expect(out).toMatchObject({ domain_verified: true, domain_verification: "jwks_contains_key" });
  });

  it("foreign domain without the key → accepted but flagged unverified", async () => {
    const { k, r } = await register(() => "https://impersonated.invalid/dir");
    expect(r.status).toBe(201);
    const out = (await r.json()) as { domain_verified: boolean; domain_verification: string };
    expect(out.domain_verified).toBe(false);
    expect(out.domain_verification).toBe("http_502");
    const list = (await (await SELF.fetch("https://example.com/agents")).json()) as {
      agents: { kid: string; domain_verified: boolean }[];
    };
    expect(list.agents.find((a) => a.kid === k.kid)?.domain_verified).toBe(false);
  });
});

describe("rate limit hardening", () => {
  it("challenge and submit have separate budgets", async () => {
    for (let i = 0; i < 10; i++) {
      expect(await checkAndIncrementRateLimit(env.DB, "1.1.1.1", "challenge")).toBe(true);
    }
    expect(await checkAndIncrementRateLimit(env.DB, "1.1.1.1", "challenge")).toBe(false);
    expect(await checkAndIncrementRateLimit(env.DB, "1.1.1.1", "submit")).toBe(true);
  });

  it("buckets IPv6 by /64", async () => {
    for (let i = 0; i < 10; i++) {
      await checkAndIncrementRateLimit(env.DB, `2001:db8:1:2::${i.toString(16)}`, "challenge");
    }
    expect(
      await checkAndIncrementRateLimit(env.DB, "2001:db8:1:2:ffff::1", "challenge"),
    ).toBe(false);
    expect(await checkAndIncrementRateLimit(env.DB, "2001:db8:1:3::1", "challenge")).toBe(true);
  });

  it.each([
    ["1.2.3.4", "1.2.3.4"],
    ["2001:db8::1", "2001:0db8:0000:0000::/64"],
    ["2001:DB8:0:0:1:2:3:4", "2001:0db8:0000:0000::/64"],
    ["::ffff:10.0.0.1", "10.0.0.1"],
    ["fe80::1%eth0", "fe80:0000:0000:0000::/64"],
    ["unknown", "unknown"],
    ["not:an:ip:::x", "not:an:ip:::x"],
  ])("ipBucket(%s) = %s", (ip, want) => {
    expect(ipBucket(ip)).toBe(want);
  });
});

describe("UI", () => {
  it("lists agents, escapes HTML and shows verification", async () => {
    await register(
      (kid) => `https://example.com/.well-known/http-message-signatures-directory/${kid}`,
      "good-bot",
    );
    await register(() => "https://evil.invalid/d", "<script>x</script>");
    const r = await SELF.fetch("https://example.com/");
    expect(r.status).toBe(200);
    expect(r.headers.get("content-type")).toContain("text/html");
    const html = await r.text();
    expect(html).toContain("good-bot");
    expect(html).not.toContain("<script>x</script>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("✓ example.com");
    expect(html).toContain("unverified · evil.invalid");
  });

  it("search filters by name and treats % literally", async () => {
    await register(() => "https://a.invalid/d", "alpha-bot");
    await register(() => "https://b.invalid/d", "beta-bot");
    const html = await (await SELF.fetch("https://example.com/?q=alpha")).text();
    expect(html).toContain("alpha-bot");
    expect(html).not.toContain("beta-bot");
    const none = await (await SELF.fetch("https://example.com/?q=%25")).text();
    expect(none).toContain("No agents found");
  });

  it("serves badges", async () => {
    const { k } = await register(
      (kid) => `https://example.com/.well-known/http-message-signatures-directory/${kid}`,
    );
    const ok = await SELF.fetch(`https://example.com/badge/${k.kid}.svg`);
    expect(ok.headers.get("content-type")).toContain("image/svg+xml");
    expect(await ok.text()).toContain("verified");
    const missing = await SELF.fetch(`https://example.com/badge/${"A".repeat(43)}.svg`);
    expect(missing.status).toBe(404);
    expect(await missing.text()).toContain("unknown");
  });
});
