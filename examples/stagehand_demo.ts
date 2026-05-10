/**
 * Stagehand x wbauth demo (DIST-05).
 *
 * What this demonstrates:
 * - applyTo(page, identity) registers a signing handler on Stagehand's
 *   underlying Playwright page (raw `stagehand.context.pages()[0]`).
 *   Every outgoing request carries Web Bot Auth (RFC 9421) signatures.
 * - Real-mode: runs `stagehand.observe(...)` — read-only, smaller LLM
 *   cost than `stagehand.act(...)` — against https://example.com.
 *   Routes through **OpenRouter** by default (one key → many models);
 *   falls back to direct OpenAI if only OPENAI_API_KEY is set.
 * - Mock-mode (no LLM key): skips Stagehand's LLM-driven calls and
 *   just navigates to our directory Worker
 *   (https://wbauth.silov801.workers.dev/agents). The page.on("request")
 *   listener prints the signed Signature header — the verification
 *   anchor that proves the SDK API surface works without an LLM.
 *
 * Run:
 *   npm install @browserbasehq/stagehand wbauth
 *   npx playwright install chromium      # Stagehand LOCAL still needs Chromium
 *
 *   # Mock mode (no key required):
 *   npx tsx examples/stagehand_demo.ts
 *
 *   # Real mode via OpenRouter (recommended — one key, all models):
 *   OPENROUTER_API_KEY=sk-or-... npx tsx examples/stagehand_demo.ts
 *   # Optional: pick a model
 *   OPENROUTER_API_KEY=sk-or-... WBAUTH_MODEL=anthropic/claude-3.5-sonnet \\
 *     npx tsx examples/stagehand_demo.ts
 *
 *   # Real mode via direct OpenAI (legacy):
 *   OPENAI_API_KEY=sk-... npx tsx examples/stagehand_demo.ts
 *
 * Pitfalls:
 * - `env: "LOCAL"` does NOT mean "no browser needed" — it means
 *   "local Chromium instead of Browserbase." You still need
 *   `playwright install chromium` once (Pitfall 5).
 * - `applyTo(page, identity)` MUST be called BEFORE the first
 *   `page.goto()` (Pitfall 3). page.route only intercepts requests
 *   started after registration.
 *
 * Local-dev tip: if you're hacking on the wbauth TS SDK in this
 * monorepo, `cd typescript && npm link` then `cd examples && npm link
 * wbauth` so the demo picks up your local build.
 *
 * Per CONTEXT D-70: this demo does NOT depend on Cloudflare verifier
 * round-trip. Daily canary (Phase 1) covers full Cloudflare e2e.
 */
import { Stagehand } from "@browserbasehq/stagehand";
import { Identity, applyTo } from "wbauth";

const WORKER_URL = "https://wbauth.silov801.workers.dev/agents";
const KEY_PATH = `${process.env.HOME}/.config/wbauth/key.pem`;

async function previewKid(path: string): Promise<string> {
  // Best-effort: derive the real kid from the on-disk key. Falls back to
  // a placeholder string on first run when the key has not been
  // generated yet (loadOrGenerate will then materialize it).
  try {
    const id = await Identity.loadOrGenerate(path, {
      signatureAgentUrl: "https://example.invalid/placeholder",
    });
    return id.kid;
  } catch {
    return "PLACEHOLDER_KID";
  }
}

interface LlmConfig {
  model: string;
  modelClientOptions: { apiKey: string; baseURL?: string };
  provider: string;
}

function buildLlmConfig(): LlmConfig | null {
  // Priority: OPENROUTER_API_KEY (one key, many models) → OPENAI_API_KEY.
  const openrouterKey = process.env.OPENROUTER_API_KEY;
  if (openrouterKey) {
    const model = process.env.WBAUTH_MODEL ?? "openai/gpt-4o-mini";
    return {
      model,
      // Stagehand model names are provider-prefixed (`openai/gpt-4o`),
      // matching OpenRouter's naming — no extra translation needed.
      modelClientOptions: {
        apiKey: openrouterKey,
        baseURL: "https://openrouter.ai/api/v1",
      },
      provider: "OpenRouter",
    };
  }
  const openaiKey = process.env.OPENAI_API_KEY;
  if (openaiKey) {
    const model = process.env.WBAUTH_MODEL ?? "openai/gpt-4o-mini";
    return {
      model,
      modelClientOptions: { apiKey: openaiKey },
      provider: "OpenAI",
    };
  }
  return null;
}

async function main(): Promise<void> {
  const llm = buildLlmConfig();
  const hasLlmKey = llm !== null;
  console.log(
    `[demo] ${hasLlmKey ? `Real mode (${llm!.provider}, model=${llm!.model})` : "Mock mode"}`,
  );

  const stagehand = new Stagehand({
    env: "LOCAL",
    ...(llm ? { model: llm.model, modelClientOptions: llm.modelClientOptions } : {}),
    localBrowserLaunchOptions: { headless: true },
  });
  await stagehand.init();

  try {
    // Stagehand exposes the raw Playwright Page via context.pages().
    const page = stagehand.context.pages()[0]!;

    const kid = await previewKid(KEY_PATH);
    const identity = await Identity.loadOrGenerate(KEY_PATH, {
      signatureAgentUrl: `https://wbauth.silov801.workers.dev/.well-known/http-message-signatures-directory/${kid}`,
    });

    // CRITICAL: register signing BEFORE the first navigation (Pitfall 3).
    await applyTo(page, identity);

    // Verification anchor: print every signed outgoing request. The
    // mock-mode "did something" proof.
    page.on("request", (req) => {
      const sig = req.headers()["signature"];
      if (sig) {
        console.log(
          `[signed] ${req.method()} ${req.url()} sig=${sig.slice(0, 40)}...`,
        );
      }
    });

    if (hasLlmKey) {
      await page.goto("https://example.com");
      const result = await stagehand.observe("find the main heading");
      console.log("[stagehand] observed:", result);
    } else {
      await page.goto(WORKER_URL);
      await page.waitForTimeout(500);
      console.log(`\n[demo] Identity kid: ${identity.kid}`);
      console.log("[demo] Signed request fired against Worker.");
    }
  } finally {
    await stagehand.close();
  }
}

main().catch((err: unknown) => {
  console.error(err);
  process.exit(1);
});
