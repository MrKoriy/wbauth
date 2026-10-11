// zod schemas for the two POST bodies on /register/*.
// V5 ASVS: every untrusted JSON body is parsed through a strict schema.
// V9 ASVS: signature_agent_url is enforced HTTPS.
import * as z from "zod";

// RFC 7638 SHA-256 thumbprint, base64url without padding = 43 chars.
const Kid = z
  .string()
  .regex(/^[A-Za-z0-9_-]{43}$/, "kid must be an RFC 7638 SHA-256 thumbprint");
// Ed25519 public key, base64url without padding = 43 chars.
const X = z
  .string()
  .regex(/^[A-Za-z0-9_-]{43}$/, "x must be a 32-byte base64url Ed25519 key");
const Short = z.string().max(500);

export const ChallengeBody = z.object({
  kid: Kid,
});

export const SubmitBody = z.object({
  kid: Kid,
  challenge: z.string().regex(/^[0-9a-f]{32}$/),
  client_name: z.string().min(1).max(80),
  client_uri: z.string().url().max(500).optional(),
  signature_agent_url: z
    .string()
    .url()
    .max(500)
    .refine((u) => u.startsWith("https://"), { message: "must be https://" }),
  expected_user_agent: Short.optional(),
  contacts: z.array(z.string().max(200)).max(10).optional(),
  purpose: Short.optional(),
  targeted_content: Short.optional(),
  rate_control: Short.optional(),
  keys: z.object({
    keys: z
      .array(
        z.object({
          kty: z.literal("OKP"),
          crv: z.literal("Ed25519"),
          kid: Kid,
          x: X,
        }),
      )
      .min(1)
      .max(4),
  }),
});

export type SubmitBodyT = z.infer<typeof SubmitBody>;
export type ChallengeBodyT = z.infer<typeof ChallengeBody>;
