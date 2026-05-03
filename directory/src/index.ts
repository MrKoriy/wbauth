export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/ping") {
      const { results } = await env.DB.prepare(
        "SELECT COUNT(*) as count FROM hello"
      ).all<{ count: number }>();
      return Response.json({ ok: true, row_count: results[0].count });
    }
    return new Response("Day 1 hello-world", { status: 200 });
  },
};
