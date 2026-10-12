// Read-path caching (audit #19).
//
// Read endpoints are hot (every verifier resolves Signature-Agent through
// them) but change rarely. Two layers sit in front of D1 + Ed25519 signing:
//
//   1. An in-isolate LRU (works everywhere, including *.workers.dev where the
//      Cache API is a no-op). Bounded by entry count and total bytes.
//   2. The Cache API (`caches.default`) on custom domains.
//
// Both keep a response for EDGE_TTL_SECONDS (60 s). Directory signatures are
// minted with a 300 s lifetime, so a cached copy always has ≥ 240 s of
// validity left. Clients still see `max-age=300`.
//
// Every cached 200 carries a strong ETag over the body; `If-None-Match`
// yields 304 without touching D1 (audit #21).
import { createMiddleware } from "hono/factory";
import type { Env } from "./env";

export const EDGE_TTL_SECONDS = 60;
const MEMORY_MAX_ENTRIES = 256;
const MEMORY_MAX_BYTES = 8 * 1024 * 1024;

interface MemEntry {
  status: number;
  headers: [string, string][];
  body: ArrayBuffer;
  until: number;
}

const memory = new Map<string, MemEntry>();
let memoryBytes = 0;

function memGet(key: string, now: number): MemEntry | undefined {
  const e = memory.get(key);
  if (!e) return undefined;
  memory.delete(key);
  if (e.until <= now) {
    memoryBytes -= e.body.byteLength;
    return undefined;
  }
  memory.set(key, e); // LRU bump
  return e;
}

function memPut(key: string, e: MemEntry): void {
  if (e.body.byteLength > MEMORY_MAX_BYTES / 4) return;
  const old = memory.get(key);
  if (old) {
    memory.delete(key);
    memoryBytes -= old.body.byteLength;
  }
  memory.set(key, e);
  memoryBytes += e.body.byteLength;
  while (memory.size > MEMORY_MAX_ENTRIES || memoryBytes > MEMORY_MAX_BYTES) {
    const oldest = memory.keys().next().value as string;
    memoryBytes -= memory.get(oldest)?.body.byteLength ?? 0;
    memory.delete(oldest);
  }
}

/** Test hook / purge helper. */
export function clearMemoryCache(prefix?: string): void {
  for (const [k, e] of memory) {
    if (!prefix || k.startsWith(prefix)) {
      memory.delete(k);
      memoryBytes -= e.body.byteLength;
    }
  }
}

function edgeCache(): Cache | undefined {
  return (globalThis as unknown as { caches?: { default?: Cache } }).caches
    ?.default;
}

async function etagFor(body: ArrayBuffer): Promise<string> {
  const d = new Uint8Array(await crypto.subtle.digest("SHA-256", body));
  let s = "";
  for (const b of d.subarray(0, 16)) s += b.toString(16).padStart(2, "0");
  return `"${s}"`;
}

function notModified(req: Request, etag: string | null, headers: Headers): Response | null {
  const inm = req.headers.get("if-none-match");
  if (!etag || !inm) return null;
  const tags = inm.split(",").map((t) => t.trim().replace(/^W\//, ""));
  if (!tags.includes(etag) && !tags.includes("*")) return null;
  const h = new Headers();
  for (const k of ["etag", "cache-control", "content-type"]) {
    const v = headers.get(k);
    if (v) h.set(k, v);
  }
  return new Response(null, { status: 304, headers: h });
}

function fromEntry(e: MemEntry, layer: string): Response {
  const res = new Response(e.body.slice(0), { status: e.status, headers: e.headers });
  res.headers.set("x-edge-cache", "HIT");
  res.headers.set("x-cache-layer", layer);
  return res;
}

export const edgeCached = createMiddleware<{ Bindings: Env }>(
  async (c, next) => {
    if (c.req.method !== "GET") return next();
    const key = c.req.url;
    const now = Date.now();

    const mem = memGet(key, now);
    if (mem) {
      const nm = notModified(c.req.raw, new Headers(mem.headers).get("etag"), new Headers(mem.headers));
      return nm ?? fromEntry(mem, "memory");
    }

    const cache = edgeCache();
    const reqKey = new Request(key, { method: "GET" });
    if (cache) {
      const hit = await cache.match(reqKey);
      if (hit) {
        const body = await hit.arrayBuffer();
        const entry: MemEntry = {
          status: hit.status,
          headers: [...hit.headers],
          body,
          until: now + EDGE_TTL_SECONDS * 1000,
        };
        memPut(key, entry);
        const nm = notModified(c.req.raw, hit.headers.get("etag"), hit.headers);
        return nm ?? fromEntry(entry, "edge");
      }
    }

    await next();
    if (c.res.status !== 200) return;
    const body = await c.res.clone().arrayBuffer();
    const etag = await etagFor(body);
    const headers = new Headers(c.res.headers);
    headers.set("etag", etag);
    c.res = new Response(body, { status: 200, headers });
    memPut(key, { status: 200, headers: [...headers], body, until: now + EDGE_TTL_SECONDS * 1000 });

    const nm = notModified(c.req.raw, etag, headers);
    if (nm) c.res = nm;

    if (cache) {
      const stored = new Response(body, { status: 200, headers });
      const cc = stored.headers.get("cache-control") ?? "public";
      stored.headers.set("cache-control", `${cc}, s-maxage=${EDGE_TTL_SECONDS}`);
      c.executionCtx.waitUntil(cache.put(reqKey, stored));
    }
  },
);

/** Drop cached entries for one agent after (re-)registration. */
export async function purgeAgentCache(origin: string, kid: string): Promise<void> {
  // In-isolate: drop the agent's entries and every list/snapshot page.
  clearMemoryCache(`${origin}/.well-known/http-message-signatures-directory/${kid}`);
  clearMemoryCache(`${origin}/agents`);
  clearMemoryCache(`${origin}/static/`);
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
