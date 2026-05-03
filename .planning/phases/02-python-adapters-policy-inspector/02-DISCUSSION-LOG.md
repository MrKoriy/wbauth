# Phase 2: Python Adapters & Policy Inspector - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-04
**Phase:** 2-Python Adapters & Policy Inspector
**Areas discussed:** Browser Use spike timing, async/sync API surface, verdict philosophy
**Mode:** Carrying forward Phase 1 decisions (L-01..L-05); deciding only Phase 2 implementation choices

---

## Browser Use Spike Timing

### Q: Browser Use Playwright spike — взять или пропустить?

| Option | Description | Selected |
|--------|-------------|----------|
| Skip (Recommended) | Playwright `page.route()` confidence is HIGH from research; Browser Use exposes underlying Playwright Page; real verification in Phase 4 demos | ✓ |
| Spike now (1-hour test) | Install Browser Use locally, try attach_signing on real bot; safer but extra time cost | |

**User's choice:** Skip
**Rationale captured in CONTEXT.md D-13:** Defer real Browser Use integration to Phase 4 (`examples/browser_use_demo.py`). If actual gap surfaces there, fix in place; speculative pre-spike not worth the time on this schedule.

---

## Inspector API Surface — Async vs Sync

### Q: Делать sync обёртку для inspect(url)?

| Option | Description | Selected |
|--------|-------------|----------|
| Async-only (Recommended) | `await inspect(url)`. Honest API matching internal asyncio.gather. Sync users do `asyncio.run(inspect(url))` themselves | ✓ |
| Async + sync wrapper | `inspect(url)` (sync) + `inspect_async(url)` (async). More convenient for scripts but creates "which is canonical?" ambiguity | |

**User's choice:** Async-only
**Rationale captured in CONTEXT.md D-16:** Internal implementation does parallel asyncio.gather — exposing async natively is the honest API. No `inspect_sync` wrapper. CLI commands handle the asyncio.run() boilerplate per D-26 so shell users don't see it.

---

## Verdict Engine Philosophy

### Q: Как verdict engine интерпретирует граничные случаи?

| Option | Description | Selected |
|--------|-------------|----------|
| Strict (Recommended) | Ambiguity → restricted, not allowed. ai.txt restrictions count. signing-required without identity → restricted. Errs on caution; matches honest-identity philosophy | ✓ |
| Liberal | Only robots.txt blocks (forbidden). ai.txt = info in reasons. Agent decides | |

**User's choice:** Strict
**Rationale captured in CONTEXT.md D-18:** Verdict philosophy aligns with project's honest-identity positioning. Ambiguous policy signals → `restricted` (with reasons explaining why), not `allowed`. Only deterministic blocks (robots.txt Disallow for our path/UA, or unparseable robots.txt) → `forbidden`.

---

## Claude's Discretion (areas not requiring user sign-off)

The user delegated implementation-level decisions to me — these are documented in CONTEXT.md D-30..D-32 and are subject to planner/executor judgment:

- Internal module organization beyond named files in D-14/D-17
- Exception class hierarchy beyond `RobotsParseError`
- Test assertion style and fixture loaders

## Deferred Ideas

- `aiohttp` adapter (REQUIREMENTS.md ADAPT-AIOHTTP-01 — v1.x trigger: 5+ users ask)
- `undici` Dispatcher TS adapter (Phase 4 / v1.x)
- Configurable user-agent for robots.txt matching (Phase 2 hardcodes `wbauth/0.1`)
- MCP discovery in inspector (v2)
- A2A AgentCard discovery (v2)
- Receipts (v2)
- OpenTelemetry hook (v1.x trigger: Laminar/AgentOps user asks)
- Disk-backed cache (multi-process scenarios — v1.x)
- Configurable verdict policy (v2 if demand)
