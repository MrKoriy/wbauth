---
phase: 02-python-adapters-policy-inspector
plan: 01
subsystem: adapters
tags: [httpx, requests, playwright, web-bot-auth, rfc-9421, ed25519, content-digest]

# Dependency graph
requires:
  - phase: 01-foundation-cryptographic-root
    provides: "wbauth.sign(), Identity, NormalizedRequest, KeyPair, SignatureHeaders, byte-equal test vectors"
provides:
  - "wbauth.adapters.WebBotAuth — httpx.Auth subclass (sync + async) with Identity-driven UA injection and auto Content-Digest"
  - "wbauth.adapters.WebBotAuthAdapter — requests.auth.AuthBase subclass with same UA + Content-Digest semantics"
  - "wbauth.adapters.attach_signing — Playwright async helper that registers page.route('**/*', handler) for browser-driver request signing"
  - "wbauth.adapters._utils.ensure_content_digest — internal helper that satisfies the Phase-1 signer's content-digest precondition for POST/PUT/PATCH bodies (RFC 9530 sha-256)"
  - "Phase-2 runtime/dev deps frontloaded in pyproject.toml (cachetools, playwright, protego, requests; pytest-httpx + responses)"
  - "Public re-exports at wbauth root: WebBotAuth, WebBotAuthAdapter, attach_signing"
  - "Byte-equal vector conformance via test_adapter_conformance.py for both httpx + requests adapters against spec/test-vectors/01-basic-get/expected.json"
affects: [02-02-policy-inspector, 02-03-cli, 04-typescript-sdk-and-framework-integrations, 05-pre-army-hardening-docs-and-launch]

# Tech tracking
tech-stack:
  added: [requests>=2.32, playwright>=1.59, protego>=0.6, cachetools>=7, pytest-httpx, responses]
  patterns:
    - "Stateless adapter holding only `self._identity`, signing fresh per request"
    - "Adapters import from wbauth.signer / wbauth.normalized_request directly (NOT from `wbauth`) to avoid circular import via the package-root re-exports"
    - "UA injection is opt-in via `identity.user_agent` AND only fires when the request truly has no UA at signing time"
    - "Content-Digest auto-computed in adapter glue; signer's POST/PUT/PATCH content-digest covered-component requirement is fulfilled by adapters, not by user code"
    - "Vector conformance tests monkeypatch the adapter-module-local `sign` symbol to inject vector-fixed created/nonce — preserves production defaults while exercising the adapter code path"

key-files:
  created:
    - "python/src/wbauth/adapters/__init__.py — re-exports WebBotAuth, WebBotAuthAdapter, attach_signing"
    - "python/src/wbauth/adapters/httpx_auth.py — 47 LOC, class WebBotAuth(httpx.Auth)"
    - "python/src/wbauth/adapters/requests_adapter.py — 43 LOC, class WebBotAuthAdapter(AuthBase)"
    - "python/src/wbauth/adapters/playwright.py — 45 LOC, async def attach_signing(page, identity)"
    - "python/src/wbauth/adapters/_utils.py — internal ensure_content_digest() helper"
    - "python/tests/test_adapters_package.py — package skeleton + dep import smoke"
    - "python/tests/test_adapters_httpx.py — 6 tests (sync + async + statelessness + UA pos/neg + POST body)"
    - "python/tests/test_adapters_requests.py — 5 tests (mirror of httpx via responses lib)"
    - "python/tests/test_adapters_playwright.py — 6 tests via AsyncMock route/request, no browser launch"
    - "python/tests/test_adapter_conformance.py — byte-equal vs vector 01 for both httpx + requests adapters"
  modified:
    - "python/pyproject.toml — added 4 runtime deps + 2 dev deps for Phase 2"
    - "python/src/wbauth/__init__.py — re-exports WebBotAuth, WebBotAuthAdapter, attach_signing"
    - "uv.lock — locked Phase-2 dep tree"

key-decisions:
  - "Adapters import wbauth.signer.sign and wbauth.normalized_request.NormalizedRequest directly, NOT via the package root, to avoid a circular import the moment wbauth/__init__.py started re-exporting adapter symbols"
  - "Content-Digest auto-computation lives in wbauth.adapters._utils.ensure_content_digest (not in wbauth.signer) — keeps Phase 1 signer code unchanged; signer's POST/body precondition is fulfilled by the adapter glue per its existing TODO marker"
  - "UA injection guard uses case-insensitive header check (e.g., httpx normalises to lowercase, requests preserves case) — works uniformly across all three client surfaces"
  - "Vector conformance test patches the adapter-module-local `sign` reference (not the global wbauth.signer.sign) so the adapter's import binding is exercised; this confirms adapters wire to the real signer rather than re-implementing it"
  - "Playwright tests use unittest.mock.AsyncMock — no browser launch, no `playwright install` required for CI; live-browser verification deferred to Phase 4 demos per D-13"

patterns-established:
  - "Adapter authoring: ≤50 LOC; compose Phase-1 sign() + ensure_content_digest(); attach 3 Sig* headers; conditional UA injection; return adapter-native request unchanged structurally"
  - "Vector conformance via monkeypatch of `<adapter_module>.sign`: vector-freeze created/nonce while preserving the adapter's production code path"
  - "Browser-free Playwright unit tests via AsyncMock(Route + Request) + capture-via-fake-route(): sufficient to assert handler registration pattern, header attachment, statelessness, and UA semantics"

requirements-completed: [ADAPT-01, ADAPT-02, ADAPT-03, ADAPT-06, ADAPT-07]

# Metrics
duration: ~30 min
completed: 2026-05-03
---

# Phase 2 Plan 01: Python Adapters Summary

**Three drop-in HTTP-client adapters (httpx Auth, requests AuthBase, Playwright route helper) wrapping Phase-1 `wbauth.sign()` in ≤50 LOC each, with byte-equal test-vector conformance and stateless per-request signing.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-05-03 (Plan 02-01 execution)
- **Completed:** 2026-05-03
- **Tasks:** 3 (all TDD: RED → GREEN per task)
- **Test files created:** 4 (+ 1 package smoke); 19 plan tests + 4 skeleton tests = 23 new tests, 78/78 total passing including Phase-1 regression

## Accomplishments

- `httpx.Client(auth=WebBotAuth(identity)).get(url)` works end-to-end and produces byte-equal Signature/Signature-Input/Signature-Agent vs `spec/test-vectors/01-basic-get/expected.json`.
- `requests.get(url, auth=WebBotAuthAdapter(identity))` produces the same byte-equal headers via the `responses` library mock.
- `await attach_signing(page, identity)` registers a Playwright `page.route("**/*", handler)` that signs every outgoing request via `wbauth.sign()` and continues with signed headers; verified through AsyncMock-based unit tests with no browser launch.
- Auto Content-Digest (RFC 9530 sha-256) computed for POST/PUT/PATCH bodies, satisfying the Phase-1 signer's covered-components precondition without user intervention.
- Identity.user_agent UA injection (open question #4) implemented across all three adapters with both positive and negative branches tested.
- Each adapter file ≤50 LOC of glue (47 / 43 / 45). Complexity stays in `wbauth.sign()` per ADAPT-07.

## Task Commits

1. **Task 1: Phase-2 deps + adapters package skeleton** — RED `b2ee4f5` (test), GREEN `45a2739` (feat)
2. **Task 2: httpx + requests adapters with byte-equal vector conformance** — RED `0fe3874` (test), GREEN `67e8058` (feat)
3. **Task 3: Playwright attach_signing helper with route-mode tests** — RED `c7449dc` (test), GREEN `663ac87` (feat)

## Files Created/Modified

### Created
- `python/src/wbauth/adapters/__init__.py` — re-exports the three public symbols
- `python/src/wbauth/adapters/httpx_auth.py` (47 LOC) — `class WebBotAuth(httpx.Auth)` with `requires_request_body=True`, sync + async flows, UA injection, Content-Digest
- `python/src/wbauth/adapters/requests_adapter.py` (43 LOC) — `class WebBotAuthAdapter(AuthBase)` with `__call__`, UA injection, Content-Digest
- `python/src/wbauth/adapters/playwright.py` (45 LOC) — `async def attach_signing(page, identity)` registering `page.route("**/*", handler)`, with PITFALL 6 + PITFALL 7 docstrings
- `python/src/wbauth/adapters/_utils.py` — internal `ensure_content_digest(method, headers, body)` helper (RFC 9530 sha-256)
- `python/tests/test_adapters_package.py` — 4 tests: subpackage re-exports, top-level re-exports, runtime dep imports, dev dep imports
- `python/tests/test_adapters_httpx.py` — 6 tests covering sync + async smoke, statelessness (different nonces), UA positive + negative, POST + body
- `python/tests/test_adapters_requests.py` — 5 tests mirroring httpx via the `responses` library
- `python/tests/test_adapters_playwright.py` — 6 tests using `unittest.mock.AsyncMock` for Route + Request + Page (no browser)
- `python/tests/test_adapter_conformance.py` — 2 byte-equal vector tests (httpx + requests against `spec/test-vectors/01-basic-get/expected.json`)
- `.planning/phases/02-python-adapters-policy-inspector/02-01-SUMMARY.md` — this summary

### Modified
- `python/pyproject.toml` — added runtime deps `cachetools>=7,<8`, `playwright>=1.59,<2`, `protego>=0.6,<1`, `requests>=2.32,<3`; dev deps `pytest-httpx`, `responses`
- `python/src/wbauth/__init__.py` — re-exported `WebBotAuth`, `WebBotAuthAdapter`, `attach_signing` at package root
- `uv.lock` — Phase-2 dep tree locked (greenlet, playwright, protego, pyee, pytest-httpx, pyyaml, requests, responses, urllib3 added)

## Sample Usage (one-liner per adapter)

```python
# httpx (sync OR async — same WebBotAuth instance)
import httpx
from wbauth import Identity, WebBotAuth
identity = Identity.load_or_generate(signature_agent_url="https://example.com/agent.json")
httpx.Client(auth=WebBotAuth(identity)).get("https://api.example.com/data")

# requests
import requests
from wbauth import Identity, WebBotAuthAdapter
requests.get("https://api.example.com/data", auth=WebBotAuthAdapter(identity))

# Playwright (async)
from playwright.async_api import async_playwright
from wbauth import Identity, attach_signing
async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await browser.new_page()
    await attach_signing(page, identity)        # MUST be before goto (Pitfall 6)
    await page.goto("https://example.com/")
```

## Byte-Equal Conformance Evidence

```
$ uv run pytest tests/test_adapter_conformance.py -v
tests/test_adapter_conformance.py::test_httpx_matches_vector_01    PASSED
tests/test_adapter_conformance.py::test_requests_matches_vector_01 PASSED
2 passed in 0.10s
```

Each test rebuilds an `Identity` from the vector's JWK, monkeypatches the adapter-local `sign` symbol with the vector's fixed `created`/`nonce`/`label`/`expires_after_seconds`, runs a request through the adapter (httpx via `MockTransport`, requests via `responses`), captures the outgoing request, and asserts:

- `sent.headers["Signature"] == expected["signature_value"]`
- `sent.headers["Signature-Input"] == expected["signature_input_value"]`
- `sent.headers["Signature-Agent"] == expected["signature_agent_value"]`

Both assertions hold for both adapters → adapters are byte-equal with the Phase-1 signer baseline (ADAPT-06 satisfied).

## Decisions Made

- **Direct submodule imports in adapters.** `from wbauth import sign, NormalizedRequest` causes a circular import once `wbauth/__init__.py` re-exports adapter symbols. Adapters now use `from wbauth.signer import sign` and `from wbauth.normalized_request import NormalizedRequest` — same effect, no cycle. Conformance tests still patch via the adapter-module-local `sign` reference.
- **Content-Digest in adapter glue, not in signer.** Phase-1 signer's TODO ("the caller is responsible for setting the Content-Digest header BEFORE calling sign() — Phase 2 will add a helper") is fulfilled by `wbauth.adapters._utils.ensure_content_digest`. Phase 1 code stays untouched; adapters become the canonical "user-facing entry point that does the right thing".
- **UA test for httpx required a build_request + del headers["User-Agent"] dance** because httpx 0.28 rejects `None` header values and auto-injects `python-httpx/X.Y` on every request. The adapter's "absent" branch is correct; the test simply has to construct a truly UA-less request.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Circular import between `wbauth/__init__.py` and `wbauth.adapters.httpx_auth`**

- **Found during:** Task 2 (httpx adapter implementation, GREEN run)
- **Issue:** Plan reference code does `from wbauth import sign, NormalizedRequest`. After Task 1 added `from .adapters import ...` to `wbauth/__init__.py`, importing `wbauth` triggered the adapter import, which tried to re-import `wbauth` for `sign` — circular.
- **Fix:** Switched all three adapters to `from wbauth.signer import sign` + `from wbauth.normalized_request import NormalizedRequest`. The adapter-local `sign` symbol still resolves to the same callable; conformance test monkeypatch via `wbauth.adapters.<module>.sign` continues to work.
- **Files modified:** `httpx_auth.py`, `requests_adapter.py`, `playwright.py`
- **Verification:** Full test suite passes; `from wbauth import WebBotAuth, WebBotAuthAdapter, attach_signing` succeeds.
- **Committed in:** `67e8058` (Task 2 GREEN), `663ac87` (Task 3 GREEN)

**2. [Rule 2 — Missing Critical] Content-Digest header was missing for POST/body requests**

- **Found during:** Task 2 (POST + body test, GREEN run)
- **Issue:** Phase-1 signer auto-includes `content-digest` in covered components when `body` is present and method is POST/PUT/PATCH, but expects the caller to have set the `Content-Digest` header. Without it, `http_message_signatures` raises `Covered header field "content-digest" not found in the message`. Without auto-population in the adapter, every POST sign call from a user would crash.
- **Fix:** Added `wbauth.adapters._utils.ensure_content_digest(method, headers, body)` (RFC 9530 sha-256, structured-fields form `sha-256=:<base64>:`). Wired into all three adapters; mutates the headers dict before signing AND copies the new header onto the adapter-native request so the wire-format request carries it.
- **Files modified:** `_utils.py` (new), `httpx_auth.py`, `requests_adapter.py`, `playwright.py`
- **Verification:** `test_post_with_body_signs_correctly` passes for all three adapters; the digest format matches `spec/test-vectors/02-post-with-content-digest/expected.json` reference shape.
- **Committed in:** `67e8058` (Task 2 GREEN), `663ac87` (Task 3 GREEN — Playwright)

**3. [Rule 1 — Bug] httpx UA-injection test failed because httpx 0.28 auto-injects default UA**

- **Found during:** Task 2 (UA injection test, GREEN run)
- **Issue:** Initial test pattern `client.get(url)` always sees `User-Agent: python-httpx/0.28.1` injected by httpx itself, so the adapter's "absent" branch never fires. Setting `headers={"User-Agent": None}` raises `TypeError` in httpx 0.28+.
- **Fix:** Test now builds the request with `client.build_request(...)`, deletes `req.headers["User-Agent"]`, then `client.send(req)`. Adapter behavior unchanged; the test simply constructs the truly-UA-less scenario it intended to test.
- **Files modified:** `python/tests/test_adapters_httpx.py`
- **Verification:** `test_ua_injection_when_absent` passes; `test_ua_preserved_when_caller_set_one` still passes (negative branch unchanged).
- **Committed in:** `67e8058` (Task 2 GREEN)

---

**Total deviations:** 3 auto-fixed (1 blocking, 1 missing critical, 1 bug)
**Impact on plan:** All three are correctness/integration fixes, not scope creep. The Content-Digest helper closes a Phase-1 TODO; the import refactor is forced by the package-root re-export pattern; the UA test refinement reflects httpx 0.28's actual behavior. Adapter LOC budget remained ≤50 throughout (47 / 43 / 45).

## Issues Encountered

- **macOS UF_HIDDEN flag** (L-05) requires re-running `bash scripts/post-sync.sh` after every `uv sync` for `wbauth` to remain importable. Ran twice during this plan. Phase-1 known-issue, no new mitigation needed.

## TDD Gate Compliance

All 3 tasks followed RED → GREEN gate sequence:

| Task | RED commit (test) | GREEN commit (feat) |
|------|-------------------|---------------------|
| 1    | `b2ee4f5`         | `45a2739`           |
| 2    | `0fe3874`         | `67e8058`           |
| 3    | `c7449dc`         | `663ac87`           |

No REFACTOR commits — implementations were already minimal.

## Confirmation: No Playwright Browser Installed for CI

- Playwright tests use `unittest.mock.AsyncMock` for `Route`, `Request`, `Page`; no `Browser` instance is created.
- `playwright install` was NOT run as part of this plan.
- The local developer machine had cached browsers from prior unrelated usage (`~/Library/Caches/ms-playwright/chromium-*`), but the test suite did not invoke them.
- CI (Ubuntu) will pass with only `uv sync` — no browser-binary download required for Phase 2 verification.

## Threat Flags

None — adapters introduce no new threat surface beyond what Phase 1 already mitigated. Identity.__repr__ remains REDACTED; no logging of raw requests; statelessness verified via nonce-difference test.

## Next Phase Readiness

- Plan 02-02 (policy inspector) can append-only to `wbauth/__init__.py` to re-export `inspect`, `SitePolicy` — adapter re-exports are already in place and won't conflict.
- Plan 02-03 (CLI) can rely on `wbauth.adapters.*` being stable.
- Phase 4 (TypeScript SDK) has the three adapter shapes as a reference — same semantics, mirror the API surface (sync_auth_flow + async_auth_flow → undici Dispatcher; AuthBase → fetch wrapper; attach_signing → Playwright in TS uses identical `page.route`).

## Self-Check: PASSED

Verification commands (all succeed):
- `[ -f python/src/wbauth/adapters/httpx_auth.py ]` → FOUND
- `[ -f python/src/wbauth/adapters/requests_adapter.py ]` → FOUND
- `[ -f python/src/wbauth/adapters/playwright.py ]` → FOUND
- `[ -f python/src/wbauth/adapters/_utils.py ]` → FOUND
- `[ -f python/tests/test_adapter_conformance.py ]` → FOUND
- `git log --oneline | grep b2ee4f5` → FOUND
- `git log --oneline | grep 45a2739` → FOUND
- `git log --oneline | grep 0fe3874` → FOUND
- `git log --oneline | grep 67e8058` → FOUND
- `git log --oneline | grep c7449dc` → FOUND
- `git log --oneline | grep 663ac87` → FOUND

---
*Phase: 02-python-adapters-policy-inspector*
*Completed: 2026-05-03*
