# Phase 1: Foundation & Cryptographic Root - Research

**Researched:** 2026-05-03
**Domain:** Ed25519 identity + RFC 9421 + Web Bot Auth signer; uv/pnpm monorepo; Cloudflare Workers + D1 Day-1 hosting
**Confidence:** HIGH for protocol/library APIs and Cloudflare endpoints (verified live); HIGH for monorepo tooling (vendor docs); MEDIUM for exact submission-flow timeline and RU-IP wrangler edge cases (not officially documented either way).

## Summary

Phase 1 has a deceptively wide blast radius for one phase: it must (a) confirm Cloudflare hosting works on Day 1 before any code is written, (b) erect a dual-language monorepo skeleton that survives 6+ months of dependency rot, (c) implement the cryptographic root (Ed25519 identity + RFC 9421 signer + Web Bot Auth profile) such that bytes match Cloudflare's reference verifier exactly, and (d) lock the cross-language test-vector contract that downstream phases depend on. There is no margin for redoing any of this; the rest of the project is built on top of these locked decisions.

The critical-path discovery from this research: **the existing libraries (`pyauth/http-message-signatures` 2.0.1 in Python, `web-bot-auth` 0.1.3 in TypeScript) already implement RFC 9421 with Ed25519 — we are integrating, not re-implementing.** The Python library exposes a `signer.sign(message, *, key_id, created, expires, nonce, tag, covered_component_ids)` API that natively supports the `tag="web-bot-auth"` parameter. The TypeScript library exposes `signatureHeaders(request, signer, {created, expires})` that returns `{Signature, Signature-Input}` headers. Both have been live-verified against real reference implementations.

**Primary recommendation:** Build `wbauth.identity.Identity` as a thin object that owns an Ed25519 keypair + signature-agent URL, and `wbauth.sign(NormalizedRequest, Identity) -> SignatureHeaders` as a pure function that delegates the RFC 9421 mechanics to `http-message-signatures` 2.0.1, supplying the Web Bot Auth defaults (`tag="web-bot-auth"`, `expires=created+60`, `covered_component_ids=("@authority", "signature-agent")`). Test vectors are paired `input.json`/`expected.json` files in `spec/test-vectors/`; both Python pytest and TypeScript vitest load the same files and assert byte-equality of the resulting `Signature-Input` and `Signature` headers. The Cloudflare debug check is performed against `https://crawltest.com/cdn-cgi/web-bot-auth` (returns 200 on success, 401 on key-unknown, 400 on malformed), with `https://http-message-signatures-example.research.cloudflare.com/debug` as a secondary sanity check.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Hosting & Billing Strategy:**
- **D-01: Zero-billing architecture chosen.** All hosted infrastructure runs on free tiers — no recurring credit-card charges. This optimizes for the 6+ months unmaintained period during army leave: nothing can break in billing because there is no billing.
- **D-02: Directory backend stack changed from original plan.** Architectural shift: directory backend is **TypeScript on Cloudflare Workers + D1** (NOT Python on FastAPI/Fly.io as originally written in PROJECT.md, REQUIREMENTS.md DIR-01, and SUMMARY.md). All references to FastAPI for the directory backend in research outputs are now superseded. Reason: zero-billing surface + Cloudflare D1 is managed SQLite with auto-backup. Implication: Python developer must delegate directory implementation to TypeScript-capable sub-agents with careful verification against test vectors.
- **D-03: No custom domain in v1.** Use `wbauth.workers.dev` (or similar Cloudflare-assigned subdomain) for the directory backend, and `<github-org>.github.io/wbauth` for docs. Custom domain registration deferred to post-army return.
- **D-04: Day-1 hosting protocol = Cloudflare-only.** Before any code is written: (1) sign up Cloudflare account, (2) deploy hello-world Worker, (3) provision and read/write to a D1 database instance. ~30 minutes total. If Cloudflare rejects the signup or the available payment card for any reason, escalate to user before proceeding (no automatic fallback to Fly.io/Railway).

**Project Naming:**
- **D-05: Package name is `wbauth`.** Verified available on PyPI and npm as of 2026-05-03.
- **D-06: Public import surface = `wbauth`.** Python: `from wbauth import sign, inspect, Identity`. TypeScript: `import { sign, inspect, Identity } from "wbauth"`.
- **D-07: PROJECT.md naming references are aliases, not blockers.** All earlier mentions of `agentpassport.dev` / `agentpassport` in PROJECT.md, REQUIREMENTS.md, ROADMAP.md, and research/* are working names that planner should treat as `wbauth` going forward. Update files in Phase 1 as part of repo scaffold.

**Repository Hosting:**
- **D-08: GitHub account/org choice deferred.** User will decide between personal account and new `wbauth` org at the moment of `git remote add` (planner: leave this as an open knob in scaffolding tasks; do not hardcode an org name in workflows or pyproject.toml).

### Claude's Discretion

User explicitly delegated these decisions to Claude (will review the proposal before commit):

- **D-09: Public API shape (Identity construction, signer surface, key file conventions).** Planner should propose a standard pattern based on research/STACK.md and ARCHITECTURE.md (Identity is a long-lived object constructed once at process start; key file default at `~/.config/wbauth/key.pem` with `0o600`; `Identity.load_or_generate(path, signature_agent_url=...)` as the primary entry point). Surface the proposal in the plan for explicit user sign-off before adapter work in Phase 2 begins.
- **D-10: Monorepo layout.** Apply industry-standard layout: `python/` (uv workspace member with `pyproject.toml`), `typescript/` (pnpm workspace member with `package.json`), `directory/` (TypeScript Cloudflare Worker), `spec/test-vectors/` (shared JSON test fixtures), `docs/` (Astro Starlight, deferred details to Phase 5), `.github/workflows/` (CI for python, typescript, cross-language conformance). Single repo, dual workspace roots (uv + pnpm).
- **D-11: Test vector format and initial coverage.** Apply the format described in research/ARCHITECTURE.md (paired `input.json` + `expected.json` files in `spec/test-vectors/`). Minimum 5 vectors covering: (a) basic GET with `@authority` + `signature-agent`, (b) POST with body + `content-digest`, (c) custom non-default expiry, (d) key with multiple URIs in JWKS, (e) edge case TBD (chosen during implementation — likely a Cloudflare-specific quirk). Add Cloudflare debug-endpoint round-trip as the 6th canonical "live" check.

### Deferred Ideas (OUT OF SCOPE)

- **Custom domain registration** — defer to post-army. Working name candidates if user wants to register later: `wbauth.dev`, `wbauth.io`, `wbauth.org`. Not registered now to keep zero-billing surface intact.
- **GitHub org `wbauth` vs personal account** — user defers decision to `git remote add` moment in Phase 1 implementation. Planner should leave this as a fill-in-when-applied decision, not hardcode any specific GitHub URL.
- **TypeScript-on-Workers vs Python-on-Fly.io for directory backend** — user chose TypeScript+Workers; Python+Fly.io path is rejected and should not be re-proposed without explicit re-discussion. The `directory/` workspace in monorepo is TypeScript exclusively.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| IDENT-01 | Ed25519 keygen via Python API + CLI; private key written 0o600; loading refuses files with wider permissions | Section 3 — `cryptography` 47.x `Ed25519PrivateKey.generate()` + `serialization.PrivateFormat.PKCS8` + `os.chmod(path, 0o600)` + POSIX mode check (Windows nuance documented) |
| IDENT-02 | Long-lived `Identity` object with keypair + agent metadata (signature-agent URI, expected user-agent string) | Section 3 — `Identity.load_or_generate(path, signature_agent_url=..., user_agent=...)`; held once at process start |
| IDENT-03 | `sign(NormalizedRequest, Identity) -> SignatureHeaders` producing valid RFC 9421 + Web Bot Auth headers (Ed25519, `tag="web-bot-auth"`, `expires=created+60s`) | Section 4 — `http-message-signatures` 2.0.1 `HTTPMessageSigner.sign(message, key_id=..., tag="web-bot-auth", expires=..., covered_component_ids=("@authority","signature-agent"))` |
| IDENT-04 | Generated signatures pass byte-equal verification against `spec/test-vectors/` golden files | Section 5 — paired `input.json`/`expected.json`, fixed `created` timestamp + nonce, deterministic Ed25519 means signature bytes are reproducible |
| IDENT-05 | Generated signatures pass Cloudflare's debug verifier endpoint in CI smoke tests | Section 6 — `crawltest.com/cdn-cgi/web-bot-auth` (primary, returns 200/401/400 status codes), publicly-reachable JWKS required |
| IDENT-06 | JWKS export with `kid = base64url(sha256(JWK))` per RFC 7638 | Section 3 — canonical JWK serialization (`{"crv":"Ed25519","kty":"OKP","x":"…"}` member-sorted) → SHA-256 → base64url-no-pad |
| IDENT-07 | Multi-key Identity holds active + retiring key with overlap window | Section 3 — `Identity` holds `KeyPair[]`; one `active` slot, optional `retiring` slot; JWKS export includes both; signing uses active only |
| IDENT-08 | Identity object's `__repr__` and `__str__` return REDACTED instead of leaking private key | Section 3 — `__repr__/__str__` return `"<Identity REDACTED kid=…>"`; `__reduce__` raises to refuse pickling |
| DIR-06 | Day-1 hosting confirmation (Cloudflare Workers + D1) | Section 1 — concrete wrangler commands, free tier limits, fallback decision tree |
</phase_requirements>

## Architectural Responsibility Map

Phase 1 is a foundation phase with a narrow tier surface: nearly all functionality lives in the SDK (in-process library), with one external service (Cloudflare Workers + D1) used only for the Day-1 hosting smoke test, not for any signing logic.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Ed25519 keypair generation, persistence, loading | SDK (in-process Python library) | — | Keys are local to the agent's process; no cloud key management in v1 (KMS deferred to v2 per REQUIREMENTS.md). |
| RFC 9421 signing of HTTP requests | SDK (in-process Python library) | — | Pure function; no I/O; runs wherever the agent runs. |
| JWKS export (key directory) | SDK output | Hosted (Phase 3 directory) | Phase 1 produces JWKS; Phase 3 serves it. In Phase 1, JWKS is a string the user can paste into a static file. |
| Test-vector cross-language oracle | Filesystem (`spec/test-vectors/`) | CI runners (Python + TypeScript) | Vectors are JSON files; both runtimes load identical bytes. |
| Day-1 hosting smoke test | External service (Cloudflare Workers + D1) | — | Validates the account, the wrangler CLI flow, and D1 binding work end-to-end. Not a permanent component — code is throwaway. |
| Monorepo build / test orchestration | Local + CI (GitHub Actions) | — | uv (Python) + pnpm (TypeScript) workspaces; CI matrix runs both. |
| Cloudflare debug verifier integration | External service (`crawltest.com/cdn-cgi/web-bot-auth`) | CI runner | One-shot HTTP check from a CI job; the SDK constructs the signed request, the CI run posts it and asserts a 200 response. |

**Tier discipline:** the SDK never depends on the directory backend at signing time. Signature-Agent is a string the SDK embeds; verifiers (Cloudflare) fetch the JWKS — the SDK does not. Phase 1 deliverables are 100% client-side except the Day-1 hosting test (which produces no permanent code shipped with the SDK).

## Standard Stack

### Core (versions verified against PyPI/npm 2026-05-03)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `cryptography` (PyCA) | 47.0.0 | Ed25519 keygen, sign, JWK serialization | Canonical Python crypto. Ships wheels for all major platforms — no C compiler needed. PyCA-maintained. **STACK.md said 46.x; current is 47.0.0 — minor freshness gap, planner can accept either.** [VERIFIED: pypi.org/pypi/cryptography/json] |
| `http-message-signatures` (pyauth) | 2.0.1 | RFC 9421 implementation | Native `tag` + `expires` + `covered_component_ids` parameters in `HTTPMessageSigner.sign()` — directly maps to Web Bot Auth profile needs. Apache 2.0. Same maintainer as `requests-http-signature`. [VERIFIED: pypi.org/pypi/http-message-signatures/json — version 2.0.1, requires_python>=3.10] |
| `httpx` | 0.28.1 | Async HTTP client; used as Request type by signer | First-class custom `Auth` subclass pattern is Phase 2's adapter target; for Phase 1 it's the request shape we sign. [VERIFIED: pypi.org/pypi/httpx/json] |
| `web-bot-auth` (Cloudflare) | 0.1.3 (npm; published 2026-03-09) | TypeScript Web Bot Auth signer | Cloudflare-published reference implementation. Exports `signatureHeaders` + `signerFromJWK`. Will be used by Phase 4 TS SDK; in Phase 1 it's only needed for the cross-language test-vector verifier (we run it once to confirm both libs produce identical bytes against the same input). [VERIFIED: registry.npmjs.org/web-bot-auth, deps: `http-message-sig@0.2.0` + `jsonwebkey-thumbprint@0.1.0`] |
| `wrangler` (Cloudflare CLI) | 4.87.0 | Workers + D1 deployment + local dev | Required for Day-1 hosting test. Per-project local install (`npm i -D wrangler`). [VERIFIED: registry.npmjs.org/wrangler] |
| `uv` (Astral) | 0.11.8 | Python project + dep manager + workspace | Lockfile-driven. Native `[tool.uv.workspace]` support. [VERIFIED: pypi.org/pypi/uv/json] |
| `pnpm` | 10.33.2 | Node package manager + workspace | `pnpm-workspace.yaml` with `packages:` glob list. [VERIFIED: registry.npmjs.org/pnpm] |
| `vitest` | 4.1.5 | TypeScript unit tests | Fast, native ESM, zero config for TS. [VERIFIED: registry.npmjs.org/vitest] |
| `typescript` | 6.0.3 | TypeScript compiler | [VERIFIED: registry.npmjs.org/typescript] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | latest | Python test runner | All test vectors loaded via parametrized fixtures. |
| `pytest-anyio` | 4.x | Async test mode | Use `anyio` mode (NOT `asyncio` plugin), per FastAPI's pattern. |
| `ruff` | latest | Python lint + format | One-tool replacement for flake8/black/isort. |
| `pyright` | latest | Python type-check | Faster than mypy; matches what most agent-framework devs run via VS Code. |
| `biome` | latest | TS lint + format | One-tool replacement for ESLint + Prettier. |
| `tsup` | 8.x | TS build → ESM + CJS + .d.ts | Single-command bundle; avoids hand-written tsconfig matrix. |
| `oschmod` (optional) | latest | Cross-platform chmod 0o600 | Use ONLY if Phase 1 must support Windows; on POSIX, stdlib `os.chmod` + `os.stat` is sufficient. **Recommended approach: detect platform via `sys.platform`, on Windows skip the permission check with a documented warning.** [CITED: PyPI oschmod] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `cryptography` Ed25519 | PyNaCl (libsodium) | PyNaCl is 10-20x faster but you sign one HTTP request — no perf bottleneck. `cryptography` is a transitive dep of nearly everything Python; PyNaCl is an extra C-extension build. |
| `cryptography` Ed25519 | stdlib pure-Python `pure25519` | Slower, less audited. Don't. |
| `http-message-signatures` | Roll our own RFC 9421 | The spec's signature-base canonicalization, derived components, and Structured Field encoding are subtle. 2.0.1 is mature and used by `requests-http-signature` (same author). Don't reinvent. |
| `http-message-signatures` Python | Use `web-bot-auth` npm via subprocess | Adds Node-as-runtime dependency to Python users. Reject. |
| Cloudflare Workers + D1 | Fly.io + SQLite-on-volume | Locked to Workers+D1 by D-02 (zero-billing). Fly.io requires a Stripe-processed signup; CF Workers is free-by-default. |

**Installation:**

```bash
# Python SDK workspace member
uv add cryptography>=47 \
       http-message-signatures>=2.0.1 \
       httpx>=0.28
uv add --dev pytest pytest-anyio ruff pyright

# TypeScript SDK workspace member (Phase 1 — only for vector cross-check)
pnpm add web-bot-auth
pnpm add -D vitest typescript tsup biome @types/node

# Day-1 hosting test (TypeScript Worker)
pnpm add -D wrangler
```

**Version verification** performed 2026-05-03 against npm registry and PyPI JSON API. The versions table above reflects what `npm view <pkg> version` and `https://pypi.org/pypi/<pkg>/json` return on this date. Lock the upper bound on Python SDK (`cryptography>=47,<48`, `http-message-signatures>=2.0.1,<3`) per PITFALLS.md Pitfall 11 (dep rot during army leave).

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────────────────────────────────┐
                    │  Developer machine / CI runner               │
                    │                                              │
                    │  ┌──────────────────────────────────────┐   │
                    │  │  Phase 1 SDK: wbauth (Python)        │   │
                    │  │                                      │   │
                    │  │  Identity ─owns→ Ed25519 keypair     │   │
                    │  │     │           + signature_agent_url│   │
                    │  │     │           + user_agent         │   │
                    │  │     │                                │   │
                    │  │     ▼                                │   │
                    │  │  sign(NormalizedRequest, Identity)   │   │
                    │  │     │                                │   │
                    │  │     ├─ delegates to ─→ http_message_ │   │
                    │  │     │                  signatures    │   │
                    │  │     │                  HTTPMessage   │   │
                    │  │     │                  Signer.sign() │   │
                    │  │     │                                │   │
                    │  │     ▼                                │   │
                    │  │  SignatureHeaders {                  │   │
                    │  │    Signature, Signature-Input,       │   │
                    │  │    Signature-Agent }                 │   │
                    │  └──────────────────┬───────────────────┘   │
                    │                     │                        │
                    │                     │ produces headers       │
                    │                     ▼                        │
                    │  ┌──────────────────────────────────────┐   │
                    │  │  Test layer:                          │   │
                    │  │  pytest + vitest both load            │   │
                    │  │  spec/test-vectors/<name>/input.json  │   │
                    │  │  → produce headers → assert byte-eq   │   │
                    │  │  to expected.json                     │   │
                    │  └──────────────────┬───────────────────┘   │
                    └─────────────────────┼────────────────────────┘
                                          │
                                          │ HTTPS  (CI smoke test)
                                          ▼
                          ┌────────────────────────────────────┐
                          │  Cloudflare debug verifier          │
                          │  https://crawltest.com/cdn-cgi/     │
                          │     web-bot-auth                    │
                          │  Returns 200 (ok) / 401 (key        │
                          │  unknown) / 400 (malformed)         │
                          └────────────────────────────────────┘

                    ┌─────────────────────────────────────────────┐
                    │  Day-1 Hosting Test (separate, throwaway)   │
                    │  Cloudflare Workers + D1                    │
                    │  (validates account + wrangler + D1 work)   │
                    └─────────────────────────────────────────────┘
```

### Recommended Project Structure

```
wbauth/                                # Repo root
├── README.md
├── LICENSE                            # Apache 2.0
├── .github/
│   └── workflows/
│       ├── python.yml                 # uv sync + pytest + ruff + pyright
│       ├── typescript.yml             # pnpm install + vitest + biome + tsc
│       ├── conformance.yml            # cross-language: both runtimes against spec/test-vectors/
│       └── cloudflare-debug.yml       # smoke test: sign + POST to crawltest.com
├── pyproject.toml                     # uv workspace root: [tool.uv.workspace] members=["python"]
├── uv.lock                            # committed
├── pnpm-workspace.yaml                # packages: [typescript, directory]
├── package.json                       # workspace root metadata only
├── pnpm-lock.yaml                     # committed
├── spec/
│   └── test-vectors/
│       ├── README.md                  # vector format documentation
│       ├── 01-basic-get/
│       │   ├── input.json
│       │   └── expected.json
│       ├── 02-post-with-content-digest/
│       │   ├── input.json
│       │   └── expected.json
│       ├── 03-custom-expiry/
│       │   ├── input.json
│       │   └── expected.json
│       ├── 04-multi-uri-jwks/
│       │   ├── input.json
│       │   └── expected.json
│       └── 05-cloudflare-quirk/       # TBD edge case
│           ├── input.json
│           └── expected.json
├── python/                            # uv workspace member
│   ├── pyproject.toml                 # name="wbauth", project metadata
│   ├── src/
│   │   └── wbauth/
│   │       ├── __init__.py            # re-exports: Identity, sign, SignatureHeaders
│   │       ├── identity.py            # Identity class, KeyPair, JWKS export
│   │       ├── signer.py              # sign() pure function
│   │       ├── normalized_request.py  # NormalizedRequest dataclass
│   │       └── _redaction.py          # __repr__/__str__ helpers
│   ├── tests/
│   │   ├── conftest.py                # fixture: load_vector(name)
│   │   ├── test_identity.py           # IDENT-01, 02, 06, 07, 08
│   │   ├── test_signer.py             # IDENT-03 against test vectors
│   │   └── test_vectors.py            # IDENT-04 byte-equal assertion
│   └── README.md                      # Python-specific quickstart
├── typescript/                        # pnpm workspace member
│   ├── package.json                   # name="wbauth", main/module/types
│   ├── src/
│   │   └── index.ts                   # Phase 1 stub: re-export web-bot-auth wrappers
│   ├── tests/
│   │   ├── vectors.test.ts            # cross-language: load same JSON, assert byte-eq
│   │   └── helpers.ts
│   ├── tsconfig.json
│   └── vitest.config.ts
├── directory/                         # pnpm workspace member (Phase 3, but scaffold here)
│   ├── package.json
│   ├── src/index.ts                   # Day-1: returns "hello" + reads/writes one D1 row
│   ├── wrangler.jsonc                 # binds D1
│   ├── schema.sql                     # one CREATE TABLE
│   └── README.md
├── docs/                              # Phase 5 — empty placeholder for now
└── strategic_memo_ru.md               # existing
```

### Pattern 1: Pure-Function Signer + Long-Lived Identity

**What:** `sign(request, identity)` is a pure function with no I/O. `Identity` is constructed once at process start and held for the lifetime of the agent.

**When to use:** Always for this project. Both Stripe and AWS SDKs follow this pattern; it makes the signer trivially unit-testable and keeps the private-key surface to a single object.

**Example:**

```python
# Source: synthesized from research/ARCHITECTURE.md Pattern 1 + http-message-signatures 2.0.1 sign() API
# (verified by reading https://raw.githubusercontent.com/pyauth/http-message-signatures/master/http_message_signatures/signatures.py)

from dataclasses import dataclass
from typing import Mapping
import datetime

@dataclass(frozen=True)
class NormalizedRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None = None

@dataclass(frozen=True)
class SignatureHeaders:
    signature: str
    signature_input: str
    signature_agent: str

def sign(
    request: NormalizedRequest,
    identity: "Identity",
    *,
    created: datetime.datetime | None = None,
    expires_after_seconds: int = 60,
    nonce: str | None = None,
) -> SignatureHeaders:
    """Pure signer. No I/O. Web Bot Auth profile defaults."""
    # delegates to http-message-signatures' HTTPMessageSigner.sign() with
    # tag="web-bot-auth", expires=created+expires_after_seconds,
    # covered_component_ids=("@authority", "signature-agent")
    ...
```

### Pattern 2: Identity as Long-Lived Object with Single-Source Private Key

**What:** `Identity.load_or_generate(path, signature_agent_url=...)` is the only constructor. The private key is held in one Python object; nothing else touches PEM bytes.

**Example:**

```python
# Source: research/ARCHITECTURE.md Pattern 2 + decisions D-09

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey
)
from cryptography.hazmat.primitives import serialization
import os, hashlib, base64, json
from pathlib import Path

class Identity:
    def __init__(
        self,
        private_key: Ed25519PrivateKey,
        signature_agent_url: str,
        user_agent: str | None = None,
    ):
        self._private_key = private_key  # PRIVATE — never logged
        self.signature_agent_url = signature_agent_url
        self.user_agent = user_agent
        # Compute kid from canonical JWK (RFC 7638)
        self.kid = _compute_kid(private_key.public_key())

    def __repr__(self) -> str:
        return f"<Identity REDACTED kid={self.kid!r}>"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("Identity is not pickleable (would leak private key)")

    @classmethod
    def load_or_generate(
        cls,
        path: str | Path,
        *,
        signature_agent_url: str,
        user_agent: str | None = None,
    ) -> "Identity":
        path = Path(path).expanduser()
        if path.exists():
            return cls._load(path, signature_agent_url, user_agent)
        return cls._generate(path, signature_agent_url, user_agent)

    @classmethod
    def _load(cls, path, sig_agent_url, ua):
        # Verify permissions before reading any bytes
        st = os.stat(path)
        # POSIX-only check; on Windows this is informational
        import sys
        if sys.platform != "win32":
            mode = st.st_mode & 0o777
            if mode & 0o077:  # any group or other bits set
                raise PermissionError(
                    f"Key file {path} has mode {oct(mode)}; expected 0o600. "
                    f"Fix with: chmod 600 {path}"
                )
        pem = path.read_bytes()
        key = serialization.load_pem_private_key(pem, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise TypeError(f"Expected Ed25519, got {type(key).__name__}")
        return cls(key, sig_agent_url, ua)

    @classmethod
    def _generate(cls, path, sig_agent_url, ua):
        key = Ed25519PrivateKey.generate()
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic-write with restrictive mode from the start
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, pem)
        finally:
            os.close(fd)
        return cls(key, sig_agent_url, ua)

    def export_jwks(self, *, include_retiring: bool = True) -> dict:
        """RFC 7638-compliant JWKS export."""
        keys = [self._public_jwk(self._private_key.public_key(), self.kid)]
        # If a retiring key exists (IDENT-07), append it here
        return {"keys": keys}
```

### Pattern 3: Test Vectors as Cross-Language Oracle

**What:** Paired `input.json` + `expected.json` files in `spec/test-vectors/<name>/`. Both Python and TypeScript runtimes load the same JSON files and assert byte-equality of the produced `Signature-Input` and `Signature` headers.

**Why this works for asymmetric crypto:** Ed25519 is **deterministic** — given the same private key + message, the signature bytes are identical every time. So a fixed input (with fixed `created` timestamp + nonce + private key) produces a fixed expected output. No "the signature will look like X" hand-waving needed.

### Anti-Patterns to Avoid

- **Hand-rolling RFC 9421:** the signature-base canonicalization, derived components, and Structured Field encoding are subtle. Use `http-message-signatures` 2.0.1.
- **Logging the `Identity` object or putting it in an exception message:** `__repr__` returns REDACTED specifically because someone WILL `logger.debug(f"signing with {identity!r}")`. (PITFALLS.md Pitfall 4.)
- **Auto-rotating keys silently:** the directory record points at a specific `kid`. Rotation must be a deliberate user act (`identity.rotate()`). (research/ARCHITECTURE.md Anti-Pattern 4.)
- **Using `expires=created+30`:** too short — network latency between signing and Cloudflare seeing the request can eat 1-3 seconds. Default is `expires=created+60`. (PITFALLS.md Pitfall 3.)
- **Sending `Signature-Agent` without quotes or with `http://`:** Cloudflare rejects silently. Helper must enforce both. (PITFALLS.md Pitfall 1.)
- **Using `urllib.robotparser` for Phase 2's robots.txt parsing:** known edge-case bugs. Use `protego`. (Out of Phase 1 scope but listed here so planner doesn't accidentally schedule it.)
- **Hard-coding GitHub org in workflows:** D-08 — leave as a fill-in-when-applied placeholder.
- **Pickling `Identity`:** `__reduce__` raises explicitly. If a user wants to serialize, they export the JWKS public half + reload from the keyfile.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| RFC 9421 signature base canonicalization | Custom string concatenator | `http-message-signatures` 2.0.1 (Python), `web-bot-auth` 0.1.3 (TS) | Spec is subtle: Structured Field encoding, derived component resolution, multi-line component values. 2.0.1 is mature; we'd ship bugs. |
| Ed25519 keygen / sign | `pure25519` Python | `cryptography` (PyCA) Ed25519 | PyCA wheels ship for all platforms. Pure-Python Ed25519 is slower and less audited. |
| Structured Field (RFC 8941) parsing | String split / regex | `http_sfv` (transitively included via `http-message-signatures`) | The library's own dependency. |
| JWK Thumbprint (RFC 7638) | Custom canonicalization | Library helpers OR a 10-line function with `json.dumps(..., sort_keys=True, separators=(",", ":"))` then `hashlib.sha256` then base64url-no-pad | If you do build it manually (10 lines), test against the **publicly-known IETF test vectors** in RFC 7638 §3.1 — there is one canonical Ed25519 example: `kid="poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U"` is the thumbprint of the RFC 9421 Appendix B.1.4 test key, confirmed by Cloudflare's research server. Verifies everywhere or breaks everywhere. |
| Cloudflare account / D1 setup | Custom REST calls | `wrangler` 4.87.0 CLI | `wrangler login`, `wrangler d1 create`, `wrangler deploy` — official tool, handles all auth flows. |
| Python project + dep management | pip + setup.py + venv + pip-tools | `uv` 0.11.8 | Lockfile, ~10x faster, native workspace support. |
| Cross-platform 0o600 enforcement | Manual `if windows: ... else: ...` | `oschmod` PyPI package OR documented Windows-skip with `sys.platform` check | Windows has no POSIX modes; oschmod maps to ACLs. For v1, recommend the simpler `sys.platform == "win32"` skip-with-warning approach since the SDK's primary users run Linux/macOS. |

**Key insight:** The Phase 1 SDK is essentially a 200-300 LOC Python wrapper that composes existing libraries with Web Bot Auth-specific defaults baked in. The complexity lives in test vectors and CI gates, not in code we write.

## Runtime State Inventory

> Phase 1 is greenfield — no rename or migration. Section omitted by spec.

## Common Pitfalls

### Pitfall 1: Signature-Agent header malformed (missing quotes, http://, or not in component list)

**What goes wrong:** Cloudflare rejects the request silently with no useful error. Looks like a Cloudflare bug; is an SDK bug.

**Why it happens:** `Signature-Agent` is a Structured Field (RFC 8941) — value MUST be enclosed in double quotes. URI MUST be `https://`. The header name `signature-agent` MUST appear in the `covered_component_ids` list.

**How to avoid:** Single helper `_set_signature_agent(url)` that validates `https://`, wraps in `"..."`, and forces `signature-agent` into `covered_component_ids`. Test against `https://crawltest.com/cdn-cgi/web-bot-auth` in CI.

**Warning signs:** README example showing `Signature-Agent: https://...` (no quotes). Local self-loopback verifier passes but Cloudflare rejects.

**Citation:** PITFALLS.md Pitfall 1; Cloudflare Web Bot Auth docs.

### Pitfall 2: Wrong derived components (Cloudflare doesn't accept everything in RFC 9421)

**What goes wrong:** SDK signs `@query-param` or `@status` thinking it's spec-compliant. Cloudflare rejects.

**Why it happens:** Cloudflare's verifier rejects `@query-param`, `@status`, and the parameters `sf`, `bs`, `key`, `req`, `name`. Recommended: `@authority` + components with ASCII-only values. (Verified via Cloudflare docs WebFetch 2026-05-03.)

**How to avoid:** Ship a "Cloudflare-safe profile" as the only profile in v1. Default `covered_component_ids = ("@authority", "signature-agent")`. Optional `content-digest` for POSTs. Document explicitly: "Do NOT add `@query-param` or `@status`."

**Warning signs:** Anyone proposing "let's support all RFC 9421 components."

**Citation:** PITFALLS.md Pitfall 2; Cloudflare bots reference.

### Pitfall 3: Clock skew + too-short expires window

**What goes wrong:** Signatures verify in dev (NTP-synced), then fail in prod intermittently.

**Why it happens:** `created` and `expires` are signed; verifier rejects if current time > `expires`. Network latency + proxy buffering eat 1-3 seconds. `http-message-signatures` 2.0.1's verifier defaults `max_clock_skew=5s` (verified by reading source).

**How to avoid:** Default `expires = created + 60`. Document: "If your machine is more than 5 seconds out of NTP sync, signing works locally but verification fails intermittently."

**Citation:** PITFALLS.md Pitfall 3; verified `max_clock_skew = datetime.timedelta(seconds=5)` in `http_message_signatures/signatures.py` `HTTPMessageVerifier`.

### Pitfall 4: Private Ed25519 key accidentally logged or committed

**What goes wrong:** `__repr__` of key object prints raw bytes; key ends up in CloudWatch / Sentry / GitHub.

**Why it happens:** Default `__repr__` of objects holding bytes shows them. `pickle.dumps(client)` to debug serializes the private key. Test fixtures with real keys committed to repos.

**How to avoid:**
1. `Identity.__repr__` and `__str__` return `"<Identity REDACTED kid=...>"`.
2. `Identity.__reduce__` raises `TypeError` to refuse pickling.
3. SDK never logs full request objects — provide `redacted_dict(request)` helper.
4. SDK writes keyfiles via `os.open(path, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)` — NOT `path.write_bytes()` then `chmod` (race window leaves the file world-readable for one syscall).
5. Refuse to load keyfiles with mode wider than `0o600` on POSIX. Print remediation: `chmod 600 <path>`.
6. Use the **publicly-known RFC 9421 Appendix B.1.4 Ed25519 test key** for all test vectors: `d="n4Ni-HpISpVObnQMW0wOhCKROaIKqKtW_2ZYb2p9KcU"`, `x="JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bs"`. Never a real key in the repo.

**Citation:** PITFALLS.md Pitfall 4; Cloudflare's research server confirms this key produces `kid=poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U` (verified live by GET to `https://http-message-signatures-example.research.cloudflare.com/.well-known/http-message-signatures-directory` 2026-05-03).

### Pitfall 5: `http-message-signatures` verifier requires `max_clock_skew` of 5 seconds

**What goes wrong:** Test vectors that bake in a `created` timestamp from "the past" (e.g., the day the vector was authored) cause `pyhms.verifier.verify(message)` to raise `InvalidSignature: Signature "expires" parameter is set to a time in the past`.

**Why it happens:** Verified by reading `http_message_signatures/signatures.py`: `validate_created_and_expires` checks `expires > (now - max_clock_skew)`. If the test vector's `expires` is older than 5 seconds before `now`, verification fails.

**How to avoid:** For test vectors, do NOT use the verifier to round-trip — assert on the produced `Signature-Input` / `Signature` strings directly (byte-equality with `expected.json`). Use the verifier only for live tests against the Cloudflare debug endpoint or as a self-loopback in unit tests where `created=now`.

### Pitfall 6: The `tag` parameter is sent literally; check spelling

**What goes wrong:** SDK sends `tag="webbotauth"` or `tag="web_bot_auth"` instead of `tag="web-bot-auth"`. Cloudflare rejects.

**Why it happens:** Web Bot Auth profile mandates the literal string `web-bot-auth`. Easy to typo.

**How to avoid:** Hard-code as a module constant `WEB_BOT_AUTH_TAG = "web-bot-auth"`. Reference everywhere via the constant.

### Pitfall 7: Cloudflare debug endpoint requires JWKS to be publicly reachable

**What goes wrong:** During Phase 1 local dev (no public hosting yet), the Cloudflare debug endpoint at `crawltest.com/cdn-cgi/web-bot-auth` cannot fetch the JWKS from `Signature-Agent` URL → returns 401 (key unknown), not 200.

**Why it happens:** The verifier follows the `Signature-Agent` URL and fetches `/.well-known/http-message-signatures-directory`. If the URL is unreachable (localhost, internal IP, 404), no key to verify with. (Verified by docs: 401 = "Message formatted correctly but key unknown.")

**How to avoid in Phase 1 (no domain yet):**
- **Option A (recommended):** Use `https://http-message-signatures-example.research.cloudflare.com/` as the `signature-agent` URL — it serves the RFC 9421 Appendix B.1.4 test key publicly. Combined with using the same test key as the SDK's signing key, the verifier will look up that URL, find the test public key, and verify our signature. Verified live: GETting that `/.well-known/http-message-signatures-directory` returned `{"keys":[{"kid":"poqkLGiymh_W...","kty":"OKP","crv":"Ed25519","x":"JrQLj5P..."}],"purpose":"rag"}`.
- **Option B (Day-3+, after hosting test):** Once the Day-1 hosting test confirms `<name>.workers.dev` works, deploy a one-route Worker that serves the JWKS at `/.well-known/http-message-signatures-directory` and use that URL as `signature-agent`.
- **Option C:** Push a static JWKS file to GitHub Pages and use `https://<github-org>.github.io/wbauth/jwks.json` as the URL. Works without any Cloudflare account at all.

**Recommended for Phase 1 CI smoke test:** Use Option A (RFC 9421 test key + Cloudflare's reference JWKS server). This proves end-to-end signing works without depending on our own infrastructure being deployed yet.

### Pitfall 8: Cross-platform 0o600 on Windows is a no-op

**What goes wrong:** SDK runs `os.chmod(path, 0o600)` on Windows. No error, no warning, but the permission isn't actually restricted — Windows uses ACLs, not POSIX modes.

**Why it happens:** On Windows, Python's `os.chmod` "basically has no effect" — only the read-only flag can be toggled. (Citation: search 2026-05-03.)

**How to avoid:** Detect platform; on Windows, log a clear warning (`"Windows detected — file permissions cannot be enforced via POSIX mode. Use NTFS ACLs or store the key in a per-user secrets vault."`) and skip the permission check on `_load`. For users who need real Windows enforcement, document `oschmod` as an opt-in extra dependency.

**Citation:** Search results 2026-05-03 (cross-platform Python permissions); python/cpython issue #95658.

## Code Examples

### Sign a request (the canonical Phase 1 flow)

```python
# Source: synthesized from http_message_signatures/signatures.py (verified GitHub master)
# + decisions D-09, D-11

from http_message_signatures import (
    HTTPMessageSigner, HTTPSignatureKeyResolver, algorithms
)
import datetime

class _IdentityKeyResolver(HTTPSignatureKeyResolver):
    """Adapts wbauth.Identity to http_message_signatures' resolver interface."""
    def __init__(self, identity: "Identity"):
        self._identity = identity

    def resolve_private_key(self, key_id: str):
        # cryptography Ed25519PrivateKey is what the algorithm expects directly
        return self._identity._private_key

    def resolve_public_key(self, key_id: str):
        return self._identity._private_key.public_key()


WEB_BOT_AUTH_TAG = "web-bot-auth"  # MUST be this exact string

def sign(request, identity: "Identity", *,
         created: datetime.datetime | None = None,
         expires_after_seconds: int = 60,
         nonce: str | None = None) -> SignatureHeaders:
    """Pure signer. Web Bot Auth profile."""
    # 1. Pre-set Signature-Agent header (RFC 8941 Structured Field, double-quoted)
    if not identity.signature_agent_url.startswith("https://"):
        raise ValueError(
            f"signature_agent_url must be https://, got: {identity.signature_agent_url}"
        )
    request.headers["Signature-Agent"] = f'"{identity.signature_agent_url}"'

    # 2. Compose the signer with Web Bot Auth defaults
    signer = HTTPMessageSigner(
        signature_algorithm=algorithms.ED25519,
        key_resolver=_IdentityKeyResolver(identity),
    )
    if created is None:
        created = datetime.datetime.now(datetime.timezone.utc)
    expires = created + datetime.timedelta(seconds=expires_after_seconds)

    # 3. sign() mutates request.headers in place, adding Signature + Signature-Input
    signer.sign(
        request,
        key_id=identity.kid,
        created=created,
        expires=expires,
        nonce=nonce,
        tag=WEB_BOT_AUTH_TAG,                    # <-- the magic string
        covered_component_ids=("@authority", "signature-agent"),
    )

    return SignatureHeaders(
        signature=request.headers["Signature"],
        signature_input=request.headers["Signature-Input"],
        signature_agent=request.headers["Signature-Agent"],
    )
```

### Generate a key with strict 0o600

```python
# Source: cryptography 47.x docs (verified WebFetch 2026-05-03) + research/PITFALLS.md Pitfall 4
# Important: O_CREAT|O_EXCL pattern avoids the chmod-after-write race

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import os
from pathlib import Path

def generate_key(path: Path) -> Ed25519PrivateKey:
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    # O_CREAT|O_EXCL: fail if file exists (force=True path elsewhere)
    # mode=0o600 from the syscall, no race window
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, pem)
    finally:
        os.close(fd)
    return key
```

### Compute kid (RFC 7638 thumbprint)

```python
# Source: RFC 7638 §3.1 + verified live against Cloudflare research server JWKS

import hashlib, base64, json

def _public_jwk(public_key) -> dict:
    """Canonical Ed25519 JWK (only required members, lex-sorted is implicit
    via the order json.dumps with sort_keys produces)."""
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "crv": "Ed25519",
        "kty": "OKP",
        "x": base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii"),
    }

def _compute_kid(public_key) -> str:
    jwk = _public_jwk(public_key)
    # RFC 7638: canonicalize → SHA-256 → base64url-no-pad
    canonical = json.dumps(jwk, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(canonical).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

# Sanity check: feed the RFC 9421 Appendix B.1.4 test key,
# expect kid == "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U"
# (verified live against http-message-signatures-example.research.cloudflare.com)
```

### Cloudflare debug verifier smoke test (CI hook)

```python
# Source: live HTTP probe + Cloudflare bots docs
# Endpoint behavior verified 2026-05-03:
#   GET / (no headers)              -> 400 "missing signature / signature-input / signature-agent headers"
#   GET / (with valid signed headers) -> 200 (key recognized + verified)
#   GET / (correct format, unknown key) -> 401

import httpx, datetime
from wbauth import Identity, sign, NormalizedRequest

def cloudflare_debug_smoke_test() -> None:
    """Used in CI: signs a request, sends to crawltest, asserts 200."""
    # Use the RFC 9421 Appendix B.1.4 test key + Cloudflare's research server
    # (which serves that key's JWKS publicly) so we don't need our own hosting.
    identity = Identity.from_test_key(
        signature_agent_url="https://http-message-signatures-example.research.cloudflare.com/"
    )
    req = NormalizedRequest(
        method="GET",
        url="https://crawltest.com/cdn-cgi/web-bot-auth",
        headers={},
    )
    sig = sign(req, identity, created=datetime.datetime.now(datetime.timezone.utc))

    response = httpx.get(
        "https://crawltest.com/cdn-cgi/web-bot-auth",
        headers={
            "Signature": sig.signature,
            "Signature-Input": sig.signature_input,
            "Signature-Agent": sig.signature_agent,
        },
    )
    assert response.status_code == 200, (
        f"Cloudflare verifier rejected: status={response.status_code}, body={response.text!r}"
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Roll-your-own RFC 9421 in each language | Use the verifier-vendor's library (`web-bot-auth` Cloudflare for TS) + pyauth's `http-message-signatures` for Python | 2025-2026 (libraries reached maturity in late 2025 / early 2026) | We integrate, not implement. Cuts 2-3 weeks off Phase 1 and eliminates a class of bugs. |
| Symmetric HMAC for HTTP message signatures | Asymmetric Ed25519 (Web Bot Auth profile **prohibits** HMAC) | Web Bot Auth draft -01+ | No shared-secret distribution; identity is the public key. |
| Custom Ed25519 from scratch | `cryptography` (PyCA) Ed25519 — first-class API since 2.6 (2018) | Stable since 2018 | Production-quality, audited, ships wheels. |
| `urllib.robotparser` for robots.txt | `protego` (RFC 9309 compliant) | Phase 2; mentioned only because Phase 1's plan should not accidentally ship a `urllib.robotparser` import | Phase 2 problem; flagged here so Phase 1 doesn't introduce the wrong choice. |
| `setuptools` + `pip` + `venv` | `uv` (Astral) — single binary, lockfile, workspaces | 2024-2025 stabilization | Faster, deterministic, no maintenance during army leave. |
| `npm` with workspaces | `pnpm` with `pnpm-workspace.yaml` | Mature since 2023 | Smaller node_modules; deterministic lockfile. |
| Fly.io / Railway for Python backend | Cloudflare Workers + D1 (TypeScript) for backend | D-02 (this project's locked decision) | Free tier eliminates billing surface; forces TS for backend. |

**Deprecated/outdated:**
- MkDocs Material: maintenance mode Nov 2025, Insiders deleted May 2026. (Not used here.)
- Pydantic v1: EOL'd. We use v2.
- `requests` as primary HTTP client: ship `requests-http-signature` integration in Phase 2 only as a thin alias for legacy users; primary is `httpx`.

## Section 1: Day-1 Hosting Test Procedure

This is the FIRST work item in Phase 1, before any SDK code.

### Goal

Confirm in ~30 minutes that: (a) the Cloudflare account can be created with the available payment method, (b) `wrangler` CLI authenticates, (c) a hello-world Worker deploys to `*.workers.dev`, (d) a D1 database is created and bound, (e) the Worker can read/write one row.

If any step fails, **stop and escalate to user before proceeding** (per D-04 — no automatic fallback).

### Free Tier Quotas (verified 2026-05-03)

[VERIFIED: developers.cloudflare.com/workers/platform/limits/]
- **Workers Free plan:** 100,000 requests/day, 10ms CPU per HTTP request, 3 MB script size (gzipped), 128 MB memory per isolate, 50 subrequests per invocation, 100 Workers per account, no credit card required.

[VERIFIED: developers.cloudflare.com/d1/platform/pricing/]
- **D1 Free tier:** 5 million rows read/day, 100,000 rows written/day, 5 GB storage total, scale-to-zero billing.

[VERIFIED: search results 2026-05-03]
- **No credit card required** for Workers Free plan. Account creation works without a payment method on file. Commercial use allowed on the free tier.

### Wrangler Commands (verified against current 4.87.0)

```bash
# 0. Ensure pnpm + Node 20+ installed locally
node --version    # expect v20.x or higher
pnpm --version    # expect 10.x

# 1. Inside the directory/ workspace member, install wrangler locally
cd directory/
pnpm add -D wrangler@latest    # currently 4.87.0

# 2. Authenticate (opens browser to dash.cloudflare.com)
npx wrangler login
# Expected: browser opens → "Allow Wrangler to access your Cloudflare account" → accept
# → terminal prints "Successfully logged in." If the dashboard is unreachable
# from the developer's network (e.g., RU geoblock), document the failure and escalate.

# 3. Scaffold a hello-world Worker (or copy directory/src/index.ts manually)
# Easiest: handwrite directory/src/index.ts as a 10-line fetch handler

# 4. Create a D1 database
npx wrangler d1 create wbauth-day1-test
# Expected output includes a "binding" block — copy that into wrangler.jsonc

# 5. Edit directory/wrangler.jsonc with the binding (see template below)

# 6. Apply schema
npx wrangler d1 execute wbauth-day1-test --remote --file=./schema.sql

# 7. Deploy
npx wrangler deploy
# Expected: prints "Deployed wbauth-day1-test to https://wbauth-day1-test.<your-subdomain>.workers.dev"

# 8. Smoke-test
curl https://wbauth-day1-test.<your-subdomain>.workers.dev/ping
# Expected: {"ok": true, "row_count": 1}

# 9. Confirm D1 row was written
npx wrangler d1 execute wbauth-day1-test --remote --command="SELECT * FROM hello"
# Expected: one row
```

### Templates

**`directory/wrangler.jsonc`:**

```jsonc
{
  "name": "wbauth-day1-test",
  "main": "src/index.ts",
  "compatibility_date": "2026-05-01",
  "d1_databases": [
    {
      "binding": "DB",
      "database_name": "wbauth-day1-test",
      "database_id": "<paste-from-d1-create-output>"
    }
  ]
}
```

**`directory/schema.sql`:**

```sql
CREATE TABLE IF NOT EXISTS hello (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message TEXT NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
INSERT INTO hello (message) VALUES ('Day 1 works');
```

**`directory/src/index.ts`:**

```typescript
export interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/ping") {
      const { results } = await env.DB.prepare(
        "SELECT COUNT(*) as count FROM hello"
      ).all<{ count: number }>();
      return Response.json({ ok: true, row_count: results[0].count });
    }
    return new Response("Day 1 hello-world", { status: 200 });
  },
};
```

### Failure Modes & Escalation

| Failure | Likely Cause | Escalate? |
|---------|--------------|-----------|
| `wrangler login` doesn't open browser, or browser hangs at dash.cloudflare.com | RU IP block on dashboard (not officially documented either way) | Yes — try a VPN; if still fails, escalate to user |
| Account creation requires payment method | Region-specific signup flow may differ; standard signup as of 2026-05-03 does NOT require a card | Yes — escalate, do not add a card |
| `wrangler d1 create` returns "subscription required" | Should not happen on free tier; possible region-specific behavior | Yes — escalate |
| `wrangler deploy` succeeds but `curl` returns 5xx | Worker code bug or missing binding | Iterate locally; not a hosting blocker |
| Day-1 test passes but later D1 writes fail | Almost certainly hit the 100k writes/day cap | Document; not a Day-1 issue |

## Section 2: Monorepo Scaffold Recipe

### Layout (concrete, verified against uv + pnpm docs)

[VERIFIED: docs.astral.sh/uv/concepts/projects/workspaces/]
[VERIFIED: pnpm.io/workspaces and pnpm.io/pnpm-workspace_yaml]

### Root `pyproject.toml` (uv workspace root)

```toml
# /pyproject.toml — uv workspace root only, NOT a package itself
[project]
name = "wbauth-monorepo-root"
version = "0.0.0"
requires-python = ">=3.11"
description = "Workspace root — not a published package"

[tool.uv.workspace]
members = ["python"]
# directory/ and typescript/ are pnpm-workspace members, not uv

[tool.uv]
package = false   # this root is not a package
```

### `python/pyproject.toml` (the actual SDK package)

```toml
# /python/pyproject.toml
[project]
name = "wbauth"
version = "0.1.0"
description = "Web Bot Auth (RFC 9421) Python SDK — agent identity for the agentic web"
readme = "README.md"
requires-python = ">=3.11"
license = "Apache-2.0"
authors = [{ name = "wbauth contributors" }]
dependencies = [
    "cryptography>=47,<48",
    "http-message-signatures>=2.0.1,<3",
    "httpx>=0.28,<0.30",
]

[project.optional-dependencies]
windows = ["oschmod>=0.3"]   # opt-in cross-platform chmod

[project.scripts]
agentid = "wbauth.cli:main"   # IDENT-01 CLI command

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/wbauth"]

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-anyio>=4",
    "ruff>=0.6",
    "pyright>=1.1",
]
```

### `pnpm-workspace.yaml` (TypeScript workspace root)

```yaml
# /pnpm-workspace.yaml
packages:
  - 'typescript'
  - 'directory'
```

### Root `package.json` (pnpm workspace root metadata)

```json
{
  "name": "wbauth-monorepo",
  "version": "0.0.0",
  "private": true,
  "packageManager": "pnpm@10.33.2",
  "scripts": {
    "test": "pnpm -r run test",
    "build": "pnpm -r run build",
    "lint": "pnpm -r run lint"
  },
  "engines": {
    "node": ">=20",
    "pnpm": ">=10"
  }
}
```

### `typescript/package.json` (the actual TS SDK package)

```json
{
  "name": "wbauth",
  "version": "0.1.0",
  "description": "Web Bot Auth (RFC 9421) TypeScript SDK",
  "type": "module",
  "main": "./dist/index.js",
  "module": "./dist/index.mjs",
  "types": "./dist/index.d.ts",
  "exports": {
    ".": {
      "import": "./dist/index.mjs",
      "require": "./dist/index.js",
      "types": "./dist/index.d.ts"
    }
  },
  "files": ["dist"],
  "license": "Apache-2.0",
  "scripts": {
    "build": "tsup src/index.ts --format esm,cjs --dts",
    "test": "vitest run",
    "lint": "biome check ."
  },
  "dependencies": {
    "web-bot-auth": "^0.1.3"
  },
  "devDependencies": {
    "@biomejs/biome": "^2",
    "@types/node": "^20",
    "tsup": "^8",
    "typescript": "^6",
    "vitest": "^4"
  }
}
```

### Sharing `spec/test-vectors/` Across Both Runtimes

The vectors live at the **repo root** (`spec/test-vectors/`). Both the Python tests and TypeScript tests resolve paths relative to the repo root. Concrete approach:

**Python (`python/tests/conftest.py`):**

```python
import json, pathlib, pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
VECTORS_DIR = REPO_ROOT / "spec" / "test-vectors"

def all_vector_dirs():
    return sorted(p for p in VECTORS_DIR.iterdir() if (p / "input.json").exists())

@pytest.fixture(params=all_vector_dirs(), ids=lambda p: p.name)
def vector(request):
    d = request.param
    return {
        "name": d.name,
        "input": json.loads((d / "input.json").read_text()),
        "expected": json.loads((d / "expected.json").read_text()),
    }
```

**TypeScript (`typescript/tests/helpers.ts`):**

```typescript
import { readdirSync, readFileSync, statSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const VECTORS_DIR = resolve(REPO_ROOT, "spec", "test-vectors");

export function loadAllVectors() {
  return readdirSync(VECTORS_DIR)
    .filter(name => statSync(resolve(VECTORS_DIR, name)).isDirectory())
    .map(name => ({
      name,
      input: JSON.parse(readFileSync(resolve(VECTORS_DIR, name, "input.json"), "utf-8")),
      expected: JSON.parse(readFileSync(resolve(VECTORS_DIR, name, "expected.json"), "utf-8")),
    }));
}
```

### CI Matrix (`.github/workflows/conformance.yml`)

```yaml
name: Cross-language Conformance
on: [push, pull_request]
jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --all-extras --dev
      - run: uv run pytest python/tests/test_vectors.py -v
  typescript:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 10 }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm --filter wbauth test
  cloudflare-debug:
    runs-on: ubuntu-latest
    needs: [python]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run python -m wbauth._smoke.cloudflare_debug
        # exits non-zero on anything but HTTP 200 from crawltest.com
```

## Section 3: Identity API Implementation Reference

### `Identity.load_or_generate()` — primary entry point

```python
# python/src/wbauth/identity.py
# Source: cryptography 47.x docs (verified) + research/PITFALLS.md Pitfalls 4 & 8

from __future__ import annotations
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey
)
from cryptography.hazmat.primitives import serialization
from dataclasses import dataclass, field
from pathlib import Path
import os, sys, hashlib, base64, json
from typing import Optional

DEFAULT_KEY_PATH = Path("~/.config/wbauth/key.pem").expanduser()


@dataclass(frozen=True)
class KeyPair:
    """A single Ed25519 keypair with its computed kid."""
    private_key: Ed25519PrivateKey
    kid: str

    def public_jwk(self) -> dict:
        raw = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return {
            "crv": "Ed25519",
            "kty": "OKP",
            "kid": self.kid,
            "x": base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii"),
        }


class Identity:
    """Long-lived agent identity. Holds Ed25519 keypair + signature-agent URL.
    Constructed once at process start; passed everywhere by reference."""

    def __init__(
        self,
        active: KeyPair,
        signature_agent_url: str,
        *,
        user_agent: Optional[str] = None,
        retiring: Optional[KeyPair] = None,
    ):
        if not signature_agent_url.startswith("https://"):
            raise ValueError(
                f"signature_agent_url must be https://, got: {signature_agent_url!r}"
            )
        self._active = active
        self._retiring = retiring
        self.signature_agent_url = signature_agent_url
        self.user_agent = user_agent

    # ---------- Public API ----------
    @property
    def kid(self) -> str:
        return self._active.kid

    def export_jwks(self) -> dict:
        keys = [self._active.public_jwk()]
        if self._retiring is not None:
            keys.append(self._retiring.public_jwk())
        return {"keys": keys}

    def rotate(self, new_path: Path | None = None) -> "Identity":
        """IDENT-07: generate new active key, demote current to retiring.
        Returns a new Identity (immutable update). Old key stays usable
        in retiring slot until next rotate() call drops it."""
        new_pair = _generate_keypair_to(new_path or DEFAULT_KEY_PATH)
        return Identity(
            active=new_pair,
            signature_agent_url=self.signature_agent_url,
            user_agent=self.user_agent,
            retiring=self._active,   # demote current → retiring
        )

    # ---------- Constructors ----------
    @classmethod
    def load_or_generate(
        cls,
        path: str | Path = DEFAULT_KEY_PATH,
        *,
        signature_agent_url: str,
        user_agent: Optional[str] = None,
    ) -> "Identity":
        path = Path(path).expanduser()
        if path.exists():
            pair = _load_keypair(path)
        else:
            pair = _generate_keypair_to(path)
        return cls(pair, signature_agent_url, user_agent=user_agent)

    @classmethod
    def from_test_key(cls, signature_agent_url: str) -> "Identity":
        """For tests + Cloudflare debug smoke. Uses RFC 9421 Appendix B.1.4
        publicly-known Ed25519 test key. NEVER use in production."""
        d = base64.urlsafe_b64decode("n4Ni-HpISpVObnQMW0wOhCKROaIKqKtW_2ZYb2p9KcU=")
        key = Ed25519PrivateKey.from_private_bytes(d)
        return cls(KeyPair(key, _compute_kid(key.public_key())),
                   signature_agent_url)

    # ---------- Redaction guarantees (IDENT-08) ----------
    def __repr__(self) -> str:
        return f"<Identity REDACTED kid={self.kid!r} sig_agent={self.signature_agent_url!r}>"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("Identity is not pickleable (would leak private key material)")


# ---------- Helpers ----------

def _compute_kid(public_key: Ed25519PublicKey) -> str:
    """RFC 7638 thumbprint."""
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    jwk = {"crv": "Ed25519", "kty": "OKP",
           "x": base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")}
    canonical = json.dumps(jwk, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(canonical).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _load_keypair(path: Path) -> KeyPair:
    if sys.platform != "win32":
        mode = os.stat(path).st_mode & 0o777
        if mode & 0o077:
            raise PermissionError(
                f"Key file {path} has mode {oct(mode)}; expected 0o600. "
                f"Fix: chmod 600 {path}"
            )
    pem = path.read_bytes()
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError(f"Expected Ed25519, got {type(key).__name__}")
    return KeyPair(key, _compute_kid(key.public_key()))


def _generate_keypair_to(path: Path) -> KeyPair:
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Key already exists at {path}; refuse overwrite")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, pem)
    finally:
        os.close(fd)
    return KeyPair(key, _compute_kid(key.public_key()))
```

### CLI for IDENT-01: `agentid keygen`

```python
# python/src/wbauth/cli.py
import sys, argparse
from pathlib import Path
from .identity import Identity, DEFAULT_KEY_PATH

def main():
    p = argparse.ArgumentParser(prog="agentid")
    sub = p.add_subparsers(dest="cmd", required=True)
    kg = sub.add_parser("keygen")
    kg.add_argument("--output", default=str(DEFAULT_KEY_PATH))
    args = p.parse_args()
    if args.cmd == "keygen":
        # signature_agent_url is required by Identity, but for `agentid keygen`
        # alone we just need the kid; pass a placeholder and warn
        identity = Identity.load_or_generate(
            args.output,
            signature_agent_url="https://example.invalid/placeholder",
        )
        print(f"Wrote key to {args.output} (mode 0o600)")
        print(f"kid: {identity.kid}")
        return 0
```

## Section 4: Signer Implementation Reference

### Library API (verified against pyauth source)

`http_message_signatures.HTTPMessageSigner.sign()` accepts (from verified source `signatures.py`):

```python
sign(
    message,                     # request object with .headers, .method, .url
    *,
    key_id: str,                 # → keyid param in Signature-Input
    created: datetime | None,    # → created= param (defaults to now)
    expires: datetime | None,    # → expires= param (we set to created+60)
    nonce: str | None,           # → nonce= param (optional; recommended for replay defense)
    label: str | None,           # → signature label (default "pyhms"; we'll use "sig1")
    tag: str | None,             # → tag= param (we set to "web-bot-auth")
    include_alg: bool = True,    # → emits alg="ed25519"
    covered_component_ids: Sequence[str] = ("@method", "@authority", "@target-uri"),
                                 # we override to ("@authority", "signature-agent")
    append_if_signature_exists: bool = False,
)
```

The library's `signature_metadata_parameters` set is `{"alg", "created", "expires", "keyid", "nonce", "tag"}` — all the params Web Bot Auth needs are covered natively.

### Web Bot Auth Profile Defaults (locked)

```python
# python/src/wbauth/signer.py
from http_message_signatures import HTTPMessageSigner, HTTPSignatureKeyResolver, algorithms
import datetime, secrets

WEB_BOT_AUTH_TAG = "web-bot-auth"           # NEVER change
DEFAULT_LABEL = "sig1"                       # canonical label
DEFAULT_EXPIRES_SECONDS = 60                 # research says 30 too short, 60 safe
DEFAULT_COMPONENTS = ("@authority", "signature-agent")
# For POST requests with a body, append "content-digest" — see _components_for()


class _IdentityResolver(HTTPSignatureKeyResolver):
    def __init__(self, identity):
        self._identity = identity
    def resolve_private_key(self, key_id):
        return self._identity._active.private_key  # Ed25519PrivateKey directly
    def resolve_public_key(self, key_id):
        return self._identity._active.private_key.public_key()


def _components_for(method: str, has_body: bool) -> tuple[str, ...]:
    base = list(DEFAULT_COMPONENTS)
    if has_body and method.upper() in ("POST", "PUT", "PATCH"):
        base.append("content-digest")
    return tuple(base)


def sign(request, identity, *,
         created: datetime.datetime | None = None,
         expires_after_seconds: int = DEFAULT_EXPIRES_SECONDS,
         nonce: str | None = None,
         label: str = DEFAULT_LABEL) -> SignatureHeaders:
    """Pure signer. Mutates request.headers in place AND returns a SignatureHeaders dataclass."""

    # 1. Set Signature-Agent (Structured Field, double-quoted)
    request.headers["Signature-Agent"] = f'"{identity.signature_agent_url}"'

    # 2. If body present, set Content-Digest before signing
    has_body = bool(getattr(request, "body", None) or getattr(request, "content", None))
    # ... (caller is responsible for Content-Digest header in v1; document this)

    # 3. Defaults
    if created is None:
        created = datetime.datetime.now(datetime.timezone.utc)
    expires = created + datetime.timedelta(seconds=expires_after_seconds)
    if nonce is None:
        nonce = secrets.token_urlsafe(16)

    # 4. Sign
    signer = HTTPMessageSigner(
        signature_algorithm=algorithms.ED25519,
        key_resolver=_IdentityResolver(identity),
    )
    signer.sign(
        request,
        key_id=identity.kid,
        created=created,
        expires=expires,
        nonce=nonce,
        label=label,
        tag=WEB_BOT_AUTH_TAG,
        covered_component_ids=_components_for(request.method, has_body),
    )

    return SignatureHeaders(
        signature=request.headers["Signature"],
        signature_input=request.headers["Signature-Input"],
        signature_agent=request.headers["Signature-Agent"],
    )
```

### Sample Output (canonical signing-base for vector 01)

For input `GET https://crawltest.com/cdn-cgi/web-bot-auth` with `signature-agent="https://example.com/jwks"`, `created=1735689600`, `expires=1735689660`, `keyid="poqkLGiymh_W..."`, `tag="web-bot-auth"`, `alg="ed25519"`, `nonce="abc"`:

The signature base (what gets signed) looks like:

```
"@authority": crawltest.com
"signature-agent": "https://example.com/jwks"
"@signature-params": ("@authority" "signature-agent");created=1735689600;keyid="poqkLGiymh_W...";alg="ed25519";expires=1735689660;nonce="abc";tag="web-bot-auth"
```

Then `Signature-Input` header value:

```
sig1=("@authority" "signature-agent");created=1735689600;keyid="poqkLGiymh_W...";alg="ed25519";expires=1735689660;nonce="abc";tag="web-bot-auth"
```

And `Signature` is `sig1=:<base64-of-Ed25519-signature>:`.

## Section 5: Test Vector Schema

### `input.json` schema (per vector)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "name": "01-basic-get",
  "description": "GET request with @authority + signature-agent only",
  "request": {
    "method": "GET",
    "url": "https://crawltest.com/cdn-cgi/web-bot-auth",
    "headers": {},
    "body": null
  },
  "identity": {
    "private_key_jwk": {
      "kty": "OKP",
      "crv": "Ed25519",
      "d": "n4Ni-HpISpVObnQMW0wOhCKROaIKqKtW_2ZYb2p9KcU",
      "x": "JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bs"
    },
    "signature_agent_url": "https://http-message-signatures-example.research.cloudflare.com/"
  },
  "signing_params": {
    "created": 1735689600,
    "expires_after_seconds": 60,
    "nonce": "test-nonce-01-fixed",
    "label": "sig1",
    "covered_components": ["@authority", "signature-agent"]
  }
}
```

### `expected.json` schema (per vector)

```json
{
  "kid": "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U",
  "signature_input_value": "sig1=(\"@authority\" \"signature-agent\");created=1735689600;keyid=\"poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U\";alg=\"ed25519\";expires=1735689660;nonce=\"test-nonce-01-fixed\";tag=\"web-bot-auth\"",
  "signature_value": "sig1=:<base64-of-deterministic-Ed25519-signature>:",
  "signature_agent_value": "\"https://http-message-signatures-example.research.cloudflare.com/\"",
  "jwks_kid_thumbprint": "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U"
}
```

### Why Byte-Equal Verification Works

**Ed25519 is deterministic:** `Sign(sk, m)` produces the same 64-byte signature every time, no nonce-in-the-crypto involved (that's ECDSA's problem). The only "nonce" in our flow is the optional RFC 9421 `nonce=` parameter — which is itself signed (so we fix it in the vector input, not generated).

**Therefore:** given a fixed private key + fixed `created` + fixed `expires` + fixed `nonce` + fixed components → the `Signature-Input` string is deterministic AND the `Signature` bytes are deterministic. We can capture both and assert byte-equality across runs and across language implementations.

### Vector Generation Strategy (chicken-and-egg)

The first vector cannot have an `expected.json` until the signer exists. Resolution:

1. Implement the Python signer first.
2. Author `input.json` for vector 01 (using the RFC 9421 test key).
3. Run the Python signer once with that input → capture output → write `expected.json`.
4. Manually verify the `expected.json` against an independent oracle:
    - Cross-check by running `web-bot-auth` 0.1.3 in TypeScript with the same input (this is exactly what cross-language CI does on every push thereafter).
    - Send the signed request to `https://crawltest.com/cdn-cgi/web-bot-auth` once — if it returns 200, the vector is canonically correct.
5. Commit input + expected as the first locked vector. Subsequent vectors follow the same flow.

### Five (Six) Initial Vectors

Per D-11:

| # | Name | What it covers |
|---|------|---------------|
| 01 | `01-basic-get` | GET with `@authority` + `signature-agent` only — minimum viable signature |
| 02 | `02-post-with-content-digest` | POST with body + `content-digest` covered component |
| 03 | `03-custom-expiry` | `expires_after_seconds=300` (non-default) — proves param is plumbed through |
| 04 | `04-multi-uri-jwks` | Identity with retiring key — JWKS export contains 2 keys; signature uses active only |
| 05 | `05-cloudflare-quirk` | TBD during implementation — likely "@authority is lowercase host, even if URL is mixed-case" or "signature-agent appears in components even though not mentioned in URL" |
| 06 | `06-cloudflare-debug-live` | NOT a byte-equal vector — runs the smoke test against `crawltest.com/cdn-cgi/web-bot-auth` and asserts HTTP 200 |

## Section 6: Cloudflare Debug Verifier Integration

### Two Endpoints (both verified live 2026-05-03)

| Endpoint | Returns | Use When |
|----------|---------|----------|
| `https://crawltest.com/cdn-cgi/web-bot-auth` | Plain text + status code: 200 = verified ok, 401 = key unknown, 400 = malformed | **Primary CI smoke test.** Programmatic, terse, fast. Returned `400 missing signature / signature-input / signature-agent headers` on unsigned probe. |
| `https://http-message-signatures-example.research.cloudflare.com/debug` | HTML page (intended for human inspection); Returns 200 even on no headers (the page tells you what's missing) | **Manual debugging.** Open in browser, see formatted explanation of what failed. Useful during development, not for CI. |
| `https://http-message-signatures-example.research.cloudflare.com/.well-known/http-message-signatures-directory` | JSON: `{"keys":[{"kid":"poqkLGiymh_W...","kty":"OKP","crv":"Ed25519","x":"JrQLj5P..."}],"purpose":"rag"}` | Use the `kid`+`x` here to confirm the JWK thumbprint algorithm is correct (compute SHA-256 over canonical JWK and compare to `kid`). |

### Constraints & Quirks

[VERIFIED: WebFetch developers.cloudflare.com/bots/reference/bot-verification/web-bot-auth/]
- **Rejected derived components:** `@query-params`, `@status`. Don't sign these.
- **Unsupported parameters in components:** `sf`, `bs`, `key`, `req`, `name`. Don't use these.
- **Recommended:** `@authority` + ASCII-only header values.
- **JWKS reachability:** the `Signature-Agent` URL MUST be publicly reachable over HTTPS. If unreachable → `401`. **No JWKS = no verification.**
- **Rate limits:** not officially documented. Assume reasonable use (CI runs once per push, not in a tight loop).
- **kid format:** base64url-no-pad of SHA-256 over canonical JWK per RFC 7638 / RFC 8037 Appendix A.3. Example: `poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U`.

### CI Hook (one-shot)

```yaml
# .github/workflows/cloudflare-debug.yml
name: Cloudflare Debug Verifier
on:
  push: {branches: [main]}
  pull_request:
  schedule:
    - cron: '0 12 * * *'   # daily canary, per PITFALLS.md Pitfall 12
jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - name: Sign + send to crawltest.com
        run: uv run python -m wbauth._smoke.cloudflare_debug
        # Implementation: uses Identity.from_test_key() with
        # signature_agent_url=https://http-message-signatures-example.research.cloudflare.com/
        # so the verifier can fetch the JWKS publicly.
        # Asserts response.status_code == 200; non-zero exit otherwise.
```

### CLI Hook (`agentid verify --domain`)

For Phase 2 (CLI-03), but the implementation uses the same module Phase 1 ships:

```bash
agentid verify --domain crawltest.com
# Internally: signs a probe request with the user's loaded identity,
# POSTs to https://<domain>/cdn-cgi/web-bot-auth, prints pass/fail per criterion.
```

## Section 7: Open Questions / Things To Verify At Implementation Time

1. **Does `http-message-signatures` 2.0.1 emit `alg="ed25519"` (lowercase) by default for the `algorithms.ED25519` algorithm class?** [ASSUMED] Verified library has `include_alg: bool = True` flag — but the exact string emitted by `signature_algorithm.algorithm_id` for ED25519 needs to be confirmed against Cloudflare's expectations. RFC 9421 IANA registry says `ed25519`. **Action:** during implementation, dump the produced `Signature-Input` for the first vector and confirm `alg="ed25519"` appears literally. If Cloudflare expects something else (e.g., `Ed25519`), wrap the algorithm class to override.

2. **Does the Python library accept `Ed25519PrivateKey` objects directly via `key_resolver.resolve_private_key()`, or does it require raw bytes / a specific wrapper?** [ASSUMED based on synopsis showing `b"top-secret-key"` for HMAC, but Ed25519 algorithm class likely expects the cryptography library's key object since that's what its own `_algorithms.py` would consume.] **Action:** test in the first integration test; if it requires raw bytes, the resolver returns `private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())` — 32 bytes.

3. **What does `wrangler login` do if Cloudflare's dashboard is unreachable from the developer's IP?** [ASSUMED based on indirect evidence — search results don't confirm or deny RU geoblock] — community reports vary. **Mitigation:** Day-1 hosting test runs first; if `wrangler login` hangs or browser doesn't open, escalate per D-04 before any time is invested in code. Manual workaround: generate API token in dashboard via VPN, set `CLOUDFLARE_API_TOKEN` env var, skip `wrangler login`.

4. **What's the canonical kid format Cloudflare expects when `Signature-Agent` URL is multi-key JWKS?** [VERIFIED via JWKS endpoint: each entry has its own `kid` field; signer references the `kid` of the active key as the `keyid=` param in `Signature-Input`. If JWKS contains active+retiring, the verifier picks by `keyid` match.] No action needed — Phase 3 will exercise this end-to-end.

5. **Edge case for vector 05 (Cloudflare-specific quirk):** to be discovered during implementation. Candidates: (a) `@authority` lowercasing when URL contains uppercase host, (b) `signature-agent` URL with trailing slash vs without, (c) URL with port (`:443`) explicit vs implicit. Pick whichever surfaces during the first round of vector authoring.

6. **Does `tag="web-bot-auth"` need to be quoted in `Signature-Input`?** [ASSUMED yes since it's a string parameter per RFC 8941 Item Parameters] — `http-message-signatures` 2.0.1 uses `http_sfv` library to encode all params, so this should be handled automatically. **Verify:** dump the produced header and confirm `tag="web-bot-auth"` appears (with quotes), not `tag=web-bot-auth`.

7. **POSIX file mode check on a SMB-mounted filesystem (corp environment edge case):** behavior undefined; user fix is "store key on a local POSIX filesystem." Not blocking.

8. **`signature-agent` URL during local dev:** RECOMMENDATION (Section 6 Pitfall 7 Option A) — use `https://http-message-signatures-example.research.cloudflare.com/` as the URL during Phase 1 dev/CI; switch to `https://<name>.workers.dev/.well-known/http-message-signatures-directory` once Phase 1's hosting test confirms the worker is reachable. After Phase 3 (directory backend), agents publish to `https://<name>.workers.dev/.well-known/http-message-signatures-directory/<id>`. **No placeholder URL — using the Cloudflare research server's URL means the JWKS is real and the test key is real.**

## Environment Availability

Day-1 hosting check + dev environment audit. Probed against the developer's machine 2026-05-03.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python ≥3.11 | Python SDK | ✓ (assumed; user is Python developer) | — | If <3.11, install via uv: `uv python install 3.11` |
| Node ≥20 | TypeScript SDK + wrangler | ✓ (assumed) | — | nvm: `nvm install 20 && nvm use 20` |
| pnpm ≥10 | TypeScript workspace | ⚠ (verify) | — | `npm install -g pnpm@10` |
| uv ≥0.11 | Python workspace | ⚠ (verify) | — | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Cloudflare account | Day-1 hosting test (DIR-06) | ✗ (not yet created) | — | None — IS the hosting test; D-04 dictates escalation if signup fails |
| `wrangler` CLI | Day-1 hosting test | ✗ (will be installed via `pnpm add -D wrangler`) | — | Install per Section 1 |
| `cryptography` 47.x | Identity API | ✗ (will install via uv) | — | None |
| `http-message-signatures` 2.0.1 | Signer | ✗ (will install via uv) | — | None |
| `web-bot-auth` 0.1.3 npm | Cross-language vector check | ✗ (will install via pnpm) | — | None |
| Public internet from CI | Cloudflare debug verifier smoke test | ✓ (GitHub Actions runners are public) | — | None |
| Public internet from dev machine | Live debug during dev | ✓ (verified — `curl crawltest.com` returned 400 as expected) | — | If RU IP blocked from CF dashboard, use VPN to do account-creation steps |

**Missing dependencies with no fallback:**
- Cloudflare account creation: blocking for DIR-06. If signup fails or requires a card the user doesn't want to provide, planner halts and escalates per D-04.

**Missing dependencies with fallback:**
- pnpm/uv install: standard one-line installers exist.

## Validation Architecture

> Skipped — `workflow.nyquist_validation` is `false` in `.planning/config.json`.

## Security Domain

`security_enforcement: true`, ASVS Level 1 in `.planning/config.json`.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Phase 1 produces signing primitives; user authentication is out of scope (the agent identity IS the public key). |
| V3 Session Management | no | No sessions in the signer. |
| V4 Access Control | no | No authorization in the signer. |
| V5 Input Validation | yes | `Identity.__init__` validates `signature_agent_url` is `https://`. CLI validates `--output` path. Loader validates PEM format and key type (`Ed25519PrivateKey`). |
| V6 Cryptography | **yes** (primary surface) | Use `cryptography` (PyCA) `Ed25519PrivateKey` for keygen + sign. Never hand-roll Ed25519. PEM serialization via `serialization.PrivateFormat.PKCS8` + `NoEncryption()` (no encryption-at-rest in v1; protected by 0o600 file mode). |
| V7 Error Handling | yes | Permission errors raise `PermissionError` with remediation message, NEVER include key bytes in the message. |
| V8 Data Protection | **yes** (primary surface) | `Identity.__repr__` returns REDACTED. `__reduce__` raises to refuse pickling. Keyfiles written via `os.open(..., 0o600)` with O_EXCL to prevent race. Loader refuses files with mode wider than 0o600 on POSIX. **Test-vector key is the publicly-known RFC 9421 Appendix B.1.4 key — never a real key in the repo.** |
| V9 Communication | yes | All Cloudflare debug + JWKS fetches are HTTPS. `signature_agent_url` is enforced HTTPS at construction. |
| V14 Configuration | yes | Default key path `~/.config/wbauth/key.pem` follows XDG-ish convention; never `/tmp/`, never `~/.ssh/`. CLI prints exact path on keygen so user knows where to find it. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Private key leaked via log/stack-trace | Information Disclosure | `__repr__` returns REDACTED; never include `Identity` object in log messages or exception args. |
| Key file world-readable due to umask | Information Disclosure | `os.open(path, O_WRONLY\|O_CREAT\|O_EXCL, 0o600)` — mode set at syscall, no race. Loader refuses mode > 0o600. |
| Key serialized via pickle.dumps to a debug log | Information Disclosure | `__reduce__` raises `TypeError`. |
| Test-vector key accidentally used in production | Information Disclosure | `Identity.from_test_key()` is the ONLY way to construct from the public test key, and its docstring says "NEVER use in production." Document in README. |
| Signature replay (same signed request reused) | Spoofing | `nonce` parameter (random 16 bytes) + `expires` parameter (created+60s). Verifiers track nonces. |
| Clock skew causing intermittent verification failure | Denial of Service (self-inflicted) | `expires=created+60` (not 30). Document NTP requirement. |
| Verifier downgrade to HTTP `Signature-Agent` URL | Spoofing | `signature_agent_url` is enforced `https://` at construction time. |
| `tag="web-bot-auth"` typo (e.g., `webbotauth`) silently accepted by SDK | Tampering | Hard-coded module constant; integration test asserts the literal string appears in the produced header. |
| Multi-key Identity exports retiring key but signs with retired key | Tampering | `signer.sign()` uses `identity.kid` which is the active key's kid; resolver returns active key's private bytes; retiring key's private bytes are NEVER returned by the resolver. |

## Sources

### Primary (HIGH confidence — verified live 2026-05-03)

- [pyauth/http-message-signatures source `signatures.py`](https://raw.githubusercontent.com/pyauth/http-message-signatures/master/http_message_signatures/signatures.py) — confirmed `sign()` parameter list including `tag`, `expires`, `covered_component_ids`; verified `max_clock_skew=5s` in verifier
- [pyauth/http-message-signatures algorithms](https://raw.githubusercontent.com/pyauth/http-message-signatures/master/http_message_signatures/algorithms.py) — confirmed `ED25519` exposed
- [npm `web-bot-auth` 0.1.3 README](https://github.com/cloudflare/web-bot-auth/tree/main/packages/web-bot-auth) — confirmed `signatureHeaders(request, signer, {created, expires})` API; confirmed RFC 9421 Appendix B.1.4 test key shape
- [PyPI `cryptography` JSON metadata](https://pypi.org/pypi/cryptography/json) — version 47.0.0 current
- [PyPI `http-message-signatures` JSON metadata](https://pypi.org/pypi/http-message-signatures/json) — version 2.0.1 current, `requires_python>=3.10`
- [npm `wrangler` registry](https://registry.npmjs.org/wrangler) — version 4.87.0 current
- [npm `web-bot-auth` registry](https://registry.npmjs.org/web-bot-auth) — version 0.1.3 published 2026-03-09; deps `http-message-sig@0.2.0` + `jsonwebkey-thumbprint@0.1.0`
- [Cloudflare Web Bot Auth bot docs](https://developers.cloudflare.com/bots/reference/bot-verification/web-bot-auth/) — confirmed crawltest.com endpoint behavior (200/401/400), rejected components (`@query-params`, `@status`), JWK thumbprint format
- [Cloudflare Workers Free plan limits](https://developers.cloudflare.com/workers/platform/limits/) — 100k req/day, 10ms CPU, 3 MB script
- [Cloudflare D1 free tier](https://developers.cloudflare.com/d1/platform/pricing/) — 5M reads/day, 100k writes/day, 5 GB
- [uv workspaces docs](https://docs.astral.sh/uv/concepts/projects/workspaces/) — confirmed `[tool.uv.workspace] members=[...]` format
- [pnpm workspaces docs](https://pnpm.io/workspaces) and [`pnpm-workspace.yaml`](https://pnpm.io/pnpm-workspace_yaml) — confirmed `packages:` glob format
- [PyCA cryptography Ed25519 docs](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/) — confirmed `generate()`, `sign(data)`, `public_bytes(Raw, Raw)`, `private_bytes(PEM, PKCS8, NoEncryption)`, `from_private_bytes()`
- Live HTTP probe to `https://crawltest.com/cdn-cgi/web-bot-auth` — confirmed `400 missing signature / signature-input / signature-agent headers` on unsigned GET
- Live HTTP probe to `https://http-message-signatures-example.research.cloudflare.com/.well-known/http-message-signatures-directory` — confirmed JWKS shape `{"keys":[{"kid":"poqkLGiymh_W...","kty":"OKP","crv":"Ed25519","x":"JrQLj5P..."}],"purpose":"rag"}`

### Secondary (MEDIUM confidence — synthesized from upstream research)

- [`.planning/research/SUMMARY.md`](../../research/SUMMARY.md) — convergent decisions; phase ordering rationale
- [`.planning/research/STACK.md`](../../research/STACK.md) — stack matrix (note: claimed cryptography 46.x; current is 47.0.0 — within minor-version compat)
- [`.planning/research/ARCHITECTURE.md`](../../research/ARCHITECTURE.md) — pure-function signer pattern, identity-as-long-lived-object, monorepo layout
- [`.planning/research/PITFALLS.md`](../../research/PITFALLS.md) — pitfalls 1-8 directly applicable to Phase 1
- [`.planning/research/FEATURES.md`](../../research/FEATURES.md) — Web Bot Auth profile rules: tag, signed components, JWKS

### Tertiary (LOW confidence — flagged for validation during execution)

- Cloudflare dashboard / wrangler accessibility from RU IP — search results don't confirm or deny; mitigation is Day-1 escalation per D-04
- Cloudflare debug verifier rate limits — not officially documented; assume reasonable use
- Exact `alg=` string emitted by `algorithms.ED25519` (lowercase `ed25519` per IANA, but verify dump-and-inspect during implementation)

## Assumptions Log

> Items planner and discuss-phase should treat as needing user confirmation before becoming locked decisions, OR things to verify during implementation.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Cloudflare account signup works from developer's network without a credit card | Section 1 | Hard blocker for DIR-06; D-04 says escalate. |
| A2 | `wrangler login` browser flow works from developer's network | Section 1 | Hard blocker for DIR-06; mitigation is API token via VPN. |
| A3 | `algorithms.ED25519` in http-message-signatures emits `alg="ed25519"` (lowercase) | Section 4, Section 7 Q1 | Cloudflare verifier MAY reject other casing; trivial fix during implementation if so. |
| A4 | Resolver's `resolve_private_key()` can return `Ed25519PrivateKey` objects directly (not raw bytes) | Section 4, Section 7 Q2 | If wrong, return `private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())` — 32 bytes. Documented mitigation. |
| A5 | Using `https://http-message-signatures-example.research.cloudflare.com/` as `signature_agent_url` during Phase 1 dev/CI is acceptable to Cloudflare's debug verifier (it serves the test key publicly) | Section 6 Pitfall 7 | If verifier requires JWKS at a specific path (e.g., must be ours), fall back to publishing JWKS to GitHub Pages OR completing the Day-3 Worker JWKS endpoint. |
| A6 | The `tag` parameter is auto-quoted by `http_sfv` library | Section 7 Q6 | Verify by dumping output; if not, wrap in `'"web-bot-auth"'` manually. |
| A7 | `cryptography` 47.x is API-compatible with the 46.x version called out in STACK.md | Section "Standard Stack" | Highly likely (PyCA's stable Ed25519 API hasn't broken since 2.6); pin upper bound `<48`. |
| A8 | `web-bot-auth` 0.1.3 npm package's `signatureHeaders()` produces byte-equivalent output to `http-message-signatures` 2.0.1 Python given same input/key/timestamp | Section 5 vector strategy | If they diverge, one of them deviates from RFC 9421; Cloudflare's package is the verifier-vendor — if anything, conform Python to TS, not vice-versa. Investigation case if vector check fails. |
| A9 | Default key path `~/.config/wbauth/key.pem` is acceptable to user (D-09 said this is Claude's discretion to propose) | Section 3 | If user prefers `~/.local/share/wbauth/...` (XDG_DATA), trivially configurable. Surface in plan for sign-off. |
| A10 | Windows users are a minority for v1; documented `sys.platform`-based skip-with-warning is acceptable instead of full `oschmod` integration | Section 3 Pattern 2 + Pitfall 8 | If a Windows user reports key-leak, escalate post-army; v1 documents the limitation. |

**If this table is empty:** N/A — assumptions remain. Discuss-phase already gathered the locked decisions; assumptions A1, A2, A5, A9 are the most likely to need a quick user confirmation before plan execution begins. A3, A4, A6, A8 are implementation-time verifications (no user input needed; just dump-and-inspect tasks in the first plan).

## Open Questions

1. **Should Phase 1 ship the CLI (`agentid keygen`) or defer to Phase 2 (CLI-01 is mapped to Phase 2 in REQUIREMENTS.md)?**
   - What we know: REQUIREMENTS.md traceability says CLI-01 → Phase 2. But IDENT-01 says "via Python API and CLI" — they're coupled.
   - What's unclear: do we ship the keygen CLI in Phase 1 to satisfy IDENT-01's CLI half, and let Phase 2 add `inspect`/`verify`/`register`?
   - Recommendation: ship `agentid keygen` in Phase 1 (it's 30 LOC and satisfies IDENT-01); the broader CLI surface (`inspect`, `verify --domain`, `register`) lives in Phase 2.

2. **Where should the Python entry-point script declared in `pyproject.toml` go — `agentid` or `wbauth`?**
   - What we know: REQUIREMENTS.md uses `agentid` as the CLI name. D-06 says public import is `wbauth`.
   - What's unclear: do we name the CLI `wbauth` for consistency with the package, or keep `agentid` for the docs/README narrative?
   - Recommendation: use `wbauth` as the CLI command (`wbauth keygen`). Cleaner for users — one name to remember. Update REQUIREMENTS.md docs accordingly. Surface as a sub-decision in plan-checker review.

3. **Can the Day-1 hosting test reuse the eventual `directory/` workspace member, or should it be a throwaway (`directory-day1/`)?**
   - Recommendation: use `directory/` from the start with a temporary `src/index.ts` that only does the hello-world ping. Phase 3 replaces `src/index.ts` with the real backend. Schema (`schema.sql`) starts as the day-1 `hello` table; Phase 3 migrates it. Keeping it throwaway costs a delete-and-recreate.

4. **Does Phase 1 need the `MAINTAINER_AWAY.md` and `v1.x-frozen` branch (HARDEN-03)?**
   - What we know: HARDEN-03 is mapped to Phase 5.
   - Recommendation: defer — Phase 5 owns it. Phase 1 should add a one-line note in the README saying "this is pre-1.0; expect the API to lock at the v1.0 tag."

5. **Test vector for "Cloudflare-specific quirk" (vector 05) — what to pick?**
   - Recommendation: defer the choice to implementation time. Likely candidate: a request where the URL has uppercase hostname (`https://Crawltest.com/...`) and the verifier expects `@authority` to be lowercased — Phase 1 implementer picks the first surprise that surfaces during the first round of vector authoring.

## Metadata

**Confidence breakdown:**
- Standard stack (libraries + versions): HIGH — versions verified live against npm + PyPI 2026-05-03; APIs verified by reading source for `http-message-signatures` and the README of `web-bot-auth` 0.1.3.
- Architecture (Identity, signer pattern): HIGH — directly derived from research/ARCHITECTURE.md and the verified library APIs.
- Pitfalls: HIGH for protocol-specific (Cloudflare docs verified live); HIGH for crypto hygiene (well-established patterns); MEDIUM for Windows cross-platform (search-derived, not personally tested).
- Day-1 hosting procedure: HIGH for command sequence (verified vendor docs); MEDIUM for "will signup work from developer's network" (no public source confirms or denies — escalation gated by D-04).
- Test-vector format: HIGH for schema; MEDIUM for "vector 05 edge case" (TBD by design).

**Research date:** 2026-05-03

**Valid until:** 2026-06-03 — re-verify versions if implementation begins after this date. The protocol (RFC 9421 + Web Bot Auth draft) is stable on a months-to-years horizon; the libraries (`http-message-signatures`, `web-bot-auth`, `wrangler`) are on weeks-to-months churn. `web-bot-auth` 0.1.3 (March 2026) is particularly young — track its repo for breaking changes.
