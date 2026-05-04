// /register/challenge + /register/submit per D-38 two-step proof-of-key-ownership.
//
// Implementation source: 03-RESEARCH.md Examples 3 + 4.
//
// Security tasks honored:
//  - Task #2 (V7 ASVS): all errors return JSON; no stack traces leaked.
//  - Task #3 (V4 ASVS): blocklist enforced before any expensive crypto work.
//  - Task #4 (replay regression): nonce row is DELETED from
//    registration_challenges BEFORE the 201 response is returned (T-03-02
//    regression guard tested in tests/handlers.test.ts).
import { Hono } from "hono";
import { sValidator } from "@hono/standard-validator";
import { getConnInfo } from "hono/cloudflare-workers";
import { verify } from "web-bot-auth";
import { verifierFromJWK } from "web-bot-auth/crypto";

import type { Env } from "../env";
import { isReservedName } from "../blocklist";
import { checkAndIncrementRateLimit } from "../ratelimit";
import { ChallengeBody, SubmitBody } from "../schemas";

export const registerRouter = new Hono<{ Bindings: Env }>();

registerRouter.post(
  "/challenge",
  sValidator("json", ChallengeBody),
  async (c) => {
    const { kid } = c.req.valid("json");
    const ip = getConnInfo(c).remote.address ?? "unknown";

    // Rate-limit gate (10/day/IP per D-40, D-48). Challenge AND submit both
    // count against the budget so an attacker can't burn nonces freely.
    const allowed = await checkAndIncrementRateLimit(c.env.DB, ip);
    if (!allowed) {
      return c.json({ error: "rate_limited", retry_after_seconds: 3600 }, 429);
    }

    // 128-bit random nonce, hex-encoded.
    const nonceBytes = new Uint8Array(16);
    crypto.getRandomValues(nonceBytes);
    const nonce = Array.from(nonceBytes, (b) =>
      b.toString(16).padStart(2, "0"),
    ).join("");

    const now = Math.floor(Date.now() / 1000);
    const expiresAt = now + 300; // 5 min validity

    // UPSERT: re-issuing a challenge for the same kid replaces the old nonce.
    await c.env.DB.prepare(
      `INSERT INTO registration_challenges (kid, nonce, expires_at)
       VALUES (?1, ?2, ?3)
       ON CONFLICT(kid) DO UPDATE SET nonce = ?2, expires_at = ?3`,
    )
      .bind(kid, nonce, expiresAt)
      .run();

    return c.json({ challenge: nonce, expires_at: expiresAt });
  },
);

registerRouter.post(
  "/submit",
  sValidator("json", SubmitBody),
  async (c) => {
    const body = c.req.valid("json");
    const ip = getConnInfo(c).remote.address ?? "unknown";

    // Rate-limit also gates submit per D-40 ("/register/*").
    const allowed = await checkAndIncrementRateLimit(c.env.DB, ip);
    if (!allowed) return c.json({ error: "rate_limited" }, 429);

    // Blocklist (D-43, D-44). Run before any DB read of challenges so a
    // misnamed registrant doesn't waste their challenge.
    const blocked = isReservedName(body.client_name);
    if (blocked) {
      return c.json(
        {
          error: "reserved_name",
          blocked_token: blocked,
          guidance:
            "If you represent this organization and want this name on agentpassport, contact <maintainer-email-TBD-Phase-5>",
        },
        422,
      );
    }

    // The kid in the body must appear in the JWKS the body submits.
    const jwk = body.keys.keys.find((k) => k.kid === body.kid);
    if (!jwk) return c.json({ error: "kid_not_in_jwks" }, 400);

    // Validate challenge: must exist, must match, must not be expired.
    const ch = await c.env.DB.prepare(
      `SELECT nonce, expires_at FROM registration_challenges WHERE kid = ?`,
    )
      .bind(body.kid)
      .first<{ nonce: string; expires_at: number }>();

    if (!ch) return c.json({ error: "no_challenge" }, 400);
    if (ch.nonce !== body.challenge) {
      return c.json({ error: "wrong_challenge" }, 400);
    }
    if (ch.expires_at < Math.floor(Date.now() / 1000)) {
      return c.json({ error: "challenge_expired" }, 400);
    }

    // Verify the submit POST itself is RFC 9421-signed by the kid's key.
    // The body IS the proof-of-key-ownership: the signature commits to the
    // POST URL, content-digest, and the JWKS the client submitted.
    const verifier = await verifierFromJWK(jwk);
    try {
      await verify(c.req.raw, verifier);
    } catch (err) {
      return c.json(
        { error: "signature_invalid", reason: String(err) },
        401,
      );
    }

    // UPSERT agents row.
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare(
      `INSERT INTO agents (
         kid, client_name, client_uri, signature_agent_url, expected_user_agent,
         contacts, purpose, targeted_content, rate_control, keys,
         created_at, last_updated
       ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?11)
       ON CONFLICT(kid) DO UPDATE SET
         client_name         = ?2,
         client_uri          = ?3,
         signature_agent_url = ?4,
         expected_user_agent = ?5,
         contacts            = ?6,
         purpose             = ?7,
         targeted_content    = ?8,
         rate_control        = ?9,
         keys                = ?10,
         last_updated        = ?11`,
    )
      .bind(
        body.kid,
        body.client_name,
        body.client_uri ?? null,
        body.signature_agent_url,
        body.expected_user_agent ?? null,
        JSON.stringify(body.contacts ?? []),
        body.purpose ?? null,
        body.targeted_content ?? null,
        body.rate_control ?? null,
        JSON.stringify(body.keys),
        now,
      )
      .run();

    // CRITICAL: burn the challenge BEFORE returning 201. If we return first
    // and then DELETE, a network error between response and DELETE would
    // leave a reusable nonce. Test handlers.test.ts asserts the row is gone
    // by the time the response is observed (T-03-02 regression guard).
    await c.env.DB.prepare(
      `DELETE FROM registration_challenges WHERE kid = ?`,
    )
      .bind(body.kid)
      .run();

    const directoryUrl = `${new URL(c.req.url).origin}/.well-known/http-message-signatures-directory/${body.kid}`;
    return c.json({ kid: body.kid, directory_url: directoryUrl }, 201);
  },
);
