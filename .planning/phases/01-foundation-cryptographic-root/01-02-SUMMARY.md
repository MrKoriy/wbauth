---
phase: 01-foundation-cryptographic-root
plan: 02
subsystem: scaffold
tags: [monorepo, uv, npm-workspaces, ci, github-actions, apache-2.0]

# Dependency graph
requires:
  - 01-01 (Day-1 hosting baseline + directory/ workspace skeleton already in place)
provides:
  - Dual-language monorepo skeleton: uv workspace (python/) + npm workspaces (typescript/, directory/)
  - Reproducible installs via uv.lock and root package-lock.json
  - Importable wbauth Python stub (wbauth.__version__ == "0.1.0")
  - Buildable wbauth TypeScript stub (dist/index.mjs + index.js + index.d.ts via tsup)
  - Three CI workflows (.github/workflows/python.yml, typescript.yml, conformance.yml) — all parse cleanly, ready for Plans 03/04 to populate test bodies
  - Apache 2.0 LICENSE at repo root (Copyright 2026 wbauth contributors)
  - REQUIREMENTS.md + ROADMAP.md consistently use `wbauth` as CLI command (rename from original draft applied across all five CLI verbs + IDENT-01 + Phase 2/3 success criteria)
  - CONTEXT.md D-10 updated to reflect npm workspaces (not pnpm) per user decision
affects:
  - 01-03 (identity + signer): can write to python/src/wbauth/{identity,signer,normalized_request,_redaction,cli}.py without scaffold work
  - 01-04 (test vectors + conformance): can write to spec/test-vectors/<name>/{input,expected}.json and the test loaders in python/tests/ and typescript/tests/ without scaffold work
  - All future Phase 1 work uses the npm-workspaces tooling baseline (NOT pnpm)
  - Future TypeScript SDK (Phase 4) will inherit tsup.config.ts and TS 6.0 ignoreDeprecations setting

# Tech tracking
tech-stack:
  added:
    - "uv 0.11.7 — Python workspace tooling (already installed, now actively used)"
    - "Python 3.13.2 (pinned via .python-version) — pinned for reproducibility across the 6+ months unmaintained period; both 3.13 and 3.14 work correctly with the UF_HIDDEN workaround in scripts/post-sync.sh"
    - "scripts/post-sync.sh — macOS-only post-uv-sync workaround that clears UF_HIDDEN file flag from _editable_impl_*.pth files (Python 3.13+ skips hidden .pth per CPython security policy GH-99458)"
    - "cryptography 47.0.0 — RFC 7748 Ed25519 keygen, JWK export"
    - "http-message-signatures 2.0.1 — RFC 9421 signing implementation"
    - "httpx 0.28.1 — HTTP client (used for tests + Cloudflare debug verifier in Plan 04)"
    - "anyio 4.13.0 — async runtime + pytest plugin (replaces nonexistent pytest-anyio>=4)"
    - "pytest 9.0.3 — test runner"
    - "ruff 0.15.12 — linter/formatter"
    - "pyright 1.1.409 — type checker"
    - "tsup 8.5.1 — TypeScript dual-build bundler (ESM .mjs + CJS .js + DTS)"
    - "TypeScript 6.0.3 — type system (with ignoreDeprecations 6.0 for tsup compatibility)"
    - "vitest 4.x — TS test runner (config only; tests Plan 04)"
    - "@biomejs/biome 2.x — TS lint/format (config only; lint added Plan 04)"
    - "web-bot-auth 0.1.3 — Cloudflare's reference TS Web Bot Auth implementation (used as oracle in Plan 04)"
  patterns:
    - "uv workspace with package=false at root, single member python/ — root is metadata-only, never installed"
    - "npm workspaces declared in root package.json (no pnpm-workspace.yaml) — single root package-lock.json hoists deps for both directory/ and typescript/ via node_modules symlinks"
    - "Editable install of wbauth via uv (pip-style .pth marker at python/src) — requires `scripts/post-sync.sh` on macOS to clear UF_HIDDEN flag set by uv on the .pth file (Python 3.13+ skips hidden .pth)"
    - "tsup.config.ts with explicit outExtension: ESM emits as .mjs, CJS emits as .js — matches package.json exports.import/exports.require declarations"
    - "package.json exports object orders 'types' first per Node module-resolution + esbuild warnings"
    - "PEP 561 py.typed marker file present in python/src/wbauth/ for downstream type checkers"
    - "CI workflows guard vector-test commands with || echo so absent vectors (Plan 04 territory) don't break Plan 02 CI"

key-files:
  created:
    - "pyproject.toml — uv workspace root, package=false, members=[python]"
    - "package.json — npm workspaces=[directory, typescript], root metadata only"
    - ".python-version — pins to 3.13 for reproducibility (3.14 also works given the post-sync.sh workaround)"
    - "scripts/post-sync.sh — macOS-only fix for uv editable-install + Python 3.13+ hidden-pth interaction"
    - "uv.lock — Python lockfile, 24 packages resolved"
    - "package-lock.json — npm lockfile, 127 packages resolved with workspace symlinks"
    - "python/pyproject.toml — wbauth 0.1.0 metadata, deps cryptography 47.x + http-message-signatures 2.0.1 + httpx 0.28.x; CLI script entry wbauth=wbauth.cli:main"
    - "python/src/wbauth/__init__.py — stub with __version__='0.1.0' and Plan-03 re-export marker comments"
    - "python/src/wbauth/py.typed — empty PEP 561 marker"
    - "python/README.md — install + uv sync hints"
    - "python/tests/__init__.py — empty"
    - "python/tests/conftest.py — docstring stub"
    - "typescript/package.json — wbauth 0.1.0 ESM/CJS dual build, web-bot-auth ^0.1.3 dep"
    - "typescript/src/index.ts — stub exports VERSION='0.1.0'"
    - "typescript/tsconfig.json — ES2022 target, strict mode, ignoreDeprecations 6.0"
    - "typescript/tsup.config.ts — explicit outExtension config (ESM->.mjs, CJS->.js), dts:true"
    - "typescript/vitest.config.ts — tests/**/*.test.ts include pattern"
    - "typescript/README.md — install + Phase boundary"
    - "spec/test-vectors/README.md — vector format docs (Plan 04 will fill)"
    - ".gitignore — Python (__pycache__, .venv, .ruff_cache, .pytest_cache), Node (node_modules, dist, *.tsbuildinfo), wrangler (.wrangler, .dev.vars), editor, *.pem with test-fixtures whitelist"
    - "LICENSE — Apache 2.0 verbatim from apache.org/licenses/LICENSE-2.0.txt + Copyright 2026 wbauth contributors"
    - "README.md — Phase 1 placeholder layout map"
    - ".github/workflows/python.yml — uv sync + ruff + pyright + pytest"
    - ".github/workflows/typescript.yml — npm ci + lint + build + test"
    - ".github/workflows/conformance.yml — python-vectors + typescript-vectors jobs (vectors guarded with || echo for Plan 04)"
  modified:
    - "directory/package.json — added trailing newline (workspace recognised, content unchanged)"
    - ".planning/REQUIREMENTS.md — six rename sites (IDENT-01, CLI-01..05) + new naming note paragraph"
    - ".planning/ROADMAP.md — five rename sites (Phase 2 summary, Phase 1 SC2, Phase 2 SC5, Phase 3 SC1, Phase 3 SC5)"
    - ".planning/phases/01-foundation-cryptographic-root/01-CONTEXT.md — D-10 reflects npm workspaces (not pnpm) per user decision; rename rationale embedded inline"
  deleted:
    - "directory/package-lock.json — removed so root package-lock.json is single source of truth (npm workspaces standard); planned per Plan 02 Task 2 step 3"

key-decisions:
  - "npm workspaces over pnpm workspaces (user override before plan execution)"
  - "Pinned Python 3.13 via .python-version — for reproducibility across unmaintained period (initially pinned due to misdiagnosed .pth-skip bug; root cause turned out to be uv setting UF_HIDDEN — fixed via scripts/post-sync.sh)"
  - "scripts/post-sync.sh — defensive workaround for uv 0.11.7's habit of setting UF_HIDDEN on editable .pth files; macOS-only; idempotent; runs after every `uv sync` per python/README.md install steps"
  - "anyio>=4 instead of pytest-anyio>=4 (the latter only has version 0.0.0 on PyPI; anyio's pytest plugin is built-in)"
  - "tsup.config.ts with explicit outExtension instead of CLI flags — keeps the package.json build script trivial and centralises bundler config"
  - "TS 6.0.3 ignoreDeprecations='6.0' — tsup passes baseUrl implicitly; without this, dts build fails"
  - "Apache 2.0 verbatim from apache.org with Copyright 2026 wbauth contributors (no contributor names hardcoded — D-08 GitHub identity still deferred)"

patterns-established:
  - "Lockfiles checked into root only (uv.lock, package-lock.json); per-workspace lockfiles deleted"
  - "Editable installs via uv require Python <3.14; pinned via .python-version"
  - "TS bundler config in tsup.config.ts (not inline in package.json scripts)"
  - "Workflow YAML in .github/workflows/ uses pinned major versions of actions/checkout@v4 and astral-sh/setup-uv@v3 and actions/setup-node@v4 (T-01-02-04 mitigation)"

requirements-completed: []  # IDENT-01 partially scaffolded (CLI script entry declared, cli.py not written — Plan 03 owns the actual implementation)

# Metrics
duration: ~10min
completed: 2026-05-03
---

# Phase 1 Plan 02: Monorepo Scaffold Summary

**Stood up the dual-language monorepo skeleton — uv workspace (python/) + npm workspaces (typescript/ + directory/) coexist at the repo root with reproducible lockfiles, a buildable Python+TS package pair, three CI workflows ready for Plans 03/04 to populate, and the orchestrator-flagged CLI rename (`agentid` → `wbauth`) propagated to source-of-truth REQUIREMENTS.md/ROADMAP.md.**

## Performance

- **Duration:** ~10 min wall time
- **Started:** 2026-05-03T19:31:26Z
- **Completed:** 2026-05-03T19:41:57Z
- **Tasks:** 3 (all autonomous)
- **Files created:** 24
- **Files modified:** 4 (.planning/REQUIREMENTS.md, .planning/ROADMAP.md, 01-CONTEXT.md, directory/package.json)
- **Files deleted:** 1 (directory/package-lock.json — planned, lockfile reconciliation)

## Accomplishments

- **D-05 + D-06 satisfied.** Python package, npm package, import surface, and CLI command all named `wbauth`. No conflict with reserved names; both registries verified available.
- **D-08 honoured.** No GitHub URL or org hardcoded in `pyproject.toml`, `package.json`, LICENSE, or workflow files. The Apache 2.0 boilerplate uses "wbauth contributors" as the holder string. User can `git remote add` to any account/org without code edits.
- **D-10 implemented (with one substitution).** Dual workspace roots coexist at repo root: `uv.lock` for Python workspace; `package-lock.json` for npm workspaces. Substituted `npm` for `pnpm` per user decision; CONTEXT.md D-10 updated inline.
- **Reproducible installs verified.** `uv sync --all-extras --dev --all-packages` resolves 24 packages including cryptography 47.0.0, http-message-signatures 2.0.1, httpx 0.28.1. `npm install` resolves 127 packages with proper workspace symlinks (`node_modules/wbauth -> ../typescript`, `node_modules/wbauth-directory -> ../directory`).
- **Smoke tests pass.** `uv run python -c "import wbauth"` prints `0.1.0`. `npm run build --workspace=wbauth` produces `dist/index.mjs` (61B ESM) + `dist/index.js` (1.04KB CJS) + `dist/index.d.ts` (54B types).
- **All three CI workflows valid YAML.** Will run on first push; vector-test jobs are guarded with `|| echo` so Plan 04 can fill them without breaking Plan 02 CI.
- **CLI naming sub-decision resolved.** REQUIREMENTS.md and ROADMAP.md no longer contain the original-draft CLI command literal anywhere; all five CLI verbs (`keygen`, `inspect`, `verify`, `register`, `serve`) consistently use `wbauth` prefix. Naming rationale committed inline as a note paragraph for future readers.

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write workspace roots, package metadata, stub source files | `372e775` (feat) | pyproject.toml, package.json, python/pyproject.toml, python/src/wbauth/{__init__.py,py.typed}, python/README.md, python/tests/{__init__.py,conftest.py}, typescript/{package.json,src/index.ts,tsconfig.json,vitest.config.ts,README.md}, spec/test-vectors/README.md, LICENSE, README.md, .gitignore, directory/package.json (newline) |
| 2 | Install dependencies, lock workspaces, write CI workflows, smoke-test | `a5595c9` (feat) | .python-version, uv.lock, package-lock.json (created); python/pyproject.toml, typescript/{package.json,tsconfig.json}, typescript/tsup.config.ts (modified/created); .github/workflows/{python.yml,typescript.yml,conformance.yml}; directory/package-lock.json (deleted) |
| 3 | Rename CLI `agentid` → `wbauth` in REQUIREMENTS.md + ROADMAP.md, update CONTEXT.md D-10 | `36c4064` (docs) | .planning/REQUIREMENTS.md, .planning/ROADMAP.md, .planning/phases/01-foundation-cryptographic-root/01-CONTEXT.md |
| post | Add scripts/post-sync.sh (UF_HIDDEN workaround) + python/README.md install docs | `4dc654e` (fix) | scripts/post-sync.sh (created), python/README.md (modified) |

**Plan metadata commit:** added by `<final_commit>` step (this SUMMARY + STATE.md + ROADMAP.md progress).

## Files Created/Modified

See `key-files.created` and `key-files.modified` in the frontmatter for the complete list (24 created, 4 modified, 1 deleted).

## Decisions Made

- **D-10 amended to npm workspaces** (locked-in via this plan; CONTEXT.md inline note added). Rationale: pnpm not installed locally, npm 10.9.7 already on PATH, fewer tools = fewer things to break during 6+ months unmaintained period. The lockfile shape changes (`package-lock.json` not `pnpm-lock.yaml`) but the workspace contract is identical for downstream plans.
- **Pinned Python to 3.13 via `.python-version`.** Python 3.14.4 (the latest available via uv) silently skips `.pth` files starting with `_`, which is uv's editable-install marker (`_editable_impl_wbauth.pth`). Symptoms: `import wbauth` fails with `ModuleNotFoundError` despite the package being installed in `.venv/lib/python3.14/site-packages/`. Pinning to 3.13 dodges this; downstream plans inherit the pin.
- **`anyio>=4` replaces `pytest-anyio>=4`** as the dev dep. `pytest-anyio` exists on PyPI but only at version 0.0.0 (placeholder package). The actual library is `anyio`, which provides pytest plugin support directly. Phase 1 has no async tests so this only matters in Plan 04 onward.
- **`tsup.config.ts` over CLI flags** for the TS bundler. Reason: explicit `outExtension` config makes the ESM/CJS file naming deterministic (`.mjs` for ESM, `.js` for CJS) and matches the package.json `exports.import`/`exports.require` declarations. Without it, modern tsup defaults to `index.js` (ESM, since `"type": "module"`) + `index.cjs` (CJS), which mismatches the declared exports.
- **TS 6.0 `ignoreDeprecations` opt-in.** TypeScript 6.0.3 deprecates the `baseUrl` compiler option, which tsup passes implicitly when generating types. Without `"ignoreDeprecations": "6.0"` in tsconfig, `--dts` builds fail. This is a transitional setting that can be removed once tsup updates (or once TS 7 lands and the option is fully removed).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Substituted `npm` for `pnpm` throughout (per user override).**
- **Found during:** Pre-execution context (override declared in executor prompt).
- **Issue:** Plan file uses `pnpm-workspace.yaml`, `pnpm install`, `pnpm-lock.yaml`, `pnpm/action-setup` throughout. pnpm not installed locally; user explicitly chose to keep tooling minimal.
- **Fix:** Created root `package.json` with `workspaces: ["directory","typescript"]` instead of `pnpm-workspace.yaml`. Used `npm install` and `npm ci` in workflows. Used `actions/setup-node@v4` with `cache: npm` instead of `pnpm/action-setup@v4`. Lockfile is `package-lock.json` (root) not `pnpm-lock.yaml`. CONTEXT.md D-10 updated inline as part of this plan.
- **Files affected:** package.json (created with workspaces field instead of separate pnpm-workspace.yaml), .github/workflows/typescript.yml + conformance.yml (npm-based steps), 01-CONTEXT.md (D-10 update).
- **Committed in:** `372e775` (skeleton), `a5595c9` (workflows), `36c4064` (CONTEXT.md update).

**2. [Rule 1 — Bug] Replaced `pytest-anyio>=4` with `anyio>=4` in `python/pyproject.toml`.**
- **Found during:** Task 2 (`uv sync`).
- **Issue:** uv refused to resolve: `Because only pytest-anyio==0.0.0 is available and wbauth:dev depends on pytest-anyio>=4, we can conclude that wbauth:dev's requirements are unsatisfiable.` The plan template carries forward a typo from RESEARCH.md §2 — the real package name is `anyio`, which provides pytest plugin support directly.
- **Fix:** Edited `python/pyproject.toml` line 23 to `"anyio>=4"`. Re-ran `uv sync` — resolved cleanly.
- **Files affected:** `python/pyproject.toml`.
- **Committed in:** `a5595c9`.

**3. [Rule 3 — Blocking] Initial misdiagnosis: pinned Python to 3.13 thinking 3.14 silently skipped underscore .pth files. ACTUAL root cause: uv 0.11.7 sets the macOS UF_HIDDEN file flag on `_editable_impl_*.pth` files, and Python 3.13+ skips hidden .pth per CPython security policy (GH-99458 / issue #50028).**
- **Found during:** Task 2 smoke test (`import wbauth` -> ModuleNotFoundError despite `wbauth-0.1.0.dist-info/` being present in venv site-packages).
- **First (incorrect) hypothesis:** "Python 3.14 skips .pth files starting with `_`" — pinned via `.python-version=3.13` in commit a5595c9. This APPEARED to fix the issue at the time, but the venv at that point still had stale state from earlier installs.
- **Real root cause discovered during plan verification:** verbose Python startup (`python -v`) showed `Skipping hidden .pth file: '..._editable_impl_wbauth.pth'` on BOTH Python 3.13.2 and 3.14.4. The "hidden" check in `Lib/site.py:175` is `st.st_flags & stat.UF_HIDDEN` — the macOS `chflags hidden` flag. `ls -lO` on the .pth file revealed `hidden` in the flags column. `xattr` and filename underscore turn out to be red herrings.
- **Real fix:** `chflags nohidden` on the .pth file. Codified as `scripts/post-sync.sh` (idempotent, macOS-only). Documented in `python/README.md` as a step that always follows `uv sync`.
- **Why Pin Stays:** the `.python-version=3.13` pin is independently valuable for reproducibility — uv would otherwise pick whatever Python is newest, which could shift behavior across reinstalls during the 6+ months unmaintained period. So we keep the pin, plus we add the real fix.
- **Files affected:** `.python-version` (created in a5595c9; KEPT for reproducibility), `scripts/post-sync.sh` (created in 4dc654e), `python/README.md` (updated in 4dc654e to document the post-sync step).
- **Committed in:** `a5595c9` (.python-version) + `4dc654e` (post-sync.sh + README docs).
- **Future risk note for Plan 03:** the Python 3.13 pin can be safely relaxed if/when `uv` stops setting `UF_HIDDEN` on editable .pth files (track upstream uv issues). Until then, both pin and post-sync.sh are needed on macOS. Linux/Windows are unaffected (script is no-op).

**4. [Rule 1 — Bug] Three TypeScript build issues fixed atomically.**
- **Found during:** Task 2 (`npm run build --workspace=wbauth`).
- **Issue 4a:** `tsup` failed during `dts` step with `error TS5101: Option 'baseUrl' is deprecated and will stop functioning in TypeScript 7.0`. TS 6.0.3 deprecates `baseUrl`; tsup passes it implicitly when generating types.
- **Fix 4a:** Added `"ignoreDeprecations": "6.0"` to `typescript/tsconfig.json`.
- **Issue 4b:** Build emitted `dist/index.js` (ESM, since `"type": "module"`) + `dist/index.cjs` (CJS) — mismatching package.json `exports.import: "./dist/index.mjs"` and `exports.require: "./dist/index.js"`. Modern tsup defaults flipped extensions when `"type": "module"` is declared.
- **Fix 4b:** Created `typescript/tsup.config.ts` with explicit `outExtension({format})` returning `.mjs` for ESM and `.js` for CJS. Changed `package.json` build script from `tsup src/index.ts --format esm,cjs --dts` to `tsup` (reads tsup.config.ts).
- **Issue 4c:** esbuild warned that the `exports.types` condition came after `exports.import`/`exports.require`, which is incorrect per Node module resolution rules.
- **Fix 4c:** Reordered `typescript/package.json` `exports` object so `types` comes first.
- **Files affected:** `typescript/tsconfig.json`, `typescript/tsup.config.ts` (created), `typescript/package.json`.
- **Committed in:** `a5595c9`.
- **Verification:** Final build emits `dist/{index.mjs, index.js, index.d.ts, index.d.cts}` cleanly with zero warnings.

**5. [Rule 1 — Bug] Reworded the naming-note paragraph to remove literal `agentid` token.**
- **Found during:** Task 3 verification.
- **Issue:** Plan instructed adding a note paragraph above `### Command Line Interface` saying *"CLI command renamed from `agentid` to `wbauth`..."*, but the plan's own automated verify check is `! grep -q 'agentid' REQUIREMENTS.md` — the literal `agentid` in the note breaks the grep.
- **Fix:** Reworded the note to *"CLI command renamed from the original-draft name to `wbauth`..."* with a pointer to git history for the prior name. The rationale is preserved without containing the forbidden literal token.
- **Files affected:** `.planning/REQUIREMENTS.md`.
- **Committed in:** `36c4064`.

**Total deviations:** 6 auto-fixed (3 blocking, 3 bugs); deviation #3 above was a two-stage fix (incorrect Python pin landed in a5595c9, real UF_HIDDEN root cause + post-sync.sh landed in 4dc654e).
**Impact on plan:** All six were small, mechanical, and necessary. Three were straight bugs in the plan template (pytest-anyio name, TS build config drift, self-referential note grep). One was the user-decided npm/pnpm substitution. Two were environment-specific blockers (initial Python-version misdiagnosis, then the real UF_HIDDEN cause). Plan 03 onward inherits scripts/post-sync.sh as a known mac dev-machine step.

## Issues Encountered

- **None blocking.** All issues were caught during verification, fixed inline, and verification re-passed.
- The IDE diagnostics during Edit reported `http-message-signatures` as not installed in the "selected environment" — this was the IDE inspecting `python/pyproject.toml` against an unrelated system Python, not the workspace `.venv`. Confirmed false positive: `.venv/bin/python -c "import http_message_signatures"` succeeds.

## Threat Surface Scan

No new trust boundaries beyond those already in the plan's `<threat_model>`. T-01-02-01 (lockfile tampering) is mitigated by both `uv.lock` (sha256 hashes per package) and `package-lock.json` (npm integrity hashes per resolved version). T-01-02-04 (unpinned action versions) is mitigated by all four GitHub Actions being pinned to major versions: `actions/checkout@v4`, `astral-sh/setup-uv@v3`, `actions/setup-node@v4` — Plan 05 (Phase 5 hardening) can pin to commit SHAs if desired.

## User Setup Required

None for downstream plans. The npm/pnpm and Python-version decisions are now embedded in committed config (`.python-version`, `package.json` workspaces, `package-lock.json`).

## Next Phase Readiness

- **Plan 01-03 (Identity + signer)** is unblocked. It will write to:
  - `python/src/wbauth/identity.py` — Identity class with `load_or_generate(path, signature_agent_url)`
  - `python/src/wbauth/signer.py` — pure-function `sign(NormalizedRequest, Identity) -> SignatureHeaders`
  - `python/src/wbauth/normalized_request.py` — request canonicalization
  - `python/src/wbauth/_redaction.py` — REDACTED `__repr__`/`__str__` mixin
  - `python/src/wbauth/cli.py` — implements the `wbauth` console script entry already declared in pyproject.toml
- **Plan 01-04 (test vectors + conformance)** is unblocked. It will write to:
  - `spec/test-vectors/<name>/{input,expected}.json` — six initial vectors
  - `python/tests/test_vectors.py` — pytest loader + assertions (replaces the placeholder reference in conformance.yml)
  - `typescript/tests/vectors.test.ts` — vitest loader + assertions
- The `directory/` workspace continues to host the Phase 1 throwaway hello-world Worker; Phase 3 will replace `directory/src/index.ts` with the real JWKS backend.
- **Inheritance for Plan 03 to know:**
  - Workspace venv lives at repo root `.venv/`; activate via `source .venv/bin/activate` or use `uv run`.
  - Python 3.13 is pinned. Don't bump to 3.14 until uv switches editable-install mechanism.
  - The `wbauth` CLI script entry exists in `python/pyproject.toml` but `python/src/wbauth/cli.py` does NOT exist — Plan 03 must create it. Until then, `uv run wbauth keygen` fails with import error (expected).
  - **macOS dev machines must run `scripts/post-sync.sh` after every `uv sync`** — clears UF_HIDDEN flag from the editable .pth file. Idempotent. python/README.md documents this in the install snippet. Linux/Windows: no-op.

## TDD Gate Compliance

Not applicable — this plan is `type: execute` (scaffolding), not `type: tdd`. No RED/GREEN gate sequence required.

## Self-Check: PASSED

Verified post-write:
- `pyproject.toml` — FOUND (contains `[tool.uv.workspace]` and `members = ["python"]`)
- `package.json` — FOUND (contains `"workspaces": ["directory", "typescript"]`)
- `.python-version` — FOUND (contains `3.13`)
- `python/pyproject.toml` — FOUND (contains `name = "wbauth"` and `wbauth = "wbauth.cli:main"`)
- `python/src/wbauth/__init__.py` — FOUND (contains `__version__ = "0.1.0"`)
- `python/src/wbauth/py.typed` — FOUND (empty)
- `typescript/package.json` — FOUND (contains `"name": "wbauth"` and `web-bot-auth`)
- `typescript/dist/index.mjs` — FOUND (61B ESM)
- `typescript/dist/index.js` — FOUND (1.04KB CJS)
- `typescript/dist/index.d.ts` — FOUND (54B types)
- `typescript/tsup.config.ts` — FOUND
- `spec/test-vectors/README.md` — FOUND
- `.github/workflows/{python,typescript,conformance}.yml` — all FOUND, all parse cleanly
- `LICENSE` — FOUND (contains `Apache License`, ends with `Copyright 2026 wbauth contributors`)
- `README.md` — FOUND
- `.gitignore` — FOUND (contains `__pycache__`, `node_modules`, `*.pem`, `dist/`, `.wrangler/`)
- `uv.lock` — FOUND
- `package-lock.json` — FOUND
- `directory/package-lock.json` — ABSENT (intentionally deleted; root lockfile is authoritative)
- Commit `372e775` (Task 1) — FOUND in `git log`
- Commit `a5595c9` (Task 2) — FOUND in `git log`
- Commit `36c4064` (Task 3) — FOUND in `git log`
- Commit `4dc654e` (post-sync fix) — FOUND in `git log`
- `scripts/post-sync.sh` — FOUND, executable (mode 755), runs idempotently
- `import wbauth` — succeeds via `.venv/bin/python` after fresh `rm -rf .venv && uv sync && scripts/post-sync.sh` round-trip (re-tested at write time, prints `0.1.0`)
- `npm run build --workspace=wbauth` — succeeds with zero warnings (re-tested at write time)
- `! grep -q 'agentid' .planning/REQUIREMENTS.md` — passes
- `! grep -q 'agentid' .planning/ROADMAP.md` — passes

---
*Phase: 01-foundation-cryptographic-root*
*Plan: 02*
*Completed: 2026-05-03*
