# Phase 4: TypeScript SDK & Framework Integrations - Discussion Log

> **Audit trail only.** Decisions are captured in CONTEXT.md.

**Date:** 2026-05-04
**Phase:** 4-TypeScript SDK & Framework Integrations
**Areas discussed:** TS scope, DIST-07 timing, demo runnability

---

## TS SDK Scope (signer/adapters vs full inspect port)

| Option | Description | Selected |
|--------|-------------|----------|
| Signer + adapters only (Recommended) | TS exports sign, Identity, createSignedFetch, applyTo. No inspect() port | ✓ |
| Signer + adapters + full inspect() port | Duplicate Phase 2 in TS — robots/ai.txt/llms.txt parsers + verdict engine | |
| Signer + adapters + light inspect() (robots only) | Middle ground; ai.txt/llms.txt deferred | |

**Rationale CONTEXT.md D-58:** Distribution-critical surface is TS adapters for Browser Use/Stagehand ecosystem. inspect() port is bounded v1.x effort if demand materializes. Skip ai.txt/llms.txt parser duplication entirely.

---

## DIST-07 (Upstream PRs) Timing

| Option | Description | Selected |
|--------|-------------|----------|
| Move to Phase 5 (Recommended) | PRs need public GitHub repo + author identity + maintenance — D-08 still deferred | ✓ |
| Do in Phase 4 (original plan) | Could draft PRs locally and defer submission, OR resolve D-08 now | |
| Prepare PR drafts in Phase 4, submit in Phase 5 | Phase 4 writes PR text + example files; Phase 5 forks + push + open | |

**Rationale CONTEXT.md D-71:** Bundles all "go-public" actions in Phase 5 with DIST-08 (Cloudflare submission). Phase 4 produces examples/ files; Phase 5 publishes them.

---

## Demo Runnability

| Option | Description | Selected |
|--------|-------------|----------|
| Runnable + optional LLM (Recommended) | Real working scripts; with API key = real agent run; without = mock-mode showing signed request | ✓ |
| Doc-only examples | README inserts + pseudo-code; nothing runs | |
| Runnable demos without LLM (mock only) | Pre-determined actions; no LLM at all | |

**Rationale CONTEXT.md D-67/D-68:** Each example is a working script. With API key, full demo. Without, mock-mode (page.on("request") logging shows signed request bytes). Mocked demos still demonstrate the SDK API surface.

---

## Claude's Discretion

CONTEXT.md D-72..D-75 — internal TS module organization, vitest fixture loading, export style, example file headers.

## Deferred Ideas

- TS inspect() port (v1.x trigger: 5+ TS users)
- TS undici Dispatcher (v1.x)
- TS Node CLI binary (Phase 5 / v1.x)
- DIST-07 → Phase 5 (not deferred, scheduled)
