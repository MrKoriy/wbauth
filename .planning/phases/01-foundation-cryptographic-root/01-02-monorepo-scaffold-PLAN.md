---
phase: 01-foundation-cryptographic-root
plan: 02
type: execute
wave: 2
depends_on: [01]
files_modified:
  - pyproject.toml
  - package.json
  - pnpm-workspace.yaml
  - python/pyproject.toml
  - python/src/wbauth/__init__.py
  - python/src/wbauth/py.typed
  - python/README.md
  - python/tests/__init__.py
  - python/tests/conftest.py
  - typescript/package.json
  - typescript/src/index.ts
  - typescript/tsconfig.json
  - typescript/vitest.config.ts
  - typescript/README.md
  - directory/package.json
  - spec/test-vectors/README.md
  - .github/workflows/python.yml
  - .github/workflows/typescript.yml
  - .github/workflows/conformance.yml
  - .gitignore
  - LICENSE
  - README.md
  - .planning/REQUIREMENTS.md
autonomous: true
requirements: [IDENT-01]   # partial — installs the `wbauth` CLI script entry in pyproject.toml; Plan 03 implements the actual cli.py logic

must_haves:
  truths:
    - "A developer can run `uv sync` from the repo root and it installs the python/ workspace member"
    - "A developer can run `pnpm install` from the repo root and it installs the typescript/ and directory/ workspace members"
    - "Running `uv run python -c 'import wbauth'` from the repo root succeeds (wbauth package is importable)"
    - "Running `pnpm --filter wbauth build` produces dist/ output"
    - "Both pyproject.toml lockfile (uv.lock) and pnpm-lock.yaml are committed and reproducible"
    - "GitHub Actions workflow files are syntactically valid (yamllint or actionlint passes)"
    - "REQUIREMENTS.md uses `wbauth` as the CLI command name (not `agentid`) — naming sub-decision per orchestrator brief"
  artifacts:
    - path: pyproject.toml
      provides: "uv workspace root declaration"
      contains: "[tool.uv.workspace]"
    - path: pnpm-workspace.yaml
      provides: "pnpm workspace member list"
      contains: "packages:"
    - path: python/pyproject.toml
      provides: "wbauth Python package metadata"
      contains: "name = \"wbauth\""
    - path: python/src/wbauth/__init__.py
      provides: "wbauth public API surface (initially empty stub re-exports)"
      contains: "__version__"
    - path: typescript/package.json
      provides: "wbauth TypeScript package metadata"
      contains: "\"name\": \"wbauth\""
    - path: spec/test-vectors/README.md
      provides: "Test vector format documentation (Plan 04 will add actual vectors)"
      contains: "input.json"
    - path: .github/workflows/python.yml
      provides: "Python CI: uv sync + pytest + ruff + pyright"
      contains: "astral-sh/setup-uv"
    - path: .github/workflows/typescript.yml
      provides: "TS CI: pnpm install + vitest + biome"
      contains: "pnpm/action-setup"
    - path: .github/workflows/conformance.yml
      provides: "Cross-language conformance CI (skeleton — actual vectors load in Plan 04)"
      contains: "pytest"
    - path: LICENSE
      provides: "Apache 2.0 license per PROJECT.md constraints"
      contains: "Apache License"
  key_links:
    - from: "pyproject.toml (root)"
      to: "python/pyproject.toml"
      via: "[tool.uv.workspace] members = [\"python\"]"
      pattern: "members\\s*=\\s*\\[.*python.*\\]"
    - from: "pnpm-workspace.yaml"
      to: "typescript/ and directory/"
      via: "packages: glob list"
      pattern: "typescript|directory"
    - from: ".github/workflows/python.yml"
      to: "python/ workspace member"
      via: "uv sync runs against root, picks up python/ via [tool.uv.workspace]"
      pattern: "uv sync"
    - from: ".planning/REQUIREMENTS.md"
      to: "wbauth CLI naming (per discuss-phase orchestrator brief)"
      via: "renamed from `agentid` to `wbauth`"
      pattern: "wbauth keygen"
---

<objective>
Erect the dual-language monorepo skeleton that satisfies decisions D-05, D-06, D-07, D-10: a single git repo with `uv` workspace (Python) and `pnpm` workspace (TypeScript + directory) coexisting at the root, package name `wbauth` in both ecosystems, CI workflows for both runtimes plus a cross-language conformance scaffold, and Apache 2.0 license.

Purpose: Plans 03 and 04 cannot start until the workspace skeletons exist (they fill in `python/src/wbauth/identity.py`, `python/src/wbauth/signer.py`, `spec/test-vectors/*`, etc.). This plan creates the package metadata, root configs, CI yaml, and empty stub modules that downstream plans extend. It also resolves the orchestrator-flagged CLI naming sub-decision (`agentid` → `wbauth`) by patching REQUIREMENTS.md.

Output: A repo where `uv sync` succeeds, `pnpm install` succeeds, `uv run python -c 'import wbauth'` succeeds (against an empty stub), `pnpm --filter wbauth build` produces a dist/ from a stub `index.ts`, all three CI workflows are valid YAML, and REQUIREMENTS.md consistently references `wbauth` as the CLI command name.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/01-foundation-cryptographic-root/01-CONTEXT.md
@.planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md
@.planning/phases/01-foundation-cryptographic-root/01-01-HOSTING-RESULT.md
@.planning/REQUIREMENTS.md

<interfaces>
<!-- All canonical file contents from 01-RESEARCH.md §2 "Monorepo Scaffold Recipe". -->
<!-- Executor: copy these verbatim. The "fill-in" parts are noted with TODO comments. -->

Root `pyproject.toml` (NOT a published package — workspace root only):
```toml
[project]
name = "wbauth-monorepo-root"
version = "0.0.0"
requires-python = ">=3.11"
description = "Workspace root — not a published package"

[tool.uv.workspace]
members = ["python"]
# directory/ and typescript/ are pnpm-workspace members, not uv

[tool.uv]
package = false
```

`python/pyproject.toml` (the actual SDK package, per RESEARCH §2 — but with CLI script renamed `wbauth` per orchestrator sub-decision; see Q2 in RESEARCH §"Open Questions"):
```toml
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
windows = ["oschmod>=0.3"]

[project.scripts]
wbauth = "wbauth.cli:main"

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

`pnpm-workspace.yaml`:
```yaml
packages:
  - 'typescript'
  - 'directory'
```

Root `package.json` (workspace metadata only):
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

`typescript/package.json` (the actual TS SDK package — Phase 1 stub):
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

`python/src/wbauth/__init__.py` (Phase 1 stub — Plan 03 fills the re-exports):
```python
"""wbauth: Web Bot Auth (RFC 9421) Python SDK.

Phase 1 (current): identity + signer + JWKS + CLI keygen.
Phase 2: HTTP-client adapters + policy inspector.
"""
__version__ = "0.1.0"

# Plan 03 will add:
# from .identity import Identity, KeyPair
# from .signer import sign, SignatureHeaders
# from .normalized_request import NormalizedRequest
# __all__ = ["Identity", "KeyPair", "sign", "SignatureHeaders", "NormalizedRequest", "__version__"]
```

`typescript/src/index.ts` (Phase 1 stub — Phase 4 fills it):
```typescript
// wbauth: Web Bot Auth (RFC 9421) TypeScript SDK.
// Phase 1: stub — only used by Plan 04's cross-language vector check.
// Phase 4: full SDK (createSignedFetch, applyTo, etc.)
export const VERSION = "0.1.0";
```

`typescript/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "declaration": true,
    "outDir": "dist",
    "lib": ["ES2022"],
    "types": ["node"]
  },
  "include": ["src/**/*", "tests/**/*"]
}
```

`typescript/vitest.config.ts`:
```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
  },
});
```

`spec/test-vectors/README.md` (Plan 04 adds actual vectors):
```markdown
# spec/test-vectors/

Cross-language test vectors for wbauth's RFC 9421 + Web Bot Auth signer.

## Format

Each vector is a directory with two files:

- `input.json` — the inputs (request, identity, signing params)
- `expected.json` — the expected `Signature-Input`, `Signature`, `Signature-Agent` strings + computed `kid`

See `.planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md` §5
for the full schema and the canonical six initial vectors.

## Why byte-equality works

Ed25519 signing is deterministic: given the same private key + message bytes,
the signature is identical every time. With fixed `created`/`expires`/`nonce`
and the publicly-known RFC 9421 Appendix B.1.4 test key, the produced
`Signature-Input` and `Signature` headers are reproducible across:

- Multiple Python runs (pytest)
- Multiple TypeScript runs (vitest)
- Multiple language implementations (the cross-language oracle gate)

## Status

- Plan 02 (this plan): scaffold this README only.
- Plan 04: author the six initial vectors and wire them into pytest + vitest.
```

`.github/workflows/python.yml`:
```yaml
name: Python
on: [push, pull_request]
jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Sync workspace
        run: uv sync --all-extras --dev
      - name: Lint (ruff)
        run: uv run ruff check python/
      - name: Type check (pyright)
        run: uv run pyright python/
      - name: Tests
        run: uv run pytest python/tests/ -v
```

`.github/workflows/typescript.yml`:
```yaml
name: TypeScript
on: [push, pull_request]
jobs:
  typescript:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 10
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - name: Lint (biome)
        run: pnpm -r run lint
      - name: Build
        run: pnpm --filter wbauth build
      - name: Tests
        run: pnpm --filter wbauth test
```

`.github/workflows/conformance.yml` (cross-language; Plan 04 expands the actual vector loops):
```yaml
name: Cross-language Conformance
on: [push, pull_request]
jobs:
  python-vectors:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --all-extras --dev
      - name: Run vector tests (Python)
        run: uv run pytest python/tests/test_vectors.py -v || echo "Plan 04 will add the vectors and tests."
  typescript-vectors:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 10
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - name: Run vector tests (TypeScript)
        run: pnpm --filter wbauth test || echo "Plan 04 will add the vector tests."
```

`.gitignore`:
```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.ruff_cache/
.pyright/

# Node
node_modules/
dist/
*.tsbuildinfo

# Cloudflare wrangler
.wrangler/
.dev.vars

# Editor
.vscode/
.idea/
*.swp
.DS_Store

# Lockfiles to KEEP (do not ignore):
# - uv.lock
# - pnpm-lock.yaml

# Local key files (NEVER commit private keys)
*.pem
!**/test-fixtures/*.pem
```

`LICENSE` (Apache 2.0): use the standard text from https://www.apache.org/licenses/LICENSE-2.0.txt — full canonical content. Copyright line: `Copyright 2026 wbauth contributors`.

`README.md` (root — minimal Phase 1 placeholder; Phase 5 polishes it per HARDEN/DIST requirements):
```markdown
# wbauth

> Web Bot Auth (RFC 9421) for AI agents — signed identity + pre-flight site policy.

**Pre-1.0.** API will lock at the v1.0 tag. Do not depend on internals yet.

## Layout

- `python/` — Python SDK (`pip install wbauth`)
- `typescript/` — TypeScript SDK (`npm install wbauth`)
- `directory/` — TypeScript Cloudflare Worker (zero-billing JWKS directory; Phase 3)
- `spec/test-vectors/` — cross-language test vectors (RFC 9421 + Web Bot Auth)
- `docs/` — Astro Starlight docs site (Phase 5)

## License

Apache 2.0 — see `LICENSE`.
```

`python/README.md`:
```markdown
# wbauth (Python)

```bash
pip install wbauth   # Phase 5 — not yet published

# From source (Phase 1):
uv sync
uv run wbauth keygen
```

See repo root README for the full project description.
```

`typescript/README.md`:
```markdown
# wbauth (TypeScript)

```bash
npm install wbauth   # Phase 5 — not yet published
```

Phase 1: stub package — only used as the cross-language vector check oracle.
Phase 4: full SDK with createSignedFetch + Playwright applyTo.
```

`python/tests/__init__.py`: empty file.

`python/tests/conftest.py` (skeleton — Plan 04 fills the vector fixture):
```python
"""Phase 1 pytest fixtures.

Plan 04 will add the load_vector fixture that reads spec/test-vectors/<name>/input.json.
"""
```

`python/src/wbauth/py.typed`: empty marker file (PEP 561).

REQUIREMENTS.md edits — orchestrator-flagged sub-decision (`agentid` → `wbauth`):
- Replace every CLI command literal `agentid` with `wbauth` in REQUIREMENTS.md.
- Specifically: in IDENT-01, CLI-01, CLI-02, CLI-03, CLI-04, CLI-05.
- Add a one-line note above the CLI section: `> CLI command renamed from "agentid" to "wbauth" in Phase 1 plan 02 per CONTEXT.md D-06 (public surface = wbauth) and naming consistency. The package name and the CLI command are now the same: wbauth.`
- DO NOT change other instances of `agentid` that are not CLI command literals (none expected, but verify with grep before editing).

`directory/package.json` update (Plan 01 created a minimal version; this plan integrates it into the workspace):
- Read existing `directory/package.json` (created in Plan 01 Task 2).
- Add `"private": true` if not present.
- Confirm `"name": "wbauth-directory"`, `"type": "module"`, and the wrangler devDependency are intact.
- The file already exists; this is a non-destructive merge to ensure pnpm workspace recognises it.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write workspace roots, package metadata, and stub source files</name>
  <read_first>
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §2 "Monorepo Scaffold Recipe" (full section, lines covering pyproject.toml, pnpm-workspace.yaml, package.json templates)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §"Recommended Project Structure" tree
    - .planning/phases/01-foundation-cryptographic-root/01-CONTEXT.md D-05, D-06, D-08, D-10 (naming, package surface, GitHub org deferred, monorepo layout)
    - directory/package.json (already created by Plan 01 — read to avoid clobbering)
    - .planning/REQUIREMENTS.md (current state, before the wbauth-rename edits in Task 3)
  </read_first>
  <action>
    Create all workspace metadata, configs, and stub source files from the `<interfaces>` block above. Use the Write tool for each file (verbatim contents from `<interfaces>` — do not reinterpret).

    Files to create at exact paths:

    1. `pyproject.toml` — from `<interfaces>` "Root pyproject.toml" block.
    2. `package.json` — from `<interfaces>` "Root package.json" block. NOTE: do not hardcode any GitHub URL (D-08).
    3. `pnpm-workspace.yaml` — from `<interfaces>` block.
    4. `python/pyproject.toml` — from `<interfaces>`. CLI entry point is `wbauth = "wbauth.cli:main"` (orchestrator sub-decision; deviates from RESEARCH §2 which still showed `agentid`).
    5. `python/src/wbauth/__init__.py` — from `<interfaces>` (stub with `__version__`).
    6. `python/src/wbauth/py.typed` — empty file (PEP 561 marker).
    7. `python/README.md` — from `<interfaces>`.
    8. `python/tests/__init__.py` — empty file.
    9. `python/tests/conftest.py` — from `<interfaces>` (docstring-only stub).
   10. `typescript/package.json` — from `<interfaces>`.
   11. `typescript/src/index.ts` — from `<interfaces>` (stub with `VERSION` const).
   12. `typescript/tsconfig.json` — from `<interfaces>`.
   13. `typescript/vitest.config.ts` — from `<interfaces>`.
   14. `typescript/README.md` — from `<interfaces>`.
   15. `spec/test-vectors/README.md` — from `<interfaces>`.
   16. `.gitignore` — from `<interfaces>`.
   17. `LICENSE` — full Apache 2.0 text (download from https://www.apache.org/licenses/LICENSE-2.0.txt or use the standard canonical text). Copyright line: "Copyright 2026 wbauth contributors".
   18. `README.md` (root) — from `<interfaces>`.

    For `directory/package.json`: read the existing file (created by Plan 01) and add `"private": true` if missing. Do NOT replace other content.

    Do NOT install dependencies in this task — Task 2 handles `uv sync` and `pnpm install`.
  </action>
  <verify>
    <automated>test -f pyproject.toml &amp;&amp; test -f package.json &amp;&amp; test -f pnpm-workspace.yaml &amp;&amp; test -f python/pyproject.toml &amp;&amp; test -f python/src/wbauth/__init__.py &amp;&amp; test -f python/src/wbauth/py.typed &amp;&amp; test -f typescript/package.json &amp;&amp; test -f typescript/src/index.ts &amp;&amp; test -f typescript/tsconfig.json &amp;&amp; test -f spec/test-vectors/README.md &amp;&amp; test -f LICENSE &amp;&amp; test -f README.md &amp;&amp; test -f .gitignore &amp;&amp; grep -q '\[tool\.uv\.workspace\]' pyproject.toml &amp;&amp; grep -q "members = \[\"python\"\]" pyproject.toml &amp;&amp; grep -q 'name = "wbauth"' python/pyproject.toml &amp;&amp; grep -q 'wbauth = "wbauth.cli:main"' python/pyproject.toml &amp;&amp; grep -q '"name": "wbauth"' typescript/package.json &amp;&amp; grep -q 'web-bot-auth' typescript/package.json &amp;&amp; grep -q 'typescript' pnpm-workspace.yaml &amp;&amp; grep -q 'directory' pnpm-workspace.yaml &amp;&amp; grep -q 'Apache License' LICENSE &amp;&amp; grep -q '__version__ = "0.1.0"' python/src/wbauth/__init__.py</automated>
  </verify>
  <acceptance_criteria>
    - All 18 files listed above exist at exactly the specified paths
    - `pyproject.toml` declares `[tool.uv.workspace]` with `members = ["python"]` and `[tool.uv]` with `package = false`
    - `python/pyproject.toml` has `name = "wbauth"`, `requires-python = ">=3.11"`, deps `cryptography>=47,<48`, `http-message-signatures>=2.0.1,<3`, `httpx>=0.28,<0.30`, AND CLI script entry `wbauth = "wbauth.cli:main"` (the renamed-from-agentid name)
    - `pnpm-workspace.yaml` lists exactly two members: `typescript` and `directory`
    - `typescript/package.json` declares `"name": "wbauth"` (same package name as Python — they ship to different registries) AND lists `web-bot-auth` as a runtime dep
    - `python/src/wbauth/__init__.py` defines `__version__ = "0.1.0"` and contains commented Plan 03 re-exports as a hand-off marker
    - `LICENSE` contains Apache 2.0 text (`grep -q "Apache License"` passes)
    - `directory/package.json` retains all content created by Plan 01 (wrangler devDep present)
    - `.gitignore` excludes `__pycache__`, `node_modules`, `*.pem`, `dist/`, `.wrangler/`
  </acceptance_criteria>
  <done>
    Workspace skeleton files committed to disk. Lockfiles and node_modules not yet installed (Task 2 handles that).
  </done>
</task>

<task type="auto">
  <name>Task 2: Install dependencies, lock workspaces, write CI workflows, smoke-test imports</name>
  <read_first>
    - pyproject.toml (just-created root workspace declaration)
    - python/pyproject.toml (just-created Python package metadata)
    - typescript/package.json (just-created TS package metadata)
    - directory/package.json (already-existing wrangler workspace)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §2 "CI Matrix" subsection (the conformance.yml content)
  </read_first>
  <action>
    Install dependencies for both workspaces, commit the lockfiles, write the three GitHub Actions workflow files, and smoke-test that imports/builds work.

    Step-by-step:

    1. Install Python workspace deps (creates `uv.lock` at repo root):
       ```bash
       uv sync --all-extras --dev
       ```
       Expected: creates `.venv/`, installs cryptography 47.x, http-message-signatures 2.0.1, httpx 0.28.x, dev deps. If the installer fails because a dep version is unavailable on PyPI for the current date, log the exact version available and adjust the upper bound in `python/pyproject.toml` (e.g., if cryptography 48 is now out and 47 is yanked, bump `<48` to `<49`); document in the PLAN summary.

    2. Smoke-test Python import:
       ```bash
       uv run python -c "import wbauth; print(wbauth.__version__)"
       ```
       Expected: prints `0.1.0`.

    3. Install TypeScript workspace deps (creates `pnpm-lock.yaml` at repo root, hoists directory/'s wrangler in):
       ```bash
       pnpm install
       ```
       Expected: `node_modules/` at root + `directory/node_modules/` (or hoisted). If `directory/pnpm-lock.yaml` exists from Plan 01 (local install), delete it before `pnpm install` so the workspace lockfile is the source of truth: `rm -f directory/pnpm-lock.yaml`.

    4. Smoke-test TS build:
       ```bash
       pnpm --filter wbauth build
       ```
       Expected: produces `typescript/dist/index.js`, `typescript/dist/index.mjs`, `typescript/dist/index.d.ts`.

    5. Write the three GitHub Actions workflows from `<interfaces>`:
       - `.github/workflows/python.yml`
       - `.github/workflows/typescript.yml`
       - `.github/workflows/conformance.yml`

       Make sure the directories exist first (`mkdir -p .github/workflows`).

    6. Validate the workflow YAML syntax. Use this guard:
       ```bash
       for f in .github/workflows/*.yml; do
         python3 -c "import yaml; yaml.safe_load(open('$f'))" && echo "OK: $f" || (echo "BAD: $f" && exit 1)
       done
       ```

    7. Confirm both lockfiles are present at the repo root:
       ```bash
       test -f uv.lock && test -f pnpm-lock.yaml
       ```

    8. Confirm tsup can produce a build (already done in step 4 — verify dist exists):
       ```bash
       test -f typescript/dist/index.js && test -f typescript/dist/index.d.ts
       ```
  </action>
  <verify>
    <automated>uv run python -c "import wbauth; assert wbauth.__version__ == '0.1.0'" &amp;&amp; test -f uv.lock &amp;&amp; test -f pnpm-lock.yaml &amp;&amp; test -f typescript/dist/index.mjs &amp;&amp; test -f typescript/dist/index.d.ts &amp;&amp; test -f .github/workflows/python.yml &amp;&amp; test -f .github/workflows/typescript.yml &amp;&amp; test -f .github/workflows/conformance.yml &amp;&amp; for f in .github/workflows/*.yml; do python3 -c "import yaml; yaml.safe_load(open('$f'))" || exit 1; done &amp;&amp; grep -q 'astral-sh/setup-uv' .github/workflows/python.yml &amp;&amp; grep -q 'pnpm/action-setup' .github/workflows/typescript.yml</automated>
  </verify>
  <acceptance_criteria>
    - `uv.lock` exists at repo root (proves `uv sync` succeeded against the workspace declaration)
    - `pnpm-lock.yaml` exists at repo root (proves `pnpm install` succeeded against the pnpm workspace)
    - `uv run python -c "import wbauth; assert wbauth.__version__ == '0.1.0'"` exits 0
    - `pnpm --filter wbauth build` produced `typescript/dist/index.mjs` AND `typescript/dist/index.d.ts`
    - `.github/workflows/python.yml`, `typescript.yml`, `conformance.yml` all exist and parse as valid YAML
    - python.yml uses `astral-sh/setup-uv@v3`; typescript.yml uses `pnpm/action-setup@v4`
    - conformance.yml has both `python-vectors` and `typescript-vectors` jobs (Plan 04 fills the actual vector logic)
    - No leftover `directory/pnpm-lock.yaml` (the workspace lockfile at root is the only one)
  </acceptance_criteria>
  <done>
    Both workspaces install reproducibly. Python `import wbauth` works, TS `wbauth` builds. CI workflows are valid YAML and ready for Plan 03/04 to populate.
  </done>
</task>

<task type="auto">
  <name>Task 3: Rename CLI command `agentid` → `wbauth` in REQUIREMENTS.md</name>
  <read_first>
    - .planning/REQUIREMENTS.md (full file — read before editing to confirm scope of `agentid` references)
    - .planning/phases/01-foundation-cryptographic-root/01-CONTEXT.md D-06 (public surface = wbauth)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §"Open Questions" Q2 (CLI naming sub-decision: planner recommends `wbauth`)
  </read_first>
  <action>
    Resolve the orchestrator-flagged CLI naming sub-decision. The original REQUIREMENTS.md text uses `agentid` as the CLI command name (e.g., `agentid keygen`, `agentid inspect <url>`). The locked decision D-06 makes `wbauth` the public package/import surface, and orchestrator brief recommends consistency: CLI command = `wbauth`. The Python `pyproject.toml` script entry was already declared as `wbauth = "wbauth.cli:main"` in Task 1.

    Step-by-step:

    1. First, audit all `agentid` references in REQUIREMENTS.md:
       ```bash
       grep -n "agentid" .planning/REQUIREMENTS.md
       ```
       Expected matches (per the read in `<read_first>`): IDENT-01 line, CLI-01..CLI-05 lines, possibly Phase summary lines.

    2. Edit REQUIREMENTS.md (use Edit tool — DO NOT rewrite the whole file):

       Replace every CLI command literal `agentid` with `wbauth`. Specifically:
       - In IDENT-01: change `(agentid keygen)` to `(wbauth keygen)`
       - In CLI-01: `agentid keygen [--output PATH]` → `wbauth keygen [--output PATH]`
       - In CLI-02: `agentid inspect <url>` → `wbauth inspect <url>`
       - In CLI-03: `agentid verify --domain <domain>` → `wbauth verify --domain <domain>`
       - In CLI-04: `agentid register --directory <url> --identity <path>` → `wbauth register --directory <url> --identity <path>`
       - In CLI-05: `agentid serve [--port N]` → `wbauth serve [--port N]`
       - In ROADMAP-style summary line at top of "Phase 2" section (if present): "agentid CLI core" → "wbauth CLI core"

    3. Add a note paragraph above the "### Command Line Interface" section (insert immediately before the `### Command Line Interface` heading):
       ```markdown
       > **Naming:** CLI command renamed from `agentid` (original draft) to `wbauth` in Phase 1 Plan 02
       > per CONTEXT.md D-06 (public surface = `wbauth`) and consistency with the package name.
       > The package, the import path, and the CLI command are now all `wbauth`.
       ```

    4. Audit ROADMAP.md for the same `agentid` literal in CLI references and apply the same rename if found:
       ```bash
       grep -n "agentid" .planning/ROADMAP.md
       ```
       In Phase 2 description: "agentid CLI core" → "wbauth CLI core" (if present). Do NOT touch any other context.

    5. Verify the rename is complete:
       ```bash
       # No remaining `agentid` literals in either file
       ! grep -n 'agentid' .planning/REQUIREMENTS.md
       ! grep -n 'agentid' .planning/ROADMAP.md
       # The replacement is in place
       grep -q 'wbauth keygen' .planning/REQUIREMENTS.md
       grep -q 'wbauth inspect' .planning/REQUIREMENTS.md
       grep -q 'wbauth verify' .planning/REQUIREMENTS.md
       ```
  </action>
  <verify>
    <automated>! grep -n 'agentid' .planning/REQUIREMENTS.md &amp;&amp; ! grep -n 'agentid' .planning/ROADMAP.md &amp;&amp; grep -q 'wbauth keygen' .planning/REQUIREMENTS.md &amp;&amp; grep -q 'wbauth inspect' .planning/REQUIREMENTS.md &amp;&amp; grep -q 'wbauth verify' .planning/REQUIREMENTS.md &amp;&amp; grep -q 'wbauth register' .planning/REQUIREMENTS.md &amp;&amp; grep -q 'wbauth serve' .planning/REQUIREMENTS.md &amp;&amp; grep -q 'CLI command renamed from' .planning/REQUIREMENTS.md</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c agentid .planning/REQUIREMENTS.md` returns 0 (no `agentid` literals remain)
    - `grep -c agentid .planning/ROADMAP.md` returns 0
    - All five CLI commands now use `wbauth` prefix: `wbauth keygen`, `wbauth inspect`, `wbauth verify`, `wbauth register`, `wbauth serve`
    - A note paragraph mentioning the rename rationale is present (`grep -q "CLI command renamed from"` matches)
    - No other content in REQUIREMENTS.md or ROADMAP.md is changed (preserve all other text exactly)
  </acceptance_criteria>
  <done>
    REQUIREMENTS.md and ROADMAP.md consistently use `wbauth` as the CLI command name. The rename is documented inline so future readers understand the source-of-truth shift.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| dev machine → PyPI / npm registries | Both fetch dependency artifacts over HTTPS; supply-chain integrity relies on registry signature checks (uv + pnpm both verify checksums against lockfiles). |
| dev machine → GitHub Actions runners | Workflow yaml is committed; CI runs in GitHub-hosted ubuntu-latest with isolated runners. |
| repo → public web (after first push) | All files committed are public if the repo is pushed to a public GitHub URL. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-02-01 | Tampering | dependency in transit (PyPI/npm) | mitigate | uv.lock + pnpm-lock.yaml capture content hashes; `uv sync` and `pnpm install --frozen-lockfile` (CI) refuse to install if hashes differ. |
| T-01-02-02 | Tampering | dependency typosquatting (e.g., installing `web-bot-auth` typo) | mitigate | Exact dep names sourced from RESEARCH.md verified-against-registry tables; lockfile pins the resolved name+version. |
| T-01-02-03 | Information Disclosure | accidental commit of `.pem` private key from local development | mitigate | `.gitignore` excludes `*.pem` (with whitelist for `**/test-fixtures/*.pem` for the publicly-known RFC 9421 test key). Plan 03 reinforces this in `Identity` class. |
| T-01-02-04 | Tampering | unpinned GitHub Actions versions allowing supply-chain attack | mitigate | All workflow uses pinned major versions: `actions/checkout@v4`, `astral-sh/setup-uv@v3`, `pnpm/action-setup@v4`, `actions/setup-node@v4`. Plan 05 (Phase 5 hardening) can pin to commit SHAs if desired. |
| T-01-02-05 | Repudiation | maintainer claims they didn't approve the CLI rename | accept | Rename rationale is committed to REQUIREMENTS.md inline (`> Naming: CLI command renamed from agentid...`). Git history records who/when. |
| T-01-02-06 | Denial of Service | CI workflow consumed all GitHub Actions free minutes | accept | Three workflows × small jobs = trivial Actions usage on a public repo (free for public). Phase 5 hardening adds Dependabot which adds more PRs but stays under cap. |
</threat_model>

<verification>
1. `uv sync --all-extras --dev` succeeds; `uv.lock` is committed.
2. `pnpm install` succeeds; `pnpm-lock.yaml` is committed.
3. `uv run python -c "import wbauth"` succeeds and `wbauth.__version__ == "0.1.0"`.
4. `pnpm --filter wbauth build` produces `typescript/dist/{index.js,index.mjs,index.d.ts}`.
5. All three workflow YAML files parse cleanly.
6. REQUIREMENTS.md and ROADMAP.md contain zero `agentid` references; CLI commands all use `wbauth`.
</verification>

<success_criteria>
- Monorepo skeleton exists per D-10: `python/`, `typescript/`, `directory/` (extended from Plan 01), `spec/test-vectors/` (placeholder README), `docs/` (omitted — Phase 5 owns it), `.github/workflows/` (three files).
- D-05 + D-06 satisfied: package and CLI both named `wbauth`.
- D-08 honoured: no GitHub org name hardcoded anywhere (verified by absence of any github.com URLs in pyproject.toml or package.json).
- D-10 honoured: dual workspace roots (uv + pnpm) coexist at root.
- CLI naming sub-decision (agentid → wbauth) is propagated to source-of-truth REQUIREMENTS.md and ROADMAP.md with rationale note inline.
- Plan 03 and Plan 04 can write to `python/src/wbauth/*.py` and `spec/test-vectors/*` respectively without further scaffold work.
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundation-cryptographic-root/01-02-SUMMARY.md` summarizing:
- The created file tree (with paths)
- Confirmed dependency versions (cryptography, http-message-signatures, httpx, web-bot-auth, wrangler from Plan 01)
- The CLI naming resolution: REQUIREMENTS.md/ROADMAP.md now use `wbauth`; package script entry is `wbauth = "wbauth.cli:main"`
- A note that Plan 03 will populate `python/src/wbauth/{identity,signer,normalized_request,_redaction,cli}.py` and Plan 04 will populate `spec/test-vectors/`
</output>
