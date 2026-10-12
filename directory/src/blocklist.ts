// Reserved-name blocklist (D-43, hardened in audit #6).
//
// Exact (case-insensitive) reserved tokens are blocked, as is any name that
// contains a reserved token together with a bot/agent/crawler suffix
// ("googlestyle-app" stays allowed).
//
// Before matching, candidates are normalised so trivial evasions do not work:
//   NFKC → strip diacritics → map Cyrillic/Greek confusables → leetspeak
//   (0→o, 1→l|i, 3→e, 4→a, 5→s, 7→t, @→a, $→s) → drop non-alphanumerics.
// The check is applied to every identity-bearing field: client_name,
// expected_user_agent and the client_uri host.
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
  "chatgpt",
  "claude",
  "perplexity",
];
const SUFFIXES = ["bot", "agent", "crawler", "spider"];

const CONFUSABLES: Record<string, string> = {
  а: "a", в: "b", е: "e", ё: "e", к: "k", м: "m", н: "h", о: "o", р: "p",
  с: "c", т: "t", у: "y", х: "x", і: "i", ї: "i", ј: "j", ѕ: "s", ԁ: "d",
  ɡ: "g", ɢ: "g", ı: "i", ℓ: "l",
  α: "a", β: "b", ε: "e", ι: "i", κ: "k", ο: "o", ρ: "p", τ: "t", υ: "u", ν: "v",
};
const LEET: Record<string, string> = {
  "0": "o", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", $: "s", "!": "i", "|": "l",
};

/** Normalised variants of `s` (two, because "1" may stand for "l" or "i"). */
export function normalizeName(s: string): string[] {
  let t = s
    .normalize("NFKC")
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{M}+/gu, "");
  t = [...t].map((ch) => CONFUSABLES[ch] ?? LEET[ch] ?? ch).join("");
  const variants = new Set<string>();
  for (const one of ["l", "i"]) {
    variants.add(t.replace(/1/g, one).replace(/[^a-z0-9]+/g, ""));
  }
  return [...variants];
}

/** Returns the matched reserved token if `name` is reserved, else null. */
export function isReservedName(name: string): string | null {
  for (const lower of normalizeName(name)) {
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
  }
  return null;
}

export interface ReservedHit {
  field: "client_name" | "expected_user_agent" | "client_uri";
  token: string;
}

/** Checks every identity-bearing registration field (audit #6). */
export function findReservedField(body: {
  client_name: string;
  expected_user_agent?: string | null;
  client_uri?: string | null;
}): ReservedHit | null {
  const n = isReservedName(body.client_name);
  if (n) return { field: "client_name", token: n };
  if (body.expected_user_agent) {
    const u = isReservedName(body.expected_user_agent);
    if (u) return { field: "expected_user_agent", token: u };
  }
  if (body.client_uri) {
    let host = "";
    try {
      host = new URL(body.client_uri).hostname;
    } catch {
      host = body.client_uri;
    }
    // A brand as a whole DNS label ("openai.com.evil.io", "g00gle.bot.dev")
    // is the classic impersonation pattern; "googlestyle.app" stays allowed.
    const labels = host.toLowerCase().split(".").slice(0, -1);
    for (const t of TOKENS) {
      if (labels.some((l) => normalizeName(l).includes(t))) {
        return { field: "client_uri", token: t };
      }
    }
    const h = isReservedName(host);
    if (h) return { field: "client_uri", token: h };
  }
  return null;
}
