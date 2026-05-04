// Per D-43: exact (case-insensitive) reserved tokens, plus substring-match
// when combined with a bot/agent/crawler suffix.
//
// Per Open Question #5: substring check is case-insensitive (lowercase the
// candidate name once, then match). False-positive guard: a name that contains
// a reserved token but no bot-y suffix is allowed (e.g., "googlestyle-app").
const TOKENS = [
  "google",
  "openai",
  "anthropic",
  "cloudflare",
  "microsoft",
  "meta",
  "apple",
  "amazon",
  "aws",
  "github",
  "stripe",
  "shopify",
];
const SUFFIXES = ["bot", "agent", "crawler"];

/** Returns the matched reserved token if `name` is reserved, else null. */
export function isReservedName(name: string): string | null {
  const lower = name.toLowerCase();
  for (const t of TOKENS) {
    if (lower === t) return t;
  }
  for (const t of TOKENS) {
    if (lower.includes(t)) {
      for (const s of SUFFIXES) {
        if (lower.includes(s)) return t;
      }
    }
  }
  return null;
}
