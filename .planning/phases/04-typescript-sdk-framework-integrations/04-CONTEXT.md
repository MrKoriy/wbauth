# Phase 4: TypeScript SDK & Framework Integrations - Context

**Gathered:** 2026-05-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 ships a feature-parity TypeScript SDK for the agent-side identity half: a `wbauth` npm package exporting `sign`, `Identity`, `createSignedFetch`, and `applyTo(page, identity)` Playwright helper, byte-equal to the Python SDK via shared `spec/test-vectors/`. Plus three runnable example scripts demonstrating the SDK against Browser Use (Python), Stagehand (TS), and Playwright + OpenAI Agents SDK (Python) — each with optional-LLM fallback so they work without an API key.

**SCOPE NARROWED — what's NOT in Phase 4:**
- **Policy inspector port (TS)** — TS SDK ships signer + adapters only. The `inspect()` function stays Python-only in v1; TS users wanting policy lookups call our Python CLI as subprocess or wait for v1.x port. (Per decision below.)
- **DIST-07 — upstream PRs to Browser Use/Stagehand/mcp-agent `examples/`** — moves to Phase 5. PRs need: a public GitHub repo (D-08 still deferred), an author identity for review correspondence, and capacity to maintain the PR through review. All three are Phase-5 hardening concerns; bundling with DIST-08 (Cloudflare submission) keeps "go-public" actions together.

Covers v1 requirements: ADAPT-04, ADAPT-05, DIST-04, DIST-05, DIST-06.
DIST-07 deferred to Phase 5.

</domain>

<decisions>
## Implementation Decisions

### Carrying Forward (Locked in Earlier Phases)

- **L-01 → L-15: All Phase 1+2+3 carry-forwards apply.** Most relevant for Phase 4:
  - Package name `wbauth` for npm (Phase 1 D-05; npm name verified available 2026-05-03)
  - Public TS API surface: `import { sign, Identity, createSignedFetch, applyTo } from "wbauth"` (D-06)
  - camelCase TS API; snake_case JSON wire format (D-09 derivation)
  - Adapter LOC budget ≤50 each (Phase 2 D-15 mirror)
  - TS SDK wraps `cloudflare/web-bot-auth` 0.1.3 (already a dep from Phase 1 cross-language test vectors) — do NOT re-implement RFC 9421 signing
  - Test vectors in `spec/test-vectors/` are the cross-language oracle; TS adapter tests assert byte-equal headers vs `01-basic-get/expected.json` etc.
  - Worker URL for live-Worker examples: `https://wbauth.silov801.workers.dev` (Phase 3 D-33)
  - Cloudflare research verifier as conformance oracle for any TS-side smoke tests

### Phase 4 Implementation Decisions

#### TS SDK Scope
- **D-58: TS SDK ships signer + adapters only — NO `inspect()` port.** Public surface: `sign`, `Identity` (with `loadOrGenerate`, `fromTestKey`, `kid` accessor, `exportJwks`, multi-key rotation), `createSignedFetch`, `applyTo` (Playwright). The Python `inspect()` policy half stays Python-only in v1. Reason: keeping Phase 4 focused on the distribution-critical surface (TS adapters for Browser Use/Stagehand ecosystem) ships v1 faster; TS-port of `inspect()` is a bounded v1.x effort if demand materializes. Documented anti-feature for v1 to prevent scope creep.
- **D-59: TS Identity API mirrors Python.** `Identity.loadOrGenerate(path, { signatureAgentUrl })` (camelCase per D-09 derivation). `Identity.fromTestKey(signatureAgentUrl)` for the IETF Appendix B.1.4 test key. `identity.kid`, `identity.exportJwks()`, `identity.rotate()` — same semantics as Phase 1 Python.
- **D-60: TS Identity persists keys in same on-disk JSON format Python uses.** Users can `wbauth keygen` (Python) → load in TS, or vice-versa. Single key file format, language-agnostic.

#### Adapters
- **D-61: `createSignedFetch(identity)` returns a `typeof fetch` wrapper.** Drop-in replacement: `const sf = createSignedFetch(identity); await sf("https://...")`. Wraps the global `fetch` (Node 20+ native). Each adapter file ≤50 LOC of glue per ADAPT-07.
- **D-62: `applyTo(page, identity)` registers `page.route("**/*", handler)`** mirroring Python `attach_signing(page, identity)`. Async (Playwright TS is async-first). Handler signs via `wbauth.sign()` and calls `route.continue_({ headers: ... })`.
- **D-63: No `undici` Dispatcher in v1** — adapter coverage is `fetch` + `Playwright`. Per REQUIREMENTS.md `ADAPT-UNDICI-01` deferred; trigger = Stagehand or Browser Use TS users specifically ask. Stagehand actually uses native fetch internally via Playwright's network — so this likely never lands.

#### Test Strategy
- **D-64: Vitest + same `spec/test-vectors/` JSON files Python pytest consumes.** Mechanism: `vitest.config.ts` already has path resolver for `spec/test-vectors/` from Phase 1. Cross-language conformance: TS adapter test asserts byte-equal headers vs `expected.json` for each vector. Same set of 5 byte-equal vectors covers TS adapters too.
- **D-65: NO live Playwright browser tests in CI.** Use `unittest.mock` equivalent in vitest (mock the `Page` and `Route` objects). Real browser tests run in `examples/` scripts (D-67), executed manually before release.
- **D-66: Identity round-trip test across languages.** Generate a key in Python (`wbauth keygen --output /tmp/k.pem --jwks-output /tmp/k.jwks`), load in TS via `Identity.loadOrGenerate("/tmp/k.pem")`, sign a vector, assert byte-equal vs Python signature for the same vector. This is the canonical "single key file, two SDKs" guarantee.

#### Examples (Runnable with Optional-LLM Fallback)
- **D-67: Three example scripts, all runnable.** Files:
  - `examples/browser_use_demo.py` — Python; uses Browser Use + `wbauth.adapters.attach_signing(page, identity)`. With `OPENAI_API_KEY` env var: real Browser Use task. Without: mock-mode that just opens `https://wbauth.silov801.workers.dev/agents` and shows the signed request via `page.on("request")` logging.
  - `examples/stagehand_demo.ts` — TypeScript; uses Stagehand + `wbauth/adapters.applyTo(page, identity)`. Same LLM fallback pattern.
  - `examples/openai_agents_demo.py` — Python; uses OpenAI Agents SDK with `httpx.Client(auth=WebBotAuth(identity))`. With `OPENAI_API_KEY`: agent runs real task. Without: stubbed agent loop that just emits one signed HTTP request via the SDK.
- **D-68: Each example has a top-of-file docstring explaining what it demonstrates + how to run + what's mocked vs real.** No PR-ready boilerplate yet (those are Phase 5 outputs); just clear, copyable scripts.
- **D-69: Examples target `https://wbauth.silov801.workers.dev/agents` (our own Worker) when in mock-mode.** Real-mode (with LLM) uses whatever URL the agent decides; examples pre-seed a benign target like `https://example.com`.
- **D-70: NO requirement that examples actually pass Cloudflare verification end-to-end.** They demonstrate the SDK API surface, not the full Cloudflare handshake (Phase 1's daily-cron canary handles that separately).

#### DIST-07 Movement
- **D-71: DIST-07 (upstream PRs to Browser Use, Stagehand, mcp-agent) moves from Phase 4 to Phase 5.** Three reasons: (1) PRs need a public GitHub repo URL — D-08 (org/account) still deferred. (2) PRs need an author identity that maintainers can correspond with — also D-08. (3) PRs need capacity to respond to review — that's Phase 5 hardening territory. Phase 4 produces the `examples/` files; Phase 5 forks the upstream repos and opens the PRs.

### Claude's Discretion
- D-72: Internal TypeScript module organization (`typescript/src/identity.ts`, `typescript/src/signer.ts`, `typescript/src/adapters/fetch.ts`, `typescript/src/adapters/playwright.ts`, etc.). Planner picks based on existing skeleton from Phase 1.
- D-73: Vitest fixture loading mechanism — extend existing `typescript/tests/` patterns from Phase 1 vector tests.
- D-74: Choice between exporting from `wbauth` root vs subpath `wbauth/adapters` — match Python's `from wbauth.adapters import WebBotAuth` ergonomics where reasonable; TS-idiomatic flat exports otherwise.
- D-75: Example file headers / preamble style.

</decisions>

<canonical_refs>
## Canonical References

### Project & Requirements
- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md` — Phase 4 reqs: ADAPT-04, ADAPT-05, DIST-04, DIST-05, DIST-06 (DIST-07 moved to Phase 5)
- `.planning/ROADMAP.md` — Phase 4 boundaries

### Prior Phases
- `.planning/phases/01-foundation-cryptographic-root/01-CONTEXT.md` — D-01..D-11 (npm workspaces, package name `wbauth`)
- `.planning/phases/01-foundation-cryptographic-root/01-04-SUMMARY.md` — TS test vector loading pattern (vitest config, path resolver, web-bot-auth 0.1.3 usage)
- `.planning/phases/02-python-adapters-policy-inspector/02-CONTEXT.md` — Python adapter design (mirror in TS)
- `.planning/phases/02-python-adapters-policy-inspector/02-01-SUMMARY.md` — Python adapter LOC numbers (47/43/45) — TS targets similar
- `.planning/phases/03-hosted-directory-cloudflare-submission/03-CONTEXT.md` — Worker URL for examples

### Existing Code (read these before extending)
- `typescript/package.json` — current TS workspace deps (web-bot-auth 0.1.3 already there)
- `typescript/src/index.ts` — current stub (Phase 4 fills out)
- `typescript/tsconfig.json`, `typescript/tsup.config.ts`, `typescript/vitest.config.ts` — build/test config
- `typescript/tests/vectors.test.ts` — existing vector tests via web-bot-auth 0.1.3 (Phase 1 Plan 04)
- `python/src/wbauth/identity.py` — reference for `Identity` shape to mirror
- `python/src/wbauth/signer.py` — reference for sign() shape
- `python/src/wbauth/adapters/httpx_auth.py` + `playwright.py` — reference for adapter shape
- `spec/test-vectors/` — 5 byte-equal vectors (input.json + expected.json each)

### External Specs (read directly when implementing)
- IETF RFC 9421 — HTTP Message Signatures
- IETF draft-meunier-web-bot-auth-architecture-05 — Web Bot Auth profile
- `cloudflare/web-bot-auth` 0.1.3 npm — README for `signerFromJWK`, `verifierFromJWK`, `signatureHeaders`

### Library Docs (verify versions current at implementation time via Context7)
- `cloudflare/web-bot-auth` 0.1.3 — TS RFC 9421 implementation
- Playwright TypeScript — `page.route()` async handler pattern
- Vitest — fixture loading + parametrized tests
- `tsup` — ESM+CJS bundling for npm publish (Phase 5)

### Framework Demo Targets
- Browser Use Python docs — agent + Playwright integration patterns
- Stagehand v3 docs — Playwright integration + LLM-assisted browsing
- OpenAI Agents SDK Python — custom `httpx.Client` injection pattern

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 1)
- `typescript/tests/vectors.test.ts` already loads vectors and uses `web-bot-auth` 0.1.3 — extend this pattern for adapter tests.
- `web-bot-auth` 0.1.3 npm dep already installed.
- `vitest.config.ts` already configured with workspace path resolver to `spec/test-vectors/`.
- `tsup.config.ts` configured for ESM+CJS dual build (Phase 1 deviation #4 fix).

### Reusable Assets (from Phase 2)
- Python adapter shapes (`WebBotAuth`, `attach_signing`) — direct mirror in TS with camelCase rename.
- Adapter test pattern (mock HTTP transport, assert headers byte-equal vs vector) — replicate in vitest.

### Established Patterns
- TDD cycle (RED → GREEN → REFACTOR), atomic commits per task.
- npm workspaces — `typescript/` workspace already in root `package.json`.
- macOS env: `bash scripts/post-sync.sh` + `chflags nohidden` after `uv sync` (only relevant for Python — TS workflow is `npm install` from root).

### Integration Points
- TS adapters consumed by Phase 4 demos (Stagehand TS especially).
- Python demos consume Phase 2 Python adapters (already shipped).
- Examples reference `https://wbauth.silov801.workers.dev` (Phase 3 production directory) for live mock-mode targets.

### What's NOT Yet in Code
- `typescript/src/identity.ts` (to be created — mirror Python)
- `typescript/src/signer.ts` (to be created — wraps web-bot-auth 0.1.3 with WBA defaults)
- `typescript/src/adapters/fetch.ts` (to be created)
- `typescript/src/adapters/playwright.ts` (to be created)
- `typescript/src/adapters/index.ts` (re-exports)
- `typescript/tests/` for identity/signer/adapter tests (extend pattern from vectors.test.ts)
- `examples/` directory at project root (currently empty or has Phase 3 ad-hoc snapshot script only)

</code_context>

<specifics>
## Specific Ideas

- **TS Identity surface code shape (illustrative, not normative):**
  ```ts
  import { Identity, sign, createSignedFetch } from "wbauth";
  const identity = await Identity.loadOrGenerate("./key.pem", {
    signatureAgentUrl: "https://wbauth.silov801.workers.dev/.well-known/http-message-signatures-directory/<your-kid>"
  });
  const sf = createSignedFetch(identity);
  const res = await sf("https://example.com/api/data");
  ```
- **Stagehand demo specifically should leverage Stagehand's Browserbase-managed Playwright** — the demo can either use Browserbase (requires API key, document) or local Playwright (works offline). Default: local Playwright; document Browserbase as optional production path.

</specifics>

<deferred>
## Deferred Ideas

- **TS `inspect()` port** — v1.x. Trigger: 5+ TS users ask for it OR a Stagehand integration explicitly needs policy inspection in-process (not via Python subprocess).
- **TS `undici` Dispatcher** — v1.x. Trigger: Stagehand or Browser Use TS users specifically.
- **TS CLI binary `wbauth` for Node** — Phase 5 or v1.x. Phase 4 ships SDK only, not Node CLI. Python CLI suffices for v1.
- **DIST-07 (upstream PRs)** — Phase 5 per D-71. NOT deferred — actively scheduled in the next phase.
- **TS-side `wbauth verify` CLI equivalent** — N/A in v1; Python CLI handles this.

</deferred>

---

*Phase: 4-TypeScript SDK & Framework Integrations*
*Context gathered: 2026-05-04*
