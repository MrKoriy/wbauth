"""Browser Use x wbauth demo (DIST-04).

What this demonstrates:
- attach_signing(page, identity) registers a signing handler on a Playwright
  page that Browser Use (v0.7+) is driving. Every outgoing request from that
  page carries Signature, Signature-Input, and Signature-Agent headers
  (Web Bot Auth profile, RFC 9421).
- Real-mode: runs a live Browser Use Agent against a benign target
  (https://example.com). The agent's HTTP requests are signed. Routes
  through **OpenRouter** by default (one key → many models).
  Falls back to direct OpenAI or Browser Use's hosted backend if those
  keys are set instead.
- Mock-mode (no LLM key): skips the Agent entirely and just opens a
  BrowserSession, attaches signing, navigates to our directory Worker
  (https://wbauth.silov801.workers.dev/agents), and prints the signed
  outgoing request via page.on("request", ...). The print line is the
  verification anchor that proves the SDK API surface works without
  needing an LLM.

Run:
    uv pip install "browser-use>=0.7,<1" "playwright>=1.59,<2"
    playwright install chromium

    # Mock mode (no key required):
    python examples/browser_use_demo.py

    # Real mode via OpenRouter (recommended — one key, all models):
    OPENROUTER_API_KEY=sk-or-... python examples/browser_use_demo.py
    # Optional: pick a model
    OPENROUTER_API_KEY=sk-or-... WBAUTH_MODEL=anthropic/claude-3.5-sonnet \\
      python examples/browser_use_demo.py

    # Real mode via direct OpenAI:
    OPENAI_API_KEY=sk-... python examples/browser_use_demo.py

    # Real mode via Browser Use hosted backend:
    BROWSER_USE_API_KEY=... python examples/browser_use_demo.py

Pitfalls:
- attach_signing(page, identity) MUST be called BEFORE page.goto / agent.run
  (Phase 2 Pitfall 6). page.route only intercepts requests started after
  the handler is registered.
- Browser Use exposes both `Browser` (high-level, used with `Agent`) and
  `BrowserSession` (lower-level handle); both expose `get_current_page()`
  to reach the underlying Playwright Page. We use BrowserSession in
  mock-mode because we don't need the Agent at all.

Per CONTEXT D-70: this demo does NOT depend on Cloudflare verifier
round-trip. Daily canary (Phase 1) covers full e2e Cloudflare verification.
"""
import asyncio
import os
from pathlib import Path

from wbauth import Identity, attach_signing

WORKER_URL = "https://wbauth.silov801.workers.dev/agents"
KEY_PATH = Path("~/.config/wbauth/key.pem").expanduser()


def _kid_or_placeholder() -> str:
    """Best-effort: derive the real kid from the on-disk key for the
    signature_agent_url. Falls back to a placeholder string on first run
    when the key has not been generated yet (load_or_generate will then
    materialize it on the second call below)."""
    try:
        return Identity.load_or_generate(
            KEY_PATH,
            signature_agent_url="https://example.invalid/placeholder",
        ).kid
    except Exception:
        return "PLACEHOLDER_KID"


async def mock_mode() -> None:
    """Open a Playwright page directly via Browser Use's BrowserSession;
    show the signed outgoing request. No LLM required."""
    # Imported inside the function so the script imports cleanly even when
    # browser-use is not installed (e.g. CI structural verification).
    from browser_use import BrowserProfile, BrowserSession

    profile = BrowserProfile(headless=True)
    session = BrowserSession(browser_profile=profile)
    await session.start()
    try:
        page = await session.get_current_page()
        identity = Identity.load_or_generate(
            KEY_PATH,
            signature_agent_url=(
                "https://wbauth.silov801.workers.dev/.well-known/"
                f"http-message-signatures-directory/{_kid_or_placeholder()}"
            ),
        )

        # Register signing BEFORE the first navigation (Pitfall 6).
        await attach_signing(page, identity)

        # The verification anchor: every outgoing request prints its signed
        # headers. Mock-mode "did something" without an LLM.
        page.on(
            "request",
            lambda req: print(
                f"[signed] {req.method} {req.url} "
                f"sig={(req.headers.get('signature') or '<none>')[:40]}..."
            ),
        )

        await page.goto(WORKER_URL)
        # Give Playwright a moment to flush request events.
        await asyncio.sleep(0.5)

        print(f"\n[demo] Identity kid: {identity.kid}")
        print(
            "[demo] Signed request fired against Worker. "
            "Inspect Worker logs for verifier pass/fail."
        )
    finally:
        await session.kill()


def _build_llm():
    """Pick the cheapest viable LLM client based on env keys.

    Priority: OPENROUTER_API_KEY (recommended — one key, many models)
    → OPENAI_API_KEY (direct) → BROWSER_USE_API_KEY (hosted).
    """
    if openrouter_key := os.getenv("OPENROUTER_API_KEY"):
        # Browser Use's ChatOpenAI accepts custom base_url — point at
        # OpenRouter and use a provider-prefixed model name.
        from browser_use.llm import ChatOpenAI

        model = os.getenv("WBAUTH_MODEL", "openai/gpt-4o-mini")
        print(f"[demo] LLM provider: OpenRouter (model={model})")
        return ChatOpenAI(
            model=model,
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1",
        )
    if os.getenv("OPENAI_API_KEY"):
        from browser_use.llm import ChatOpenAI

        model = os.getenv("WBAUTH_MODEL", "gpt-4o-mini")
        print(f"[demo] LLM provider: OpenAI (model={model})")
        return ChatOpenAI(model=model)
    # Browser Use hosted backend — uses BROWSER_USE_API_KEY automatically.
    from browser_use import ChatBrowserUse

    print("[demo] LLM provider: Browser Use hosted")
    return ChatBrowserUse()


async def real_mode() -> None:
    """Run a live Browser Use Agent. Requires an LLM key (OPENROUTER_API_KEY,
    OPENAI_API_KEY, or BROWSER_USE_API_KEY). The Agent navigates to a benign
    target; every browser request is signed via attach_signing()."""
    from browser_use import Agent, Browser

    browser = Browser()
    await browser.start()
    try:
        page = await browser.get_current_page()
        identity = Identity.load_or_generate(
            KEY_PATH,
            signature_agent_url=(
                "https://wbauth.silov801.workers.dev/.well-known/"
                f"http-message-signatures-directory/{_kid_or_placeholder()}"
            ),
        )
        # CRITICAL: register before agent.run() (Pitfall 6).
        await attach_signing(page, identity)

        agent = Agent(
            task="Open https://example.com and report the page title.",
            llm=_build_llm(),
            browser=browser,
        )
        result = await agent.run()
        print(f"[agent] result: {result}")
    finally:
        await browser.stop()


def main() -> None:
    if (
        os.getenv("OPENROUTER_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("BROWSER_USE_API_KEY")
    ):
        print("[demo] Real mode (LLM key detected)")
        asyncio.run(real_mode())
    else:
        print(
            "[demo] Mock mode (no LLM key — set OPENROUTER_API_KEY for real Agent)"
        )
        asyncio.run(mock_mode())


if __name__ == "__main__":
    main()
