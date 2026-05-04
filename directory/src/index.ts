// Phase 3 production directory backend entrypoint.
//
// Replaces the Phase 1 hello-world handler. Mounts the read endpoints and
// the /register/* router, exposes /healthz, and installs an onError handler
// that returns a generic 500 (V7 ASVS — never leak stack traces to clients;
// detailed errors go only to `wrangler tail` via console.error).
import { Hono } from "hono";

import type { Env } from "./env";
import { readRouter } from "./routes/read";
import { registerRouter } from "./routes/register";

const app = new Hono<{ Bindings: Env }>();

app.get("/healthz", (c) => c.json({ ok: true }));

// Read endpoints — long cache, no auth.
app.route("/", readRouter);

// Registration — POST only, rate-limited inside the router (D-40).
app.route("/register", registerRouter);

// Generic error handler — V7 ASVS: no stack traces leaked.
app.onError((err, c) => {
  console.error("worker_error", err);
  return c.json({ error: "internal" }, 500);
});

export default app;
