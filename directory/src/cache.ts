// Edge caching for read endpoints (Cache API).
//
// Read endpoints are hot (every verifier resolves Signature-Agent through
// them) but change rarely. Caching the full signed response for 60 s at the
// edge removes the D1 query and the Ed25519 signing step from the hot path.
// Signatures are minted with a 300 s lifetime, so a cached copy always has
// ≥ 240 s of validity left. Clients still see `max-age=300`.
//
// Note: the Cache API is a no-op on *.workers.dev — attach a custom domain
// to benefit in production.
import { createMiddleware } from "hono/factory";
import type { Env } from "./env";

export const EDGE_TTL_SECONDS = 60;

function edgeCache(): Cache | undefined {
  return (globalThis as unknown as { caches?: { default?: Cache } }).caches
    ?.default;
}

export const edgeCached = createMiddleware<{ Bindings: Env }>(
  async (c, next) => {
    const cache = edgeCache();
    if (!cache || c.req.method !== "GET") return next();
    const key = new Request(c.req.url, { method: "GET" });
    const hit = await cache.match(key);
    if (hit) {
      const res = new Response(hit.body, hit);
      res.headers.set("x-edge-cache", "HIT");
      return res;
    }
    await next();
    if (c.res.status !== 200) return;
    const copy = c.res.clone();
    const stored = new Response(copy.body, copy);
    const cc = stored.headers.get("cache-control") ?? "public";
    stored.headers.set("cache-control", `${cc}, s-maxage=${EDGE_TTL_SECONDS}`);
    c.executionCtx.waitUntil(cache.put(key, stored));
  },
);

/** Drop cached entries for one agent after (re-)registration. */
export async function purgeAgentCache(origin: string, kid: string): Promise<void> {
  const cache = edgeCache();
  if (!cache) return;
  await Promise.all(
    [
      `${origin}/.well-known/http-message-signatures-directory/${kid}`,
      `${origin}/agents/${kid}`,
      `${origin}/agents`,
      `${origin}/static/all.json`,
    ].map((u) => cache.delete(new Request(u))),
  );
}
