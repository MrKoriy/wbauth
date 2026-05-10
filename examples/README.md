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
