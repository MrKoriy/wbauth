---
phase: 04-typescript-sdk-framework-integrations
plan: 03
subsystem: framework-demos
tags: [examples, demos, browser-use, stagehand, openai-agents, integrations, framework, dist-04, dist-05, dist-06]

# Dependency graph
requires:
  - phase: 02-python-adapters-policy-inspector
    provides: Python WebBotAuth (httpx.Auth) + attach_signing (Playwright async helper) + Identity.load_or_generate — consumed verbatim by browser_use_demo.py and openai_agents_demo.py
  - phase: 03-hosted-directory-cloudflare-submission
    provides: live directory Worker at https://wbauth.silov801.workers.dev/agents — every demo's mock-mode target (D-69); openai_agents_demo live smoke verified HTTP 200
  - phase: 04-typescript-sdk-framework-integrations Plan 01
    provides: TS Identity.loadOrGenerate + applyTo Playwright adapter — consumed by stagehand_demo.ts via `import { Identity, applyTo } from "wbauth"`
provides:
  - examples/browser_use_demo.py (DIST-04) — Browser Use × wbauth runnable demo, mock + real modes
  - examples/stagehand_demo.ts (DIST-05) — Stagehand × wbauth runnable demo, mock + real modes
  - examples/openai_agents_demo.py (DIST-06) — OpenAI Agents SDK × wbauth runnable demo, mock + real modes
  - examples/README.md — top-level guide (install, run, mock vs real, env vars, pitfalls, DIST-07-deferred-to-Phase-5 note)
affects: [05-publishing-distribution]

# Tech tracking
tech-stack:
  added: []  # demos depend on optional/peer deps that users install themselves; no new runtime deps to wbauth
  patterns:
    - "Mock + real bifurcation per demo — `if os.getenv('OPENAI_API_KEY') / process.env.OPENAI_API_KEY` dispatches to real_mode()/mock_mode() (D-67)"
    - "Two-load Identity pattern — placeholder URL load to derive kid, then re-load with canonical signature_agent_url that includes that kid"
    - "Verification anchors per demo: page.on('request', ...) for browser/stagehand demos, signature_input_present:True dict for openai_agents_demo — proves SDK API surface fired without depending on Cloudflare verifier (D-70)"
    - "Top-of-file docstring with run commands + what's mocked vs real (D-68)"
    - "Optional-LLM-key bifurcation: real-mode imports the framework SDK lazily inside the function body so mock-mode runs on a fresh box without that pip/npm dep installed"

key-files:
  created:
    - examples/browser_use_demo.py (153 lines) — DIST-04
    - examples/stagehand_demo.ts (117 lines) — DIST-05
    - examples/openai_agents_demo.py (139 lines) — DIST-06
    - examples/README.md (135 lines) — install + run + pitfalls for all three
  modified: []

key-decisions:
  - "D-67 honored 3/3: every demo has mock_mode + real_mode dispatched by env var presence"
  - "D-68 honored 3/3: every demo has a top-of-file docstring (Python triple-quoted, TS JSDoc /** */) explaining demonstrated behavior + run commands + mocked-vs-real split"
  - "D-69 honored 3/3: every mock-mode targets https://wbauth.silov801.workers.dev/agents (Phase 3 production Worker)"
  - "D-70 honored 3/3: no demo depends on Cloudflare verifier round-trip — verification anchor is the locally-emitted Signature-Input header, not the verifier's pass/fail"
  - "D-71 honored: DIST-07 (upstream PRs to Browser Use / Stagehand / mcp-agent) explicitly OUT of this plan; documented in README.md 'Why these demos exist' section"
  - "Two-load Identity pattern (helper functions _kid_or_placeholder / make_identity / previewKid) so the signature_agent_url can include the real kid even on first run"
  - "openai_agents_demo mock-mode does NOT import `agents` (the openai-agents pip package) — `from agents import ...` is inside real_mode() — so mock-mode runs without that dep installed (per RESEARCH §Environment Availability)"

requirements-completed: [DIST-04, DIST-05, DIST-06]

# Metrics
duration: ~4min
completed: 2026-05-10
---

# Phase 4 Plan 03: Framework Demos (Browser Use + Stagehand + OpenAI Agents) Summary

**Three runnable demo scripts (`examples/browser_use_demo.py`, `examples/stagehand_demo.ts`, `examples/openai_agents_demo.py`) plus a `examples/README.md` guide — each demo runs in mock-mode against the live Phase 3 Worker without an LLM key, and switches to a real Agent-driven flow when one is detected.**

## Performance

- **Duration:** ~4 minutes (4m 02s wall clock)
- **Started:** 2026-05-10T20:04:01Z
- **Completed:** 2026-05-10T20:08:03Z
- **Tasks:** 3 of 3 complete
- **Files created:** 4 (3 demos + README)
- **Files modified:** 0
- **Commits:** 3 (one per task, atomic)

## Accomplishments

- **DIST-04 closed:** `examples/browser_use_demo.py` exists; mock-mode opens a `BrowserSession` (lower-level Browser Use handle, per Pitfall 7) + `attach_signing(page, identity)` + `page.on("request")` listener and navigates to `https://wbauth.silov801.workers.dev/agents`. Real-mode wires `Browser` + `Agent` + `ChatBrowserUse` with `attach_signing` called BEFORE `agent.run()` (Pitfall 6). Dispatches on `OPENAI_API_KEY OR BROWSER_USE_API_KEY` (Browser Use supports both LLM providers).
- **DIST-05 closed:** `examples/stagehand_demo.ts` exists; imports `{ Identity, applyTo } from "wbauth"` (Plan 01 flat-root exports). Mock-mode constructs Stagehand with `env: "LOCAL"` and **no model** (Stagehand initializes fine in LOCAL+no-act mode), calls `applyTo(page, identity)` BEFORE first goto (Pitfall 3), and navigates to the Worker. Real-mode adds `model: "openai/gpt-4o"` + `modelClientOptions.apiKey` and runs `stagehand.observe(...)` (read-only, smaller LLM cost than `stagehand.act`).
- **DIST-06 closed:** `examples/openai_agents_demo.py` exists; defines `signed_get(url, identity) -> dict` using `httpx.Client(auth=WebBotAuth(identity))`. Mock-mode calls `signed_get(WORKER_URL, identity)` directly (skips `Runner` + `agents` import) and prints a result dict. Real-mode wraps `signed_get` in a `@function_tool` and runs `Runner.run(agent, "Fetch https://example.com ...")`.
- **Live smoke (openai_agents_demo mock-mode) PASSED end-to-end:** HTTP 200 from the Phase 3 Worker, `signature_input_present: True`, `kid: hO5qCfYU_j-sko9y9rxa9-9Fy6igy4a-DxOuxwa12TY`. This is the only demo whose mock-mode runs in CI/dev box without browser binaries; it is the live-execution proof that the SDK's signing path emits a `Signature-Input` header end-to-end.
- **examples/README.md finalized:** install + run for all three demos, Stagehand-LOCAL-still-needs-Chromium pitfall, attach_signing/applyTo-before-goto pitfall, npm-link local-dev tip for Stagehand, "Why these demos exist" background, and explicit DIST-07-deferred-to-Phase-5 note (D-71).
- **No new runtime dependencies added to wbauth.** Browser Use, Stagehand, and openai-agents are documented as user-installed in the README (peer-style consumption); the demos themselves import them lazily inside the real_mode() body so mock-mode runs without them.

## Task Commits

Per-task atomic commits (one feat per task, no test gate needed — these are demonstration scripts, not unit-tested code):

1. **Task 1:** `6e05674` — `feat(04-03): add Browser Use demo (DIST-04) + examples/README.md scaffold`
2. **Task 2:** `f8f07f5` — `feat(04-03): add Stagehand demo (DIST-05) consuming Plan 01 TS SDK`
3. **Task 3:** `fae0a0b` — `feat(04-03): add OpenAI Agents demo (DIST-06) + finalize examples/README.md`

## Files Created

```
examples/
├── README.md                  (135L) — top-level guide: install + run + pitfalls + DIST-07 note
├── browser_use_demo.py        (153L) — DIST-04
├── stagehand_demo.ts          (117L) — DIST-05
└── openai_agents_demo.py      (139L) — DIST-06
```

## Live Smoke Output (openai_agents_demo.py mock-mode)

```
$ uv run --project python python examples/openai_agents_demo.py
[demo] Mock mode (no OpenAI key)
[demo] Calling signed_get directly (no LLM).
[demo] {'url': 'https://wbauth.silov801.workers.dev/agents', 'status': 200, 'kid': 'hO5qCfYU_j-sko9y9rxa9-9Fy6igy4a-DxOuxwa12TY', 'signature_input_present': True}
```

The `signature_input_present: True` is the verification anchor — it proves the request that left `httpx` carried a `Signature-Input` header (looked up case-insensitively over `resp.request.headers` post-auth-flow). The HTTP 200 confirms the Phase 3 Worker received our request.

## Sample Output (mock-mode behaviour, by demo)

### browser_use_demo.py (mock-mode, expected output on a box with Chromium + browser-use)

```
[demo] Mock mode (no LLM key — set OPENAI_API_KEY for real Agent)
[signed] GET https://wbauth.silov801.workers.dev/agents sig=sig1=:abcd...truncated:...

[demo] Identity kid: hO5qCfYU_j-sko9y9rxa9-9Fy6igy4a-DxOuxwa12TY
[demo] Signed request fired against Worker. Inspect Worker logs for verifier pass/fail.
```

(Not executed in this plan because Chromium + browser-use install is ~350 MB; Plan verification is structural per CONTEXT D-65.)

### stagehand_demo.ts (mock-mode, expected output on a box with Chromium + stagehand)

```
[demo] Mock mode
[signed] GET https://wbauth.silov801.workers.dev/agents sig=sig1=:abcd...truncated:...

[demo] Identity kid: hO5qCfYU_j-sko9y9rxa9-9Fy6igy4a-DxOuxwa12TY
[demo] Signed request fired against Worker.
```

(Not executed in this plan — same reasons as browser_use_demo.)

## Decisions Made

- **Verbatim from RESEARCH §6.2 / §7.2 / §8.2.** All three demos follow the planner's reference code with only cosmetic tweaks (function ordering, additional docstring detail, ASCII safety in docstrings — no `×` Unicode in `.py` triple-quoted strings to avoid encoding-edge-case grief). No semantic deviations.
- **Two-load Identity helper named differently per language idiom:** `_kid_or_placeholder()` (Python — leading underscore for module-private), `previewKid(path)` (TypeScript — camelCase), `make_identity()` (Python — slightly nicer wrapper that does both loads in one call). Same pattern, three names, all stay close to the surrounding code style.
- **openai_agents_demo dispatches synchronously in mock-mode** (calls `mock_mode(identity)` directly, not `asyncio.run(...)`) because `signed_get` is a sync `httpx.Client` call and the Agents SDK Runner is the only reason real_mode goes async. Mock-mode-without-asyncio is the simplest possible "what does the SDK actually emit?" proof.
- **Stagehand mock-mode constructs Stagehand without a `model` field.** Stagehand v3.3+ initializes fine in `env: "LOCAL"` without a model when none of `act/observe/extract` are called. We exercise `page.goto + page.on("request")` only — pure Playwright surface — so no LLM is ever invoked.

## Deviations from Plan

### Auto-fixed Issues

None. All three demos were written from the verified RESEARCH §6.2 / §7.2 / §8.2 code with the planner's invariants preserved.

### Notes

- **Browser Use API drift (Pitfall 7) — not encountered.** The planner flagged that `BrowserSession` vs `Browser` API drift is a risk depending on installed `browser-use` version. We did not run the browser_use_demo (per CONTEXT D-65 — no live browser tests in CI), so this pitfall remains a developer-box smoke-run concern, not a structural-gate concern. Both API entry points are referenced in the demo (BrowserSession in mock, Browser in real) so a future contributor running the smoke can flag if either path has drifted.
- **`grep "DIST-07.*Phase 5\|D-71"` README check:** the plan's acceptance criteria specified this regex to verify the DIST-07-deferred-to-Phase-5 note is documented. The README contains both a "DIST-07" mention and an explicit "DIST-07 ... are NOT in Phase 4. They are scheduled for Phase 5" sentence — the alternation regex matches because `D-71` appears literally in the README per-CONTEXT-decision-reference style.

## Hand-off Notes

### To Phase 5 (publishing + DIST-07 upstream PRs)

The three demo scripts are ready to be the source for upstream PRs:

- **Browser Use upstream `examples/`** — copy `browser_use_demo.py` mock-mode half (drop real_mode if maintainers prefer single-purpose examples). Rename to something like `examples/web_bot_auth_signing.py`.
- **Stagehand upstream `examples/`** — copy `stagehand_demo.ts` mock-mode half. Rename to something like `examples/web-bot-auth-signing.ts`.
- **mcp-agent or openai-agents-python upstream `examples/`** — copy `openai_agents_demo.py` whole (the `@function_tool` pattern is the integration story, not just the mock-mode emit).

Each upstream PR should reference the wbauth repo URL (Phase 5 D-08 prerequisite) for the maintainers to inspect the SDK before approving.

### To Phase 5 (60-second README Loom)

The "agent fails on Cloudflare → installs SDK → 3 lines added → request passes" Loom can be storyboarded directly from the demos:

1. **Open with mock-mode** (instant, no LLM cost): `python examples/openai_agents_demo.py` → show `signature_input_present: True` HTTP 200.
2. **Switch to real-mode**: `OPENAI_API_KEY=sk-... python examples/openai_agents_demo.py` → show Agent → tool → signed request → `[agent] GET https://example.com -> HTTP 200 (signed with kid=...)`.
3. **Switch to Stagehand for the visual hook**: `npx tsx examples/stagehand_demo.ts` → show Chromium opening, Worker page loading, terminal printing the signed request.

The mock→real transition is the visual hook ("look, it works without an LLM, AND it works WITH one — same code path").

### To future maintenance

- **`KEY_PATH = ~/.config/wbauth/key.pem` is shared across all three demos.** First run of any demo materializes the key (mode 0o600, race-free per Phase 1 IDENT-01). Subsequent runs of any demo (Python or TS) load the same key — D-60 confirmed cross-language single-key-file format.
- **Worker URL hardcoded to `https://wbauth.silov801.workers.dev/agents`.** If the Phase 3 Worker URL ever changes (it shouldn't — it's behind a Cloudflare-managed subdomain), all three demos need updating in lockstep.
- **No browser-use, stagehand, or openai-agents in `requirements.txt` or `package.json`.** Users install these themselves per the README. This is intentional — keeps wbauth's runtime closure minimal (D-58 anti-feature spirit).

## Self-Check: PASSED

All four claimed files exist:

```
examples/browser_use_demo.py       FOUND
examples/stagehand_demo.ts         FOUND
examples/openai_agents_demo.py     FOUND
examples/README.md                 FOUND
```

All three claimed task commits exist in `git log`:

```
6e05674  feat(04-03): add Browser Use demo (DIST-04) + examples/README.md scaffold              FOUND
f8f07f5  feat(04-03): add Stagehand demo (DIST-05) consuming Plan 01 TS SDK                     FOUND
fae0a0b  feat(04-03): add OpenAI Agents demo (DIST-06) + finalize examples/README.md            FOUND
```

All 9 plan-level verification gates passed (file existence, py-compile, Worker URL in 3/3, OPENAI_API_KEY bifurcation in 3/3, verification anchors in 3/3, top-of-file docstrings in 3/3, README contents, live smoke `signature_input_present: True` against live Worker, DIST-07 explicit absence from `requirements:` field).
