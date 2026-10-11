// /register/challenge + /register/submit per D-38 two-step proof-of-key-ownership.
//
// Security properties (2026-10 audit hardening):
//  - kid MUST be the RFC 7638 thumbprint of its key, for every key submitted.
//    Without this, an attacker could submit their own key under a victim's
//    kid and overwrite the victim's directory entry (ON CONFLICT(kid)).
//  - The Signature-Input keyid MUST equal body.kid.
//  - The signature MUST cover `content-digest`, and Content-Digest MUST match
//    the raw body bytes, so kid/challenge/keys are bound to the signature.
//  - Signature-Agent header MUST equal body.signature_agent_url.
//  - Challenges are keyed by nonce (single-use, 5 min); requesting a new
//    challenge never invalidates someone else's pending one.
//  - All errors return JSON; no stack traces leaked. Blocklist and cheap
//    checks run before crypto work. The nonce is consumed before 201.
import { Hono } from "hono";
import { createMiddleware } from "hono/factory";
import { sValidator } from "@hono/standard-validator";
import { getConnInfo } from "hono/cloudflare-workers";
import { verify } from "web-bot-auth";
import { verifierFromJWK } from "web-bot-auth/crypto";
import type { Env } from "../env";
import { isReservedName } from "../blocklist";
import { purgeAgentCache } from "../cache";
import {
  coveredComponents,
  okpThumbprint,
  parseSha256Digest,
  safeEqual,
  sha256B64,
} from "../crypto";
import { verifyDomainOwnership } from "../domain";
import { checkAndIncrementRateLimit } from "../ratelimit";
import { ChallengeBody, SubmitBody } from "../schemas";

type Vars = { rawBody: ArrayBuffer };

const CHALLENGE_TTL_SECONDS = 300;

export const registerRouter = new Hono<{ Bindings: Env; Variables: Vars }>();

// Read the raw body ONCE before validation so the Content-Digest check sees
// the exact bytes that were signed (Hono caches it for the json validator).
const captureRawBody = createMiddleware<{ Bindings: Env; Variables: Vars }>(
  async (c, next) => {
    c.set("rawBody", await c.req.arrayBuffer());
    await next();
  },
);

function clientIp(c: Parameters<typeof getConnInfo>[0]): string {
  return getConnInfo(c).remote.address ?? "unknown";
}

registerRouter.post(
  "/challenge",
  sValidator("json", ChallengeBody),
  async (c) => {
    const { kid } = c.req.valid("json");
    const allowed = await checkAndIncrementRateLimit(
      c.env.DB,
      clientIp(c),
      "challenge",
    );
    if (!allowed) {
      return c.json({ error: "rate_limited", retry_after_seconds: 3600 }, 429);
    }

    const nonceBytes = new Uint8Array(16);
    crypto.getRandomValues(nonceBytes);
    const nonce = Array.from(nonceBytes, (b) =>
      b.toString(16).padStart(2, "0"),
    ).join("");
    const now = Math.floor(Date.now() / 1000);
    const expiresAt = now + CHALLENGE_TTL_SECONDS;

    await c.env.DB.batch([
      c.env.DB.prepare(
        `DELETE FROM registration_challenges WHERE expires_at < ?`,
      ).bind(now),
      c.env.DB.prepare(
        `INSERT INTO registration_challenges (nonce, kid, expires_at) VALUES (?1, ?2, ?3)`,
      ).bind(nonce, kid, expiresAt),
    ]);

    return c.json({ challenge: nonce, expires_at: expiresAt });
  },
);

registerRouter.post(
  "/submit",
  captureRawBody,
  sValidator("json", SubmitBody),
  async (c) => {
    const body = c.req.valid("json");
    const allowed = await checkAndIncrementRateLimit(
      c.env.DB,
      clientIp(c),
      "submit",
    );
    if (!allowed) return c.json({ error: "rate_limited" }, 429);

    const blocked = isReservedName(body.client_name);
    if (blocked) {
      return c.json(
        {
          error: "reserved_name",
          blocked_token: blocked,
          guidance:
            "If you represent this organization and want this name in the directory, open an issue at https://github.com/MrKoriy/wbauth/issues",
        },
        422,
      );
    }

    // 1. Every key's kid must be its RFC 7638 thumbprint.
    for (const k of body.keys.keys) {
      if (k.kid !== (await okpThumbprint(k))) {
        return c.json({ error: "kid_not_thumbprint", kid: k.kid }, 400);
      }
    }
    const jwk = body.keys.keys.find((k) => k.kid === body.kid);
    if (!jwk) return c.json({ error: "kid_not_in_jwks" }, 400);

    // 2. Signature must cover content-digest, and the digest must match.
    const sigInput = c.req.header("signature-input");
    if (!coveredComponents(sigInput).includes("content-digest")) {
      return c.json({ error: "content_digest_not_signed" }, 400);
    }
    const claimed = parseSha256Digest(c.req.header("content-digest"));
    const actual = await sha256B64(c.get("rawBody"));
    if (!claimed || !safeEqual(claimed, actual)) {
      return c.json({ error: "content_digest_mismatch" }, 400);
    }

    // 3. Signature-Agent header must be the URL being registered.
    if (c.req.header("signature-agent") !== `"${body.signature_agent_url}"`) {
      return c.json({ error: "signature_agent_mismatch" }, 400);
    }

    // 4. Challenge lookup (by nonce, bound to kid).
    const now = Math.floor(Date.now() / 1000);
    const ch = await c.env.DB.prepare(
      `SELECT kid, expires_at FROM registration_challenges WHERE nonce = ?`,
    )
      .bind(body.challenge)
      .first<{ kid: string; expires_at: number }>();
    if (!ch) return c.json({ error: "no_challenge" }, 400);
    if (ch.kid !== body.kid) return c.json({ error: "wrong_challenge" }, 400);
    if (ch.expires_at < now) {
      return c.json({ error: "challenge_expired" }, 400);
    }

    // 5. Verify the RFC 9421 signature with the submitted key; keyid must match.
    const baseVerifier = await verifierFromJWK(jwk);
    try {
      await verify(c.req.raw, async (data, signature, params) => {
        if (params.keyid !== body.kid) {
          throw new Error("keyid does not match body.kid");
        }
        return baseVerifier(data, signature, params);
      });
    } catch (err) {
      return c.json({ error: "signature_invalid", reason: String(err) }, 401);
    }

    // 6. Consume the challenge atomically (single use).
    const consumed = await c.env.DB.prepare(
      `DELETE FROM registration_challenges WHERE nonce = ? AND kid = ? RETURNING nonce`,
    )
      .bind(body.challenge, body.kid)
      .first<{ nonce: string }>();
    if (!consumed) return c.json({ error: "challenge_already_used" }, 409);

    const origin = new URL(c.req.url).origin;
    const domain = await verifyDomainOwnership(
      body.signature_agent_url,
      body.kid,
      jwk.x,
      origin,
    );

    await c.env.DB.prepare(
      `INSERT INTO agents (
         kid, client_name, client_uri, signature_agent_url, expected_user_agent,
         contacts, purpose, targeted_content, rate_control, keys,
         created_at, last_updated, domain_verified, domain_verified_at
       ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?11, ?12, ?13)
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
         last_updated        = ?11,
         domain_verified     = ?12,
         domain_verified_at  = ?13`,
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
        domain.verified ? 1 : 0,
        domain.verified ? now : null,
      )
      .run();

    // Remaining challenges for this kid are moot once registered.
    await c.env.DB.prepare(`DELETE FROM registration_challenges WHERE kid = ?`)
      .bind(body.kid)
      .run();

    c.executionCtx.waitUntil(purgeAgentCache(origin, body.kid));

    const directoryUrl = `${origin}/.well-known/http-message-signatures-directory/${body.kid}`;
    return c.json(
      {
        kid: body.kid,
        directory_url: directoryUrl,
        domain_verified: domain.verified,
        domain_verification: domain.reason,
      },
      201,
    );
  },
);
