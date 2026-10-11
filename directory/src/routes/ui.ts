// Human-facing pages (2026-10 audit, improvement #20).
//
//   GET /                 searchable agent list with "domain verified" marks
//   GET /badge/{kid}.svg  README badge: "Web Bot Auth | verified" / "registered"
import { Hono } from "hono";
import type { Env } from "../env";

export const uiRouter = new Hono<{ Bindings: Env }>();

const esc = (s: unknown) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string,
  );

type Row = {
  kid: string;
  client_name: string;
  signature_agent_url: string;
  purpose: string | null;
  created_at: number;
  domain_verified: number;
};

uiRouter.get("/", async (c) => {
  const q = (c.req.query("q") ?? "").trim().slice(0, 80);
  const like = `%${q.replace(/[\\%_]/g, (m) => `\\${m}`)}%`;
  const { results } = await c.env.DB.prepare(
    `SELECT kid, client_name, signature_agent_url, purpose, created_at, domain_verified
     FROM agents
     WHERE ?1 = '' OR client_name LIKE ?2 ESCAPE '\\' OR kid = ?1
     ORDER BY domain_verified DESC, created_at DESC LIMIT 100`,
  )
    .bind(q, like)
    .all<Row>();
  const rows = results
    .map((r) => {
      const host = (() => {
        try {
          return new URL(r.signature_agent_url).host;
        } catch {
          return "";
        }
      })();
      const mark = r.domain_verified
        ? `<span class="ok" title="signature_agent_url serves this key">✓ ${esc(host)}</span>`
        : `<span class="warn" title="domain not proven — do not trust the claimed host">unverified · ${esc(host)}</span>`;
      return `<tr><td><a href="/agents/${esc(r.kid)}">${esc(r.client_name)}</a><div class="p">${esc(r.purpose)}</div></td>
<td>${mark}</td><td><code>${esc(r.kid.slice(0, 12))}…</code></td>
<td>${new Date(r.created_at * 1000).toISOString().slice(0, 10)}</td></tr>`;
    })
    .join("");
  c.header("cache-control", "public, max-age=60");
  c.header(
    "content-security-policy",
    "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'",
  );
  return c.html(`<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>wbauth directory — Web Bot Auth agents</title>
<style>
:root{color-scheme:light dark;--fg:#111;--bg:#fff;--mut:#666;--line:#e5e5e5;--ok:#0a7d32;--warn:#a15c00}
@media (prefers-color-scheme:dark){:root{--fg:#eee;--bg:#111;--mut:#999;--line:#2a2a2a;--ok:#4cc27a;--warn:#e0a24a}}
body{font:15px/1.5 system-ui,sans-serif;max-width:960px;margin:40px auto;padding:0 16px;color:var(--fg);background:var(--bg)}
h1{font-size:22px;margin:0 0 4px}p.sub{color:var(--mut);margin:0 0 24px}
form{display:flex;gap:8px;margin-bottom:16px}input{flex:1;padding:8px 10px;border:1px solid var(--line);border-radius:6px;background:transparent;color:inherit}
button{padding:8px 14px;border-radius:6px;border:1px solid var(--line);background:var(--fg);color:var(--bg);cursor:pointer}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut)}a{color:inherit}
.p{color:var(--mut);font-size:13px}.ok{color:var(--ok);font-weight:600}.warn{color:var(--warn)}code{font-size:12px}
</style></head><body>
<h1>wbauth directory</h1>
<p class="sub">Public keys of AI agents that sign requests with <a href="https://datatracker.ietf.org/wg/webbotauth/about/">Web Bot Auth</a> (RFC 9421).
<span class="ok">✓</span> = the agent's own domain publishes this key.</p>
<form method="get"><input name="q" value="${esc(q)}" placeholder="Search by name or exact key id" aria-label="Search"><button>Search</button></form>
<table><thead><tr><th>Agent</th><th>Domain</th><th>Key id</th><th>Registered</th></tr></thead>
<tbody>${rows || `<tr><td colspan="4" class="p">No agents found.</td></tr>`}</tbody></table>
<p class="p">JSON: <a href="/agents">/agents</a> · <a href="/static/all.json">/static/all.json</a> · Badge: <code>/badge/&lt;kid&gt;.svg</code></p>
</body></html>`);
});

function badge(label: string, value: string, color: string): string {
  const w = (s: string) => 7 * s.length + 12;
  const lw = w(label);
  const vw = w(value);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${lw + vw}" height="20" role="img" aria-label="${esc(label)}: ${esc(value)}">
<rect width="${lw}" height="20" fill="#111"/><rect x="${lw}" width="${vw}" height="20" fill="${color}"/>
<g fill="#fff" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11" text-anchor="middle">
<text x="${lw / 2}" y="14">${esc(label)}</text><text x="${lw + vw / 2}" y="14">${esc(value)}</text></g></svg>`;
}

uiRouter.get("/badge/:file", async (c) => {
  const kid = c.req.param("file").replace(/\.svg$/, "");
  const row = /^[A-Za-z0-9_-]{43}$/.test(kid)
    ? await c.env.DB.prepare(`SELECT domain_verified FROM agents WHERE kid = ?`)
        .bind(kid)
        .first<{ domain_verified: number }>()
    : null;
  const svg = !row
    ? badge("Web Bot Auth", "unknown", "#9f1d1d")
    : row.domain_verified
      ? badge("Web Bot Auth", "verified", "#0a7d32")
      : badge("Web Bot Auth", "registered", "#6b6b6b");
  return c.body(svg, row ? 200 : 404, {
    "content-type": "image/svg+xml; charset=utf-8",
    "cache-control": "public, max-age=300",
  });
});
