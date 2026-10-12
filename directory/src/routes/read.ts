// Read endpoints per D-41 + Open Question #1 resolution.
//
//   GET /.well-known/http-message-signatures-directory          (root, signed JWKS for the directory's own key)
//   GET /.well-known/http-message-signatures-directory/{kid}    (signed agent JWKS)
//   GET /agents/{kid}                                           (full Signature Agent Card, JSON)
//   GET /agents?cursor=…                                        (keyset-paginated, 50/page)
//   GET /static/all.json?cursor=…                               (snapshot, keyset-paginated, 1000/page)
//
// Contacts are PII and never served publicly (audit #7).
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
import { edgeCached } from "../cache";
import { getDirectorySigner, getDirectoryPublicJwks } from "../signing";

export const readRouter = new Hono<{ Bindings: Env }>();

const PAGE_SIZE = 50;
const SNAPSHOT_PAGE_SIZE = 1000;
// Legacy ?page=N (OFFSET) is still honoured for small N only; use cursors.
const MAX_LEGACY_PAGE = 20;

const PUBLIC_COLUMNS = `kid, client_name, client_uri, signature_agent_url, expected_user_agent,
            purpose, targeted_content, rate_control, keys,
            created_at, last_updated, domain_verified, domain_verified_at`;

interface Cursor {
  t: number;
  k: string;
}

function encodeCursor(c: Cursor): string {
  return btoa(`${c.t}:${c.k}`).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function decodeCursor(raw: string | undefined): Cursor | null {
  if (!raw || raw.length > 128) return null;
  try {
    const s = atob(raw.replace(/-/g, "+").replace(/_/g, "/"));
    const m = s.match(/^(\d{1,15}):([A-Za-z0-9_-]{1,64})$/);
    return m ? { t: Number(m[1]), k: m[2] } : null;
  } catch {
    return null;
  }
}

async function keysetPage(
  db: D1Database,
  columns: string,
  limit: number,
  cursor: Cursor | null,
  offset = 0,
): Promise<{ rows: Record<string, unknown>[]; next: string | null }> {
  const where = cursor ? `WHERE (created_at < ?1 OR (created_at = ?1 AND kid < ?2))` : "";
  const sql = `SELECT ${columns} FROM agents ${where}
     ORDER BY created_at DESC, kid DESC LIMIT ${limit + 1}${offset ? ` OFFSET ${offset}` : ""}`;
  const stmt = db.prepare(sql);
  const { results } = await (cursor ? stmt.bind(cursor.t, cursor.k) : stmt).all();
  const rows = results as Record<string, unknown>[];
  let next: string | null = null;
  if (rows.length > limit) {
    rows.length = limit;
    const last = rows[rows.length - 1];
    next = encodeCursor({ t: Number(last.created_at), k: String(last.kid) });
  }
  return { rows, next };
}

function toCard(row: Record<string, unknown>): Record<string, unknown> {
  return {
    ...row,
    domain_verified: Boolean(row.domain_verified),
    keys: JSON.parse(row.keys as string),
  };
}

// Edge-cache every read endpoint (see src/cache.ts).
readRouter.use("/.well-known/*", edgeCached);
readRouter.use("/agents", edgeCached);
readRouter.use("/agents/*", edgeCached);
readRouter.use("/static/*", edgeCached);

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

// Per-kid agent JWKS, signed by the directory's key. The stored `keys`
// column is already the canonical public-only JWKS string, so it is served
// verbatim — no parse/stringify on the hot path (audit #19).
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

    return new Response(row.keys, {
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

// Public Signature Agent Card (unsigned JSON, short cache). No contacts.
readRouter.get("/agents/:kid", async (c) => {
  const kid = c.req.param("kid");
  const row = await c.env.DB.prepare(
    `SELECT ${PUBLIC_COLUMNS} FROM agents WHERE kid = ?`,
  )
    .bind(kid)
    .first<Record<string, unknown>>();
  if (!row) return c.json({ error: "not_found" }, 404);
  c.header("cache-control", "public, max-age=60");
  return c.json(toCard(row));
});

// Keyset-paginated list (stable under concurrent inserts, O(log n) per page).
// Follow `next_cursor` until it is null.
readRouter.get("/agents", async (c) => {
  const cursor = decodeCursor(c.req.query("cursor"));
  const rawPage = Number.parseInt(c.req.query("page") ?? "1", 10);
  const page = cursor
    ? 1
    : Number.isFinite(rawPage)
      ? Math.min(MAX_LEGACY_PAGE, Math.max(1, rawPage))
      : 1;
  const { rows, next } = await keysetPage(
    c.env.DB,
    "kid, client_name, signature_agent_url, created_at, domain_verified",
    PAGE_SIZE,
    cursor,
    cursor ? 0 : (page - 1) * PAGE_SIZE,
  );
  for (const r of rows) r.domain_verified = Boolean(r.domain_verified);
  c.header("cache-control", "public, max-age=300");
  return c.json({ page, count: rows.length, next_cursor: next, agents: rows });
});

// Snapshot for the nightly Action — keyset-paginated (no 10k silent cap).
readRouter.get("/static/all.json", async (c) => {
  const cursor = decodeCursor(c.req.query("cursor"));
  const { rows, next } = await keysetPage(
    c.env.DB,
    PUBLIC_COLUMNS,
    SNAPSHOT_PAGE_SIZE,
    cursor,
  );
  c.header("cache-control", "public, max-age=300");
  return c.json({
    generated_at: Math.floor(Date.now() / 1000),
    count: rows.length,
    next_cursor: next,
    agents: rows.map(toCard),
  });
});
