// zod schemas for the two POST bodies on /register/*.
// V5 ASVS: every untrusted JSON body is parsed through a strict schema.
// V9 ASVS: signature_agent_url is enforced HTTPS.
import * as z from "zod";

export const ChallengeBody = z.object({
  // RFC 7638 base64url SHA-256 thumbprint is ~43 chars; allow [20..80] as
  // a defensive bound while still rejecting obviously-wrong values.
  kid: z.string().min(20).max(80),
});

export const SubmitBody = z.object({
  kid: z.string(),
  challenge: z.string(),
  client_name: z.string().min(1).max(80),
  client_uri: z.string().url().optional(),
  signature_agent_url: z
    .string()
    .url()
    .refine((u) => u.startsWith("https://"), { message: "must be https://" }),
  expected_user_agent: z.string().optional(),
  contacts: z.array(z.string()).optional(),
  purpose: z.string().optional(),
  targeted_content: z.string().optional(),
  rate_control: z.string().optional(),
  keys: z.object({
    keys: z
      .array(
        z.object({
          kty: z.literal("OKP"),
          crv: z.literal("Ed25519"),
          kid: z.string(),
          x: z.string(),
        }),
      )
      .min(1),
  }),
});

export type SubmitBodyT = z.infer<typeof SubmitBody>;
export type ChallengeBodyT = z.infer<typeof ChallengeBody>;
