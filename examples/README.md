# wbauth examples

Three runnable framework integration demos. All three target our live
directory Worker at `https://wbauth.silov801.workers.dev/agents` in
mock-mode and switch to a real LLM-driven flow when an API key is
detected.

> **Note:** `examples/` is intentionally NOT shipped via PyPI or npm
> (per RESEARCH §Open Questions Q5). Browse this directory on GitHub.

> **Note (D-70):** None of these demos depend on Cloudflare verifier
> round-trip. They prove the SDK API surface works (signed
> `Signature-Input` headers leave the client). Phase 1's daily canary
> handles the full Cloudflare e2e verification path.

---

## browser_use_demo.py — Browser Use × wbauth (DIST-04)

Demonstrates `attach_signing(page, identity)` working on a Browser Use
managed Playwright page.

**Install:**
```bash
uv pip install "browser-use>=0.7,<1" "playwright>=1.59,<2"
playwright install chromium
```

**Run:**
```bash
# Mock mode (no LLM key — opens our Worker directly, prints signed request):
python examples/browser_use_demo.py

# Real mode (LLM key — runs a Browser Use Agent navigating example.com):
OPENAI_API_KEY=sk-... python examples/browser_use_demo.py
# OR
BROWSER_USE_API_KEY=... python examples/browser_use_demo.py
```

**Pitfall:** call `attach_signing(page, identity)` BEFORE `agent.run()` —
`page.route` only intercepts requests started after registration.

**Pitfall:** Browser Use exposes two API entry points; we use the
lower-level `BrowserSession` in mock-mode (no Agent needed) and the
high-level `Browser` + `Agent` in real-mode. Both expose
`get_current_page()` to reach the underlying Playwright Page.

---

## stagehand_demo.ts — Stagehand × wbauth (DIST-05)

Demonstrates `applyTo(page, identity)` working on Stagehand's
underlying Playwright page (raw `stagehand.context.pages()[0]`).

**Install:**
```bash
npm install @browserbasehq/stagehand wbauth
npx playwright install chromium  # Stagehand LOCAL still needs the Chromium binary
```

**Run:**
```bash
# Mock mode (no LLM key — opens our Worker, prints signed request):
npx tsx examples/stagehand_demo.ts

# Real mode (LLM key — runs stagehand.observe on example.com):
OPENAI_API_KEY=sk-... npx tsx examples/stagehand_demo.ts
```

**Pitfall:** Stagehand `env: "LOCAL"` does NOT mean "no browser
needed" — it means "local Chromium instead of Browserbase." You still
need `playwright install chromium` once.

**Pitfall:** call `applyTo(page, identity)` BEFORE the first
`page.goto` — `page.route` only intercepts requests started after
registration.

**Local-dev tip:** if you're hacking on the wbauth TS SDK in this
monorepo, `cd typescript && npm link` then `cd examples && npm link
wbauth` so the demo picks up your local build.

---

## openai_agents_demo.py — OpenAI Agents SDK × wbauth (DIST-06)

Demonstrates `WebBotAuth(identity)` + `httpx.Client` injected into an
OpenAI Agents SDK `@function_tool` so the Agent's tool calls produce
signed HTTP requests.

**Install:**
```bash
uv pip install "openai-agents" "httpx>=0.28,<1"
```

**Run:**
```bash
# Mock mode (no LLM key — calls signed_get directly, prints result + signature presence):
python examples/openai_agents_demo.py

# Real mode (LLM key — runs Runner with a real Agent that calls the tool):
OPENAI_API_KEY=sk-... python examples/openai_agents_demo.py
```

**Note:** The Agent's *own* OpenAI API calls are NOT signed by wbauth
(we don't sign requests TO openai.com). Only the **tool's** outbound
HTTP requests via `httpx.Client(auth=WebBotAuth(identity))` are
signed. This is the right model — the Agent gets identity for the
sites it visits, not for its own LLM calls.

**Note:** Mock-mode does NOT import `agents` (the openai-agents pip
package), so you can run the mock-mode smoke without installing it.

---

## Why these demos exist (background)

Each demo follows the same pattern (per CONTEXT D-67):

1. **Detect LLM key** in env (`OPENAI_API_KEY` etc.)
2. **Real mode**: full Agent loop on a benign target
   (`https://example.com`)
3. **Mock mode**: skip the Agent, run the SDK's signing path directly
   against our Worker
   (`https://wbauth.silov801.workers.dev/agents`), and print the
   signed request

This bifurcation means the demos are runnable on a fresh box — no API
key required for a meaningful smoke run. Phase 5 will base the README
"agent fails on Cloudflare → installs SDK → 3 lines added → request
passes" Loom demo on these scripts.

**Per CONTEXT D-71:** Upstream PRs to Browser Use, Stagehand, and
mcp-agent's `examples/` directories (DIST-07) are NOT in Phase 4.
They are scheduled for Phase 5 (need a public GitHub repo URL +
author identity for review correspondence).
