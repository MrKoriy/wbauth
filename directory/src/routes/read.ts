// Read endpoints per D-41 + Open Question #1 resolution.
//
//   GET /.well-known/http-message-signatures-directory          (root, signed JWKS for the directory's own key)
//   GET /.well-known/http-message-signatures-directory/{kid}    (signed agent JWKS)
//   GET /agents/{kid}                                           (full Signature Agent Card, JSON)
//   GET /agents                                                 (paginated; ?all=true returns up to 10000)
//   GET /static/all.json                                        (full snapshot for nightly Action — Plan 03-02)
//
// Cache-Control: `public, max-age=300` on the well-known endpoints — NO `immutable`
// per Pitfall 1 + Open Question #4 resolution. The JWKS document at /{kid} CAN
// change with multi-key rotation even though the kid itself is content-addressed.
//
// Implementation source: 03-RESEARCH.md Example 5.
//
// NOTE on imports: web-bot-auth 0.1.3 re-exports `directoryResponseHeaders`
// from its main entry (the symbol originates in the http-message-sig dep).
// The "/http-message-sig" subpath that earlier docs imply is NOT a published
// subpath export; importing from it fails at compile time.
import { Hono } from "hono";
import { directoryResponseHeaders } from "web-bot-auth";

import type { Env } from "../env";
import { getDirectorySigner, getDirectoryPublicJwks } from "../signing";

export const readRouter = new Hono<{ Bindings: Env }>();

const WELL_KNOWN_CONTENT_TYPE =
  "application/http-message-signatures-directory+json";

// Directory's OWN public JWKS (1-element). Per Open Question #1: external
// verifiers fetch this to discover the directory's signing key, so they can
// verify the per-kid signed responses.
readRouter.get("/.well-known/http-message-signatures-directory", async (c) => {
  const jwks = getDirectoryPublicJwks(c.env.DIRECTORY_PRIVATE_JWK);
  const signer = await getDirectorySigner(c.env.DIRECTORY_PRIVATE_JWK);

  const now = new Date();
  const sigHeaders = await directoryResponseHeaders(
    {
      response: {
        status: 200,
        headers: { "content-type": WELL_KNOWN_CONTENT_TYPE },
      },
      request: { method: "GET", url: c.req.url, headers: {} },
    },
    [signer],
    { created: now, expires: new Date(now.getTime() + 300_000) },
  );

  return new Response(JSON.stringify(jwks), {
    status: 200,
    headers: {
      "content-type": WELL_KNOWN_CONTENT_TYPE,
      "cache-control": "public, max-age=300",
      Signature: sigHeaders["Signature"],
      "Signature-Input": sigHeaders["Signature-Input"],
    },
  });
});

// Per-kid agent JWKS, signed by the directory's key.
readRouter.get(
  "/.well-known/http-message-signatures-directory/:kid",
  async (c) => {
    const kid = c.req.param("kid");
    const row = await c.env.DB.prepare(
      `SELECT keys FROM agents WHERE kid = ?`,
    )
      .bind(kid)
      .first<{ keys: string }>();
    if (!row) return c.json({ error: "not_found" }, 404);

    const jwks = JSON.parse(row.keys);
    const body = JSON.stringify(jwks);
    const signer = await getDirectorySigner(c.env.DIRECTORY_PRIVATE_JWK);

    const now = new Date();
    const sigHeaders = await directoryResponseHeaders(
      {
        response: {
          status: 200,
          headers: { "content-type": WELL_KNOWN_CONTENT_TYPE },
        },
        request: { method: "GET", url: c.req.url, headers: {} },
      },
      [signer],
      { created: now, expires: new Date(now.getTime() + 300_000) },
    );

    return new Response(body, {
      status: 200,
      headers: {
        "content-type": WELL_KNOWN_CONTENT_TYPE,
        "cache-control": "public, max-age=300",
        Signature: sigHeaders["Signature"],
        "Signature-Input": sigHeaders["Signature-Input"],
      },
    });
  },
);

// Full Signature Agent Card (unsigned JSON, short cache).
readRouter.get("/agents/:kid", async (c) => {
  const kid = c.req.param("kid");
  const row = await c.env.DB.prepare(
    `SELECT kid, client_name, client_uri, signature_agent_url, expected_user_agent,
            contacts, purpose, targeted_content, rate_control, keys,
            created_at, last_updated
     FROM agents WHERE kid = ?`,
  )
    .bind(kid)
    .first();
  if (!row) return c.json({ error: "not_found" }, 404);
  const card = {
    ...row,
    contacts: JSON.parse((row as { contacts?: string }).contacts ?? "[]"),
    keys: JSON.parse((row as { keys: string }).keys),
  };
  c.header("cache-control", "public, max-age=60");
  return c.json(card);
});

// Paginated list — 50/page default; ?all=true returns up to 10000 in one page
// (intentional escape hatch for the nightly snapshot job — Plan 03-02 prefers
// /static/all.json but this works as a fallback).
readRouter.get("/agents", async (c) => {
  const all = c.req.query("all") === "true";
  const page = Math.max(1, parseInt(c.req.query("page") ?? "1", 10));
  const limit = all ? 10000 : 50;
  const offset = (page - 1) * limit;
  const { results } = await c.env.DB.prepare(
    `SELECT kid, client_name, signature_agent_url, created_at
     FROM agents ORDER BY created_at DESC LIMIT ? OFFSET ?`,
  )
    .bind(limit, offset)
    .all();
  c.header("cache-control", "public, max-age=300");
  return c.json({ page, count: results.length, agents: results });
});

// Full snapshot — Plan 03-02's nightly GitHub Action consumes this.
readRouter.get("/static/all.json", async (c) => {
  const { results } = await c.env.DB.prepare(
    `SELECT kid, client_name, client_uri, signature_agent_url, expected_user_agent,
            contacts, purpose, targeted_content, rate_control, keys,
            created_at, last_updated
     FROM agents ORDER BY created_at DESC LIMIT 10000`,
  ).all();
  const agents = results.map((row) => {
    const r = row as { contacts?: string; keys: string } & Record<string, unknown>;
    return {
      ...r,
      contacts: JSON.parse(r.contacts ?? "[]"),
      keys: JSON.parse(r.keys),
    };
  });
  c.header("cache-control", "public, max-age=300");
  return c.json({ generated_at: Math.floor(Date.now() / 1000), agents });
});
