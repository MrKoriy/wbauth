---
phase: 01-foundation-cryptographic-root
plan: 04
type: execute
wave: 4
depends_on: [03]
files_modified:
  - spec/test-vectors/01-basic-get/input.json
  - spec/test-vectors/01-basic-get/expected.json
  - spec/test-vectors/02-post-with-content-digest/input.json
  - spec/test-vectors/02-post-with-content-digest/expected.json
  - spec/test-vectors/03-custom-expiry/input.json
  - spec/test-vectors/03-custom-expiry/expected.json
  - spec/test-vectors/04-multi-uri-jwks/input.json
  - spec/test-vectors/04-multi-uri-jwks/expected.json
  - spec/test-vectors/05-cloudflare-quirk/input.json
  - spec/test-vectors/05-cloudflare-quirk/expected.json
  - spec/test-vectors/06-cloudflare-debug-live/README.md
  - python/tests/conftest.py
  - python/tests/test_vectors.py
  - python/src/wbauth/_smoke/__init__.py
  - python/src/wbauth/_smoke/cloudflare_debug.py
  - typescript/tests/vectors.test.ts
  - typescript/tests/helpers.ts
  - .github/workflows/cloudflare-debug.yml
  - .github/workflows/conformance.yml
autonomous: true
requirements: [IDENT-04, IDENT-05]

must_haves:
  truths:
    - "spec/test-vectors/ contains 5 byte-equal vector directories (01..05) plus a 6th live-check directory (06-cloudflare-debug-live)"
    - "Each vector dir 01..05 has both input.json and expected.json with the schema from RESEARCH §5"
    - "pytest loads every spec/test-vectors/*/input.json, runs the Python signer with that input, and asserts byte-equality of the produced Signature-Input + Signature + Signature-Agent strings against expected.json (IDENT-04)"
    - "vitest loads the same spec/test-vectors/*/input.json files using the web-bot-auth npm package and asserts the same byte-equality against expected.json (IDENT-04 cross-language oracle)"
    - "A CI smoke test signs a request via the Python SDK using Identity.from_test_key + Cloudflare's research server URL, sends it to https://crawltest.com/cdn-cgi/web-bot-auth, and asserts HTTP 200 (IDENT-05)"
    - "GitHub Actions workflow .github/workflows/cloudflare-debug.yml runs the smoke test on push to main, on pull_request, and on a daily schedule (12:00 UTC)"
    - "The cloudflare-debug job exits non-zero if the response is anything other than 200 (IDENT-05 — hard exit criterion)"
    - "vector 06-cloudflare-debug-live/README.md documents that this 'vector' is not byte-equal but is the live conformance gate (IDENT-05)"
  artifacts:
    - path: spec/test-vectors/01-basic-get/input.json
      provides: "Vector 01: GET with @authority + signature-agent only"
      contains: "private_key_jwk"
    - path: spec/test-vectors/01-basic-get/expected.json
      provides: "Vector 01: expected Signature-Input, Signature, Signature-Agent strings"
      contains: "signature_input_value"
    - path: python/tests/test_vectors.py
      provides: "Parametrized pytest that runs all vectors against the Python signer (IDENT-04)"
      contains: "byte"
    - path: typescript/tests/vectors.test.ts
      provides: "Vitest cross-language oracle: same vectors, web-bot-auth 0.1.3 signer"
      contains: "describe"
    - path: typescript/tests/helpers.ts
      provides: "loadAllVectors() — reads spec/test-vectors/ from repo root"
      contains: "VECTORS_DIR"
    - path: python/src/wbauth/_smoke/cloudflare_debug.py
      provides: "Live smoke test: sign request, POST to crawltest.com, assert 200 (IDENT-05)"
      contains: "crawltest.com"
    - path: .github/workflows/cloudflare-debug.yml
      provides: "CI workflow: runs smoke test on push, PR, daily schedule (IDENT-05)"
      contains: "schedule"
    - path: .github/workflows/conformance.yml
      provides: "Cross-language conformance CI: pytest + vitest both consume spec/test-vectors/"
      contains: "pytest"
  key_links:
    - from: "python/tests/test_vectors.py"
      to: "spec/test-vectors/*/input.json"
      via: "conftest fixture loads all vector directories"
      pattern: "spec/test-vectors"
    - from: "typescript/tests/vectors.test.ts"
      to: "spec/test-vectors/*/input.json"
      via: "loadAllVectors() walks repo root spec/test-vectors/"
      pattern: "spec.*test-vectors"
    - from: "python/src/wbauth/_smoke/cloudflare_debug.py"
      to: "https://crawltest.com/cdn-cgi/web-bot-auth"
      via: "httpx.get with signed headers"
      pattern: "crawltest\\.com"
    - from: ".github/workflows/cloudflare-debug.yml"
      to: "python/src/wbauth/_smoke/cloudflare_debug.py"
      via: "uv run python -m wbauth._smoke.cloudflare_debug"
      pattern: "wbauth\\._smoke\\.cloudflare_debug"
---

<objective>
Author the cross-language test-vector oracle (5 byte-equal vectors + 1 live-conformance vector) and wire the Cloudflare debug verifier as a hard CI exit criterion. Satisfies IDENT-04 (byte-equal vectors) and IDENT-05 (Cloudflare conformance).

Purpose: Plan 03 produced the signer. Plan 04 proves the signer is correct against two independent oracles:
1. Cross-language byte-equality — Python SDK and TypeScript `web-bot-auth` 0.1.3 package both consume the same `spec/test-vectors/*/input.json` and must produce IDENTICAL `Signature-Input` and `Signature` headers. If they diverge, one of them deviates from RFC 9421 — and per RESEARCH §"Assumptions Log" A8, Cloudflare's TS package is the verifier-vendor, so Python conforms to TS.
2. Live conformance — a signed request hits Cloudflare's debug verifier endpoint at `https://crawltest.com/cdn-cgi/web-bot-auth` and gets 200 OK. This is the single most important external validation of the cryptographic root: if Cloudflare accepts our signature, every downstream feature has a working foundation.

Per CONTEXT.md `<critical_constraints>` 5: "Cloudflare debug verifier as conformance gate — by end of Phase 1, `https://crawltest.com/cdn-cgi/web-bot-auth` must accept a request signed by our SDK (200 OK). This is a hard exit criterion."

Output: 5 vector directories with paired input/expected JSON, a 6th directory with a README documenting the live check, parametrized pytest that runs all vectors, vitest mirror that does the same in TypeScript, a smoke test module that hits Cloudflare, and a GitHub Actions workflow that runs the smoke test on every push and daily.
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
@.planning/phases/01-foundation-cryptographic-root/01-03-SUMMARY.md
@python/src/wbauth/__init__.py
@python/src/wbauth/signer.py
@python/src/wbauth/identity.py
@spec/test-vectors/README.md

<interfaces>
<!-- Source-of-truth code references in 01-RESEARCH.md:
     §5 "Test Vector Schema" — input.json + expected.json schema
     §5 "Vector Generation Strategy" — chicken-and-egg resolution (signer-first)
     §5 "Five (Six) Initial Vectors" — table of vector names + coverage
     §6 "Cloudflare Debug Verifier Integration" — endpoint behavior + CI hook
     §"Code Examples" → "Cloudflare debug verifier smoke test" — verbatim Python smoke test
     §2 "Sharing spec/test-vectors/ Across Both Runtimes" — verbatim conftest.py + helpers.ts
-->

Vector 01 input.json template (canonical from RESEARCH §5):
```json
{
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

Vector 01 expected.json (the actual values are GENERATED by running Plan 03's signer once
on this input and capturing the output — see Task 1 below for the chicken-and-egg flow):
```json
{
  "kid": "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U",
  "signature_input_value": "<RUN_SIGNER_TO_FILL>",
  "signature_value": "<RUN_SIGNER_TO_FILL>",
  "signature_agent_value": "\"https://http-message-signatures-example.research.cloudflare.com/\"",
  "jwks_kid_thumbprint": "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U"
}
```

Vector list per RESEARCH §5:
| # | Name | What it covers | Input differences from vector 01 |
|---|------|---------------|-----------------------------------|
| 01 | 01-basic-get | GET with @authority + signature-agent only | (baseline) |
| 02 | 02-post-with-content-digest | POST with body + content-digest covered component | method=POST, body=base64-of-bytes, covered_components add "content-digest"; request.headers includes "Content-Digest": "sha-256=:<base64>:" pre-computed |
| 03 | 03-custom-expiry | expires_after_seconds=300 (non-default) | signing_params.expires_after_seconds=300 |
| 04 | 04-multi-uri-jwks | Identity with retiring key — JWKS export contains 2 keys; signature uses active only | identity has additional "retiring_key_jwk" field; expected adds a "jwks_full" field with both keys |
| 05 | 05-cloudflare-quirk | TBD edge case discovered during impl — likely "@authority lowercased even if URL host is uppercase" | request.url has uppercase hostname (e.g., https://Crawltest.com/...); expected signature_input shows `"@authority": "crawltest.com"` (lowercased) |
| 06 | 06-cloudflare-debug-live | NOT byte-equal — runs the smoke test against crawltest.com and asserts HTTP 200 | README.md only; no input.json/expected.json; smoke test lives in `python/src/wbauth/_smoke/cloudflare_debug.py` |

Python conftest fixture from RESEARCH §2 (replaces the Plan 02 stub):
```python
import json, pathlib, pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
VECTORS_DIR = REPO_ROOT / "spec" / "test-vectors"

def all_vector_dirs():
    return sorted(p for p in VECTORS_DIR.iterdir()
                  if p.is_dir() and (p / "input.json").exists())

@pytest.fixture(params=all_vector_dirs(), ids=lambda p: p.name)
def vector(request):
    d = request.param
    return {
        "name": d.name,
        "input": json.loads((d / "input.json").read_text()),
        "expected": json.loads((d / "expected.json").read_text()),
    }
```

TypeScript helpers from RESEARCH §2:
```typescript
import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const VECTORS_DIR = resolve(REPO_ROOT, "spec", "test-vectors");

export function loadAllVectors() {
  return readdirSync(VECTORS_DIR)
    .filter(name => statSync(resolve(VECTORS_DIR, name)).isDirectory())
    .filter(name => existsSync(resolve(VECTORS_DIR, name, "input.json")))
    .map(name => ({
      name,
      input: JSON.parse(readFileSync(resolve(VECTORS_DIR, name, "input.json"), "utf-8")),
      expected: JSON.parse(readFileSync(resolve(VECTORS_DIR, name, "expected.json"), "utf-8")),
    }));
}
```

Cloudflare debug smoke test (verbatim from RESEARCH §"Code Examples"):
```python
"""python/src/wbauth/_smoke/cloudflare_debug.py
Sign a request with the publicly-known RFC 9421 test key, POST to crawltest.com,
assert HTTP 200. Designed to be run as `python -m wbauth._smoke.cloudflare_debug`.
Exits non-zero on anything but 200.
"""
import sys, datetime
import httpx
from wbauth import Identity, NormalizedRequest, sign

CLOUDFLARE_DEBUG_URL = "https://crawltest.com/cdn-cgi/web-bot-auth"
CF_RESEARCH_JWKS_URL = "https://http-message-signatures-example.research.cloudflare.com/"


def run() -> int:
    identity = Identity.from_test_key(signature_agent_url=CF_RESEARCH_JWKS_URL)
    req = NormalizedRequest(method="GET", url=CLOUDFLARE_DEBUG_URL, headers={})
    sig = sign(req, identity, created=datetime.datetime.now(datetime.timezone.utc))

    response = httpx.get(
        CLOUDFLARE_DEBUG_URL,
        headers={
            "Signature": sig.signature,
            "Signature-Input": sig.signature_input,
            "Signature-Agent": sig.signature_agent,
        },
        timeout=10.0,
    )
    if response.status_code != 200:
        print(
            f"FAIL: Cloudflare debug verifier rejected. "
            f"status={response.status_code} body={response.text!r}",
            file=sys.stderr,
        )
        return 1
    print(f"OK: Cloudflare debug verifier accepted (status=200, kid={identity.kid})")
    return 0


if __name__ == "__main__":
    sys.exit(run())
```

GitHub Actions workflow `.github/workflows/cloudflare-debug.yml` (final form, per RESEARCH §6):
```yaml
name: Cloudflare Debug Verifier
on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: '0 12 * * *'   # daily canary at 12:00 UTC (Pitfall 12 mitigation)
jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - name: Sign + send to crawltest.com (Cloudflare debug verifier)
        run: uv run python -m wbauth._smoke.cloudflare_debug
        # Exits non-zero on anything but HTTP 200 from crawltest.com.
        # If this job fails, the cryptographic root is broken — block the merge.
```

Final form of `.github/workflows/conformance.yml` (REPLACES the Plan 02 stub — the real vector tests now exist):
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
        run: uv run pytest python/tests/test_vectors.py -v
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
        run: pnpm --filter wbauth test
  cloudflare-debug:
    needs: [python-vectors]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - name: Cloudflare debug verifier smoke test
        run: uv run python -m wbauth._smoke.cloudflare_debug
```

`spec/test-vectors/06-cloudflare-debug-live/README.md` (NOT a byte-equal vector):
```markdown
# 06-cloudflare-debug-live

This is NOT a byte-equality vector. It is the live conformance gate per IDENT-05.

Implementation lives at `python/src/wbauth/_smoke/cloudflare_debug.py`.
CI runs it via `.github/workflows/cloudflare-debug.yml` on every push to main,
on every PR, and on a daily schedule (12:00 UTC) to catch Cloudflare-side
spec drift during the unmaintained period (Pitfall 12).

The test:
1. Constructs an Identity from the publicly-known RFC 9421 Appendix B.1.4 test key.
2. Uses `https://http-message-signatures-example.research.cloudflare.com/` as the
   `signature-agent` URL — this is Cloudflare's research server which serves the
   matching JWKS publicly. Combined with using the same test key as the SDK's
   signing key, the verifier finds our public key and verifies our signature
   without us needing to host JWKS ourselves yet (per RESEARCH Pitfall 7 Option A).
3. Signs a GET request to `https://crawltest.com/cdn-cgi/web-bot-auth`.
4. Asserts response.status_code == 200.

Failure modes (status != 200):
- 400 → malformed signature (most likely a regression in the signer; check Pitfalls 1, 2, 6)
- 401 → key unknown (the JWKS URL was unreachable or the kid mismatch — verify Identity.from_test_key)
- 5xx → Cloudflare-side outage; retry; if persistent, escalate to Cloudflare research team
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Author 5 byte-equal test vectors (input.json + expected.json) using the Python signer to generate expected outputs</name>
  <read_first>
    - python/src/wbauth/signer.py (Plan 03 — used to generate expected.json values)
    - python/src/wbauth/identity.py (Plan 03 — for `Identity.from_test_key` used to construct identities from JWK)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §5 "Test Vector Schema" (full input.json/expected.json schemas)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §5 "Vector Generation Strategy" (chicken-and-egg flow)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §5 "Five (Six) Initial Vectors" table
    - spec/test-vectors/README.md (Plan 02 — vector format documentation)
  </read_first>
  <action>
    Author 5 vector directories. The chicken-and-egg pattern from RESEARCH §5:
    (1) write input.json by hand; (2) run the signer once on that input to capture output;
    (3) write expected.json with the captured values; (4) commit both. Subsequent runs of the
    signer on the same input MUST reproduce the same output (Ed25519 is deterministic — same
    key + same created + same nonce → identical signature bytes).

    Step-by-step:

    1. Create the directory structure:
       ```bash
       mkdir -p spec/test-vectors/01-basic-get
       mkdir -p spec/test-vectors/02-post-with-content-digest
       mkdir -p spec/test-vectors/03-custom-expiry
       mkdir -p spec/test-vectors/04-multi-uri-jwks
       mkdir -p spec/test-vectors/05-cloudflare-quirk
       mkdir -p spec/test-vectors/06-cloudflare-debug-live
       ```

    2. Write each vector's `input.json` from the table in `<interfaces>`:

       Vector 01 `input.json`: verbatim from `<interfaces>` block.

       Vector 02 `input.json`: same as 01 but:
       - `request.method = "POST"`
       - `request.body` = base64 of `b"hello-from-vector-02"` (use `import base64; base64.b64encode(b'hello-from-vector-02').decode()`)
       - `request.headers["Content-Digest"]` pre-computed: `f"sha-256=:{base64.b64encode(hashlib.sha256(body_bytes).digest()).decode()}:"`
       - `signing_params.covered_components = ["@authority", "signature-agent", "content-digest"]`
       - `signing_params.nonce = "test-nonce-02-fixed"`

       Vector 03 `input.json`: same as 01 but:
       - `signing_params.expires_after_seconds = 300`
       - `signing_params.nonce = "test-nonce-03-fixed"`

       Vector 04 `input.json`: same as 01 but:
       - `identity` adds a second key pair under `retiring_key_jwk` — generate one ad-hoc using `Ed25519PrivateKey.generate()` then export to JWK with `d` and `x` fields. Hard-code the values once generated (so the vector is deterministic).
       - `signing_params.nonce = "test-nonce-04-fixed"`

       Vector 05 `input.json`: same as 01 but:
       - `request.url = "https://Crawltest.Com/cdn-cgi/web-bot-auth"` (uppercase host — proves the signer lowercases @authority per RFC 9421 / Cloudflare expectation)
       - `signing_params.nonce = "test-nonce-05-fixed"`
       - Document at top of file (in `description` field): "Edge case: uppercase hostname; @authority must be lowercased per RFC 9421 §2.2.2"

       Vector 06: skip input.json/expected.json — only create the README.md per `<interfaces>`.

    3. Write a one-time generator script `python/scripts/generate_expected_vectors.py` (NOT a test — just a tool):
       ```python
       """Generate expected.json for each vector by running the Python signer.

       Run: uv run python python/scripts/generate_expected_vectors.py
       Then COMMIT the generated expected.json files. CI will re-run the signer on
       every push and assert byte-equality (test_vectors.py).
       """
       import json, base64, datetime, pathlib, sys
       from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
       from wbauth import Identity, KeyPair, NormalizedRequest, sign
       from wbauth.identity import _compute_kid


       VECTORS_DIR = pathlib.Path(__file__).resolve().parents[2] / "spec" / "test-vectors"


       def b64url_decode(s: str) -> bytes:
           return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


       def identity_from_jwk(jwk: dict, sig_agent_url: str, retiring_jwk: dict | None) -> Identity:
           priv = Ed25519PrivateKey.from_private_bytes(b64url_decode(jwk["d"]))
           active = KeyPair(priv, _compute_kid(priv.public_key()))
           retiring = None
           if retiring_jwk is not None:
               r_priv = Ed25519PrivateKey.from_private_bytes(b64url_decode(retiring_jwk["d"]))
               retiring = KeyPair(r_priv, _compute_kid(r_priv.public_key()))
           return Identity(active, sig_agent_url, retiring=retiring)


       def generate_one(vector_dir: pathlib.Path) -> None:
           inp = json.loads((vector_dir / "input.json").read_text())
           ident = identity_from_jwk(
               inp["identity"]["private_key_jwk"],
               inp["identity"]["signature_agent_url"],
               inp["identity"].get("retiring_key_jwk"),
           )
           req = NormalizedRequest(
               method=inp["request"]["method"],
               url=inp["request"]["url"],
               headers=dict(inp["request"]["headers"]),
               body=base64.b64decode(inp["request"]["body"]) if inp["request"].get("body") else None,
           )
           created = datetime.datetime.fromtimestamp(
               inp["signing_params"]["created"], tz=datetime.timezone.utc
           )
           result = sign(
               req, ident,
               created=created,
               expires_after_seconds=inp["signing_params"]["expires_after_seconds"],
               nonce=inp["signing_params"]["nonce"],
               label=inp["signing_params"]["label"],
           )
           expected = {
               "kid": ident.kid,
               "signature_input_value": result.signature_input,
               "signature_value": result.signature,
               "signature_agent_value": result.signature_agent,
               "jwks_kid_thumbprint": ident.kid,
           }
           if inp["identity"].get("retiring_key_jwk"):
               expected["jwks_full"] = ident.export_jwks()
           (vector_dir / "expected.json").write_text(json.dumps(expected, indent=2) + "\n")
           print(f"wrote {vector_dir.name}/expected.json")


       def main():
           dirs = sorted(d for d in VECTORS_DIR.iterdir()
                         if d.is_dir() and (d / "input.json").exists())
           for d in dirs:
               generate_one(d)
           print(f"\nGenerated {len(dirs)} expected.json files. COMMIT them.")
           return 0


       if __name__ == "__main__":
           sys.exit(main())
       ```

    4. Run the generator:
       ```bash
       uv run python python/scripts/generate_expected_vectors.py
       ```
       Verify each expected.json has been written with non-placeholder values.

    5. Sanity-check vector 01 against the canonical kid:
       ```bash
       uv run python -c "import json; v = json.load(open('spec/test-vectors/01-basic-get/expected.json')); assert v['kid'] == 'poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U', v['kid']; assert 'web-bot-auth' in v['signature_input_value']; print('vector 01 OK')"
       ```

    6. Add `python/scripts/__init__.py` (empty) so pytest doesn't accidentally pick it up as a test directory; alternatively keep `python/scripts/` outside `python/tests/` (the layout already does that).

    7. Write the README at `spec/test-vectors/06-cloudflare-debug-live/README.md` from `<interfaces>` verbatim.
  </action>
  <verify>
    <automated>test -d spec/test-vectors/01-basic-get &amp;&amp; test -d spec/test-vectors/02-post-with-content-digest &amp;&amp; test -d spec/test-vectors/03-custom-expiry &amp;&amp; test -d spec/test-vectors/04-multi-uri-jwks &amp;&amp; test -d spec/test-vectors/05-cloudflare-quirk &amp;&amp; test -d spec/test-vectors/06-cloudflare-debug-live &amp;&amp; for d in 01-basic-get 02-post-with-content-digest 03-custom-expiry 04-multi-uri-jwks 05-cloudflare-quirk; do test -f "spec/test-vectors/$d/input.json" || exit 1; test -f "spec/test-vectors/$d/expected.json" || exit 1; done &amp;&amp; test -f spec/test-vectors/06-cloudflare-debug-live/README.md &amp;&amp; uv run python -c "import json; v = json.load(open('spec/test-vectors/01-basic-get/expected.json')); assert v['kid'] == 'poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U'; assert 'web-bot-auth' in v['signature_input_value']; assert v['signature_value'].startswith('sig1=')" &amp;&amp; uv run python -c "import json; v = json.load(open('spec/test-vectors/05-cloudflare-quirk/input.json')); assert 'Crawltest' in v['request']['url'] or 'CRAWLTEST' in v['request']['url']"</automated>
  </verify>
  <acceptance_criteria>
    - All 5 byte-equal vector directories exist (01..05) with both `input.json` and `expected.json`
    - Vector 06 directory exists with `README.md` only (no input/expected — it's the live check)
    - Vector 01 expected.json contains `kid == "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U"` (the canonical RFC 9421 thumbprint)
    - Every expected.json has non-empty `signature_input_value`, `signature_value`, `signature_agent_value` (no `<RUN_SIGNER_TO_FILL>` placeholders)
    - `signature_value` always starts with `sig1=` (label per signer defaults)
    - `signature_input_value` always contains the literal `tag="web-bot-auth"` substring
    - Vector 02 input has `method=POST`, body base64, and components include `"content-digest"`
    - Vector 03 input has `expires_after_seconds=300`
    - Vector 04 input has both `private_key_jwk` and `retiring_key_jwk`; expected has `jwks_full` with 2 keys
    - Vector 05 input has uppercase hostname in url; expected.json's `signature_input_value` shows the lowercased authority
    - `python/scripts/generate_expected_vectors.py` exists for re-generation if a future change to the signer requires updating expected outputs
  </acceptance_criteria>
  <done>
    Five byte-equal test vectors authored with deterministic Ed25519-signed expected outputs. Live-check directory documented. Generator script committed for future regeneration.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire pytest + vitest to load vectors and assert byte-equality (cross-language oracle)</name>
  <read_first>
    - spec/test-vectors/01-basic-get/input.json (just created — confirms the schema)
    - spec/test-vectors/01-basic-get/expected.json (just created)
    - python/tests/conftest.py (Plan 02 stub — to be replaced)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §2 "Sharing spec/test-vectors/ Across Both Runtimes" (verbatim conftest.py + helpers.ts)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §"Assumptions Log" A8 (Python and TS may diverge — if so, conform Python to TS)
    - typescript/package.json (web-bot-auth 0.1.3 dependency confirmed by Plan 02 install)
  </read_first>
  <behavior>
    Test functions for `python/tests/test_vectors.py`:

    - test_vector_byte_equal_signature_input(vector): for each vector, sign with input.json's params and assert produced `Signature-Input` header value matches expected.json's `signature_input_value` exactly. [IDENT-04]
    - test_vector_byte_equal_signature(vector): for each vector, the produced `Signature` header value matches `signature_value` exactly. [IDENT-04]
    - test_vector_byte_equal_signature_agent(vector): produced `Signature-Agent` matches `signature_agent_value`. [IDENT-04]
    - test_vector_kid_matches(vector): the Identity's kid matches `expected["kid"]`. [IDENT-06 cross-check]
    - test_vector_jwks_full_for_multi_key(vector): if expected has `jwks_full`, identity.export_jwks() matches it. [IDENT-07]

    Test functions for `typescript/tests/vectors.test.ts`:

    - For each vector (loaded via `loadAllVectors()`), use `web-bot-auth` 0.1.3's `signatureHeaders(...)` to produce the headers, then assert byte-equality against `expected.signature_input_value` and `expected.signature_value`.
    - If a vector includes `retiring_key_jwk`, the TypeScript test may skip (Phase 4's full TS SDK handles multi-key Identity; in Phase 1 the TS package is a stub used only as the cross-language oracle).
  </behavior>
  <action>
    1. Replace `python/tests/conftest.py` from Plan 02's docstring stub with the full fixture from `<interfaces>`:
       ```python
       import json, pathlib, pytest

       REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
       VECTORS_DIR = REPO_ROOT / "spec" / "test-vectors"

       def all_vector_dirs():
           return sorted(p for p in VECTORS_DIR.iterdir()
                         if p.is_dir() and (p / "input.json").exists())

       @pytest.fixture(params=all_vector_dirs(), ids=lambda p: p.name)
       def vector(request):
           d = request.param
           return {
               "name": d.name,
               "input": json.loads((d / "input.json").read_text()),
               "expected": json.loads((d / "expected.json").read_text()),
           }
       ```

    2. Write `python/tests/test_vectors.py` with the 5 test functions from `<behavior>`. Use the same JWK→Identity helper logic as Task 1's generator (factor it into a small local helper, OR import from the generator script via `sys.path` manipulation if cleaner — but a 10-line local copy is fine):
       ```python
       import base64, datetime
       from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
       from wbauth import Identity, KeyPair, NormalizedRequest, sign
       from wbauth.identity import _compute_kid


       def _b64url_decode(s: str) -> bytes:
           return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


       def _identity_from_input(inp: dict) -> Identity:
           priv = Ed25519PrivateKey.from_private_bytes(
               _b64url_decode(inp["identity"]["private_key_jwk"]["d"])
           )
           active = KeyPair(priv, _compute_kid(priv.public_key()))
           retiring = None
           if rj := inp["identity"].get("retiring_key_jwk"):
               rpriv = Ed25519PrivateKey.from_private_bytes(_b64url_decode(rj["d"]))
               retiring = KeyPair(rpriv, _compute_kid(rpriv.public_key()))
           return Identity(active, inp["identity"]["signature_agent_url"], retiring=retiring)


       def _sign_from_input(inp: dict):
           ident = _identity_from_input(inp)
           req = NormalizedRequest(
               method=inp["request"]["method"],
               url=inp["request"]["url"],
               headers=dict(inp["request"]["headers"]),
               body=base64.b64decode(inp["request"]["body"]) if inp["request"].get("body") else None,
           )
           created = datetime.datetime.fromtimestamp(
               inp["signing_params"]["created"], tz=datetime.timezone.utc
           )
           sig = sign(
               req, ident,
               created=created,
               expires_after_seconds=inp["signing_params"]["expires_after_seconds"],
               nonce=inp["signing_params"]["nonce"],
               label=inp["signing_params"]["label"],
           )
           return ident, sig


       def test_vector_byte_equal_signature_input(vector):
           _, sig = _sign_from_input(vector["input"])
           assert sig.signature_input == vector["expected"]["signature_input_value"], (
               f"\n  produced: {sig.signature_input}"
               f"\n  expected: {vector['expected']['signature_input_value']}"
           )


       def test_vector_byte_equal_signature(vector):
           _, sig = _sign_from_input(vector["input"])
           assert sig.signature == vector["expected"]["signature_value"]


       def test_vector_byte_equal_signature_agent(vector):
           _, sig = _sign_from_input(vector["input"])
           assert sig.signature_agent == vector["expected"]["signature_agent_value"]


       def test_vector_kid_matches(vector):
           ident, _ = _sign_from_input(vector["input"])
           assert ident.kid == vector["expected"]["kid"]


       def test_vector_jwks_full_for_multi_key(vector):
           if "jwks_full" not in vector["expected"]:
               return  # vectors without retiring key skip this check
           ident, _ = _sign_from_input(vector["input"])
           assert ident.export_jwks() == vector["expected"]["jwks_full"]
       ```

       Run: `uv run pytest python/tests/test_vectors.py -v` — should produce 5 vectors × 5 tests = ~25 test cases (some `test_vector_jwks_full_for_multi_key` skip), all GREEN.

    3. Write `typescript/tests/helpers.ts` from `<interfaces>` (loadAllVectors).

    4. Write `typescript/tests/vectors.test.ts`:
       ```typescript
       import { describe, it, expect } from "vitest";
       import { loadAllVectors } from "./helpers";
       import { signatureHeaders, signerFromJWK } from "web-bot-auth";

       const vectors = loadAllVectors();

       describe("cross-language byte-equality vectors", () => {
         for (const v of vectors) {
           // Vectors with retiring_key_jwk are multi-key (IDENT-07) — Phase 4's TS SDK
           // handles multi-key. Phase 1 TS is only the cross-language oracle for the
           // active key, so we skip multi-key vectors here.
           if (v.input.identity.retiring_key_jwk) {
             it.skip(`${v.name} (multi-key — Phase 4 will cover)`, () => {});
             continue;
           }

           it(`${v.name}: produces byte-equal Signature-Input + Signature`, async () => {
             const jwk = v.input.identity.private_key_jwk;
             const signer = await signerFromJWK(jwk);

             // Construct a Request object matching the input.json shape.
             // web-bot-auth expects a Request with the Signature-Agent header pre-set,
             // mirroring the Python SDK's first action in sign().
             const headers = new Headers();
             for (const [k, val] of Object.entries(v.input.request.headers as Record<string, string>)) {
               headers.set(k, val);
             }
             headers.set("Signature-Agent", `"${v.input.identity.signature_agent_url}"`);

             const req = new Request(v.input.request.url, {
               method: v.input.request.method,
               headers,
               body: v.input.request.body
                 ? Buffer.from(v.input.request.body, "base64")
                 : undefined,
             });

             const params = {
               created: new Date(v.input.signing_params.created * 1000),
               expires: new Date(
                 (v.input.signing_params.created + v.input.signing_params.expires_after_seconds) * 1000
               ),
               nonce: v.input.signing_params.nonce,
               label: v.input.signing_params.label,
               tag: "web-bot-auth",
               coveredComponents: v.input.signing_params.covered_components,
             };

             const result = await signatureHeaders(req, signer, params);

             expect(result["Signature-Input"]).toBe(v.expected.signature_input_value);
             expect(result["Signature"]).toBe(v.expected.signature_value);
           });
         }
       });
       ```

       NOTE: `web-bot-auth` 0.1.3's exact API surface for `signatureHeaders(...)` may differ from
       the above sketch. RESEARCH §"Standard Stack" and §"Assumptions Log" A8 say to verify the
       library's actual signature against this assumed shape. If the API differs:
       - Read `node_modules/web-bot-auth/dist/index.d.ts` (or equivalent) to confirm.
       - Adjust the param shape to match.
       - If the TS library produces output that DIFFERS byte-wise from Python's expected.json,
         per RESEARCH §"Assumptions Log" A8: "Cloudflare's package is the verifier-vendor — if
         anything, conform Python to TS, not vice-versa." Re-run Task 1's generator script with
         a wrap on the Python signer to match TS, then commit the regenerated expected.json.
         Document the divergence in 01-04-SUMMARY.md.

    5. Run TypeScript tests:
       ```bash
       pnpm --filter wbauth test
       ```
       Expect all non-multi-key vectors to PASS (4 vectors × 1 test = 4 tests). The multi-key vector skips.

    6. Confirm pytest still all-green after the new test_vectors.py is added:
       ```bash
       uv run pytest python/tests/ -v
       ```
       Expect: test_identity (~14) + test_signer (~13) + test_cli (~3) + test_vectors (~25) = ~55 test cases all green.
  </action>
  <verify>
    <automated>uv run pytest python/tests/test_vectors.py -v --tb=short &amp;&amp; uv run pytest python/tests/ -v --tb=short &amp;&amp; pnpm --filter wbauth test</automated>
  </verify>
  <acceptance_criteria>
    - `python/tests/conftest.py` defines `vector` fixture parametrized over all `spec/test-vectors/*/` directories with `input.json`
    - `python/tests/test_vectors.py` exists with 5 test functions from `<behavior>`
    - `uv run pytest python/tests/test_vectors.py -v` passes ALL byte-equality assertions for all 5 vectors (4×5 = 20 strict assertions + 1 jwks_full = 21 cases minus skips)
    - Full pytest suite (`uv run pytest python/tests/`) passes ~55 tests across identity, signer, cli, vectors
    - `typescript/tests/helpers.ts` exists with `loadAllVectors()` reading from repo root `spec/test-vectors/`
    - `typescript/tests/vectors.test.ts` exists; iterates vectors; skips multi-key vector with `it.skip(...)`
    - `pnpm --filter wbauth test` passes — every non-multi-key vector produces byte-equal output
    - If TS and Python diverged: SUMMARY.md documents the divergence + the conformance direction taken (Python conformed to TS per A8)
  </acceptance_criteria>
  <done>
    Cross-language byte-equality oracle wired and green. Both runtimes consume identical `spec/test-vectors/*/input.json` and produce identical Signature/Signature-Input headers. IDENT-04 verified.
  </done>
</task>

<task type="auto">
  <name>Task 3: Implement Cloudflare debug verifier smoke test + GitHub Actions workflow (HARD exit criterion)</name>
  <read_first>
    - python/src/wbauth/signer.py (Plan 03 — used by smoke test)
    - python/src/wbauth/identity.py (Plan 03 — `Identity.from_test_key`)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §6 "Cloudflare Debug Verifier Integration" (full section: endpoint behavior, JWKS reachability rule, CI hook YAML)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §"Pitfalls" 7 (JWKS publicly reachable — Option A used here)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §"Code Examples" → "Cloudflare debug verifier smoke test (CI hook)"
    - .planning/phases/01-foundation-cryptographic-root/01-CONTEXT.md `<critical_constraints>` 5 (Cloudflare debug as hard exit criterion)
    - .github/workflows/conformance.yml (Plan 02 stub — will be replaced with the final form)
  </read_first>
  <action>
    Write the smoke test module and the dedicated GitHub Actions workflow. This is the hardest exit criterion of Phase 1.

    1. Create `python/src/wbauth/_smoke/__init__.py`:
       ```python
       """Internal smoke tests for live conformance against external services.

       Not part of the public API. Submodules are intended to be runnable as
       `python -m wbauth._smoke.<name>` from CI workflows.
       """
       ```

    2. Create `python/src/wbauth/_smoke/cloudflare_debug.py` verbatim from `<interfaces>` block.

    3. Run the smoke test locally to confirm it works (this is a network test — requires public internet):
       ```bash
       uv run python -m wbauth._smoke.cloudflare_debug
       ```
       Expected: prints `OK: Cloudflare debug verifier accepted (status=200, kid=poqkLGiymh_W...)` and exits 0.

       FAILURE TROUBLESHOOTING (if non-200):
       - 400 → signature malformed: re-check Pitfalls 1, 2, 6 in RESEARCH; re-run pytest test_signer to confirm signer regression-free.
       - 401 → key unknown: the CF research server's JWKS at `https://http-message-signatures-example.research.cloudflare.com/.well-known/http-message-signatures-directory` may have changed kids — verify with curl. Or our kid computation drifted from RFC 7638.
       - 5xx → Cloudflare-side outage; retry up to 3 times; if persistent, document in SUMMARY and re-run when service is healthy.

       This step is the LITMUS TEST for the entire phase. If it fails for a non-CF reason, the phase has a regression that must be fixed before Plan completion.

    4. Write `.github/workflows/cloudflare-debug.yml` from `<interfaces>` verbatim. The workflow has THREE triggers:
       - `push: branches: [main]` — gate every merge to main
       - `pull_request:` — gate every PR
       - `schedule: cron: '0 12 * * *'` — daily canary (Pitfall 12 mitigation: catches CF-side spec drift during army leave)

    5. Replace `.github/workflows/conformance.yml` with the full form from `<interfaces>` — the Plan 02 stub had `|| echo "Plan 04 will add..."` placeholder; now the actual vector tests exist, so remove the fallback. The new conformance.yml has THREE jobs:
       - `python-vectors` — runs `uv run pytest python/tests/test_vectors.py -v`
       - `typescript-vectors` — runs `pnpm --filter wbauth test`
       - `cloudflare-debug` — depends on python-vectors; runs the smoke test

       NOTE: the dedicated `cloudflare-debug.yml` and the conformance.yml's `cloudflare-debug` job overlap intentionally. The dedicated workflow runs on a schedule (daily canary) and on main pushes. The conformance.yml job runs on every PR (gates merges). Both call the same `python -m wbauth._smoke.cloudflare_debug` so a failure in either has the same root cause.

    6. Validate workflow YAML syntax:
       ```bash
       for f in .github/workflows/*.yml; do
         python3 -c "import yaml; yaml.safe_load(open('$f'))" && echo "OK: $f" || (echo "BAD: $f" && exit 1)
       done
       ```

    7. Confirm the conformance.yml updates are visible:
       ```bash
       grep -q 'wbauth._smoke.cloudflare_debug' .github/workflows/conformance.yml
       grep -q 'schedule:' .github/workflows/cloudflare-debug.yml
       grep -q "cron:" .github/workflows/cloudflare-debug.yml
       ! grep -q "Plan 04 will add" .github/workflows/conformance.yml  # placeholder removed
       ```
  </action>
  <verify>
    <automated>test -f python/src/wbauth/_smoke/__init__.py &amp;&amp; test -f python/src/wbauth/_smoke/cloudflare_debug.py &amp;&amp; test -f .github/workflows/cloudflare-debug.yml &amp;&amp; test -f .github/workflows/conformance.yml &amp;&amp; for f in .github/workflows/*.yml; do python3 -c "import yaml; yaml.safe_load(open('$f'))" || exit 1; done &amp;&amp; grep -q 'wbauth._smoke.cloudflare_debug' .github/workflows/conformance.yml &amp;&amp; grep -q 'schedule:' .github/workflows/cloudflare-debug.yml &amp;&amp; grep -q 'cron' .github/workflows/cloudflare-debug.yml &amp;&amp; ! grep -q "Plan 04 will add" .github/workflows/conformance.yml &amp;&amp; uv run python -m wbauth._smoke.cloudflare_debug</automated>
  </verify>
  <acceptance_criteria>
    - `python/src/wbauth/_smoke/cloudflare_debug.py` exists, imports `Identity`, `NormalizedRequest`, `sign` from `wbauth`
    - The smoke test sends a signed request to `https://crawltest.com/cdn-cgi/web-bot-auth` using `Identity.from_test_key(signature_agent_url="https://http-message-signatures-example.research.cloudflare.com/")`
    - `uv run python -m wbauth._smoke.cloudflare_debug` exits 0 and prints `OK: Cloudflare debug verifier accepted (status=200, kid=poqkLGiymh_W...)` — THIS IS THE PHASE 1 EXIT CRITERION
    - `.github/workflows/cloudflare-debug.yml` exists with triggers: `push: branches: [main]`, `pull_request:`, AND `schedule: cron: '0 12 * * *'`
    - `.github/workflows/conformance.yml` is the final form (no `|| echo "Plan 04 will add..."` placeholders) with three jobs: python-vectors, typescript-vectors, cloudflare-debug
    - Both workflow files parse as valid YAML
    - The smoke test exits non-zero on any non-200 response (verifiable by reading the source: `if response.status_code != 200: return 1`)
  </acceptance_criteria>
  <done>
    Cloudflare debug verifier conformance gate is live and passing. CI runs the smoke test on every merge to main, every PR, AND daily (Pitfall 12 canary for the army-leave period). IDENT-05 satisfied. Phase 1 hard exit criterion met.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| spec/test-vectors/*.json → CI runners | Test vectors are committed JSON; both pytest and vitest read them as untrusted-but-attached input. They reference the publicly-known RFC 9421 Appendix B.1.4 test key. |
| Python signer → http-message-signatures library | Pure-function call; same as Plan 03. |
| TypeScript signer → web-bot-auth npm package | Pinned via pnpm-lock.yaml; supply chain protected by Plan 02's lockfile gate. |
| smoke test → crawltest.com | Outbound HTTPS request from CI runner to a Cloudflare-operated public endpoint. No secrets in transit (the test key is publicly known). |
| smoke test → CF research server JWKS | Outbound HTTPS request to fetch the public JWKS used by the verifier (we don't host JWKS yet). |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-04-01 | Information Disclosure | private key in vector input.json files | mitigate | Vectors use ONLY the publicly-known RFC 9421 Appendix B.1.4 test key (`d=n4Ni-...`) which is in the IETF spec — not a secret. Vector 04's retiring key is a fresh ad-hoc Ed25519 key generated for the test (publicly-known by construction once committed). No production keys in repo. |
| T-01-04-02 | Tampering | someone modifies expected.json without rerunning the signer (poisons future tests) | mitigate | Plan 02's CI runs `pytest python/tests/test_vectors.py` on every PR — any drift between Python signer output and committed expected.json fails CI. Manual-only override would require explicit reviewer approval. |
| T-01-04-03 | Denial of Service | crawltest.com rate-limits our CI traffic | accept | RESEARCH §6: "Rate limits not officially documented. Assume reasonable use." Daily canary + per-PR runs is well within "reasonable." Mitigation if hit: add a `concurrency: cloudflare-debug-${{ github.ref }}` group + retry-with-backoff. Defer until observed. |
| T-01-04-04 | Spoofing | someone impersonates crawltest.com to return spurious 200 | accept | TLS verification by httpx on default settings; no custom CA bundle. CF's cert is validated via system trust store. Negligible. |
| T-01-04-05 | Tampering | the CF research server JWKS at `http-message-signatures-example.research.cloudflare.com` rotates kids and our pinned test key kid no longer matches | mitigate | Daily canary (cron `0 12 * * *`) catches this within 24h. PITFALLS Pitfall 12 explicitly. Mitigation: rebuild expected.json with `Identity.from_test_key(...).kid` programmatically (already done — kid is computed at runtime, not hardcoded). The fixed value `poqkLGiymh_W...` is asserted in vector 01 — if it diverges from the live CF server, the test_vectors.py test_vector_kid_matches assertion will fail, signaling that the publicly-known RFC 9421 test key has been rotated (extremely unlikely; would require an IETF spec change). |
| T-01-04-06 | Information Disclosure | smoke test logs the signed request including private key bytes | mitigate | The test logs only `status_code`, `kid` (public), and `body` (CF's response text). The Identity object's REDACTED `__repr__` (Plan 03) prevents accidental key leakage if the test ever does `print(identity)`. |
| T-01-04-07 | Spoofing | TypeScript SDK silently produces non-RFC-9421 signatures that Python's vector test misses | mitigate | The cross-language test (vectors.test.ts) compares TS output against the SAME `expected.json` that Python compares against. Divergence → vitest fails → CI fails → merge blocked. Per A8, if TS is correct and Python diverges, conform Python to TS. |
| T-01-04-08 | Repudiation | Cloudflare reverses a previously-passing test rule mid-army-leave (silent failure) | mitigate | Daily canary opens visible failure in GitHub Actions. Phase 5's HARDEN-04 will add a Discord alert + GitHub issue creation on failure for during-absence visibility. Phase 1 only sets up the canary; Phase 5 adds notification routing. |
</threat_model>

<verification>
1. `uv run pytest python/tests/ -v` passes ~55 tests (identity, signer, cli, vectors).
2. `pnpm --filter wbauth test` passes all non-multi-key vectors with byte-equal output.
3. `uv run python -m wbauth._smoke.cloudflare_debug` returns exit 0 and prints `OK: Cloudflare debug verifier accepted (status=200, ...)`. THIS IS THE PHASE 1 HARD EXIT CRITERION.
4. `spec/test-vectors/01-basic-get/expected.json` has `kid == "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U"` (canonical RFC 7638 thumbprint of Appendix B.1.4 test key).
5. `.github/workflows/cloudflare-debug.yml` has triggers for push/PR/schedule (cron `0 12 * * *`).
6. `.github/workflows/conformance.yml` has three jobs: python-vectors, typescript-vectors, cloudflare-debug — no Plan-02 placeholder fallbacks remain.
7. All workflow YAML files parse cleanly via `python3 -c "import yaml; yaml.safe_load(...)"`.
</verification>

<success_criteria>
- IDENT-04 satisfied: 5 byte-equal vectors authored; pytest + vitest both load them and assert byte-equality across language implementations
- IDENT-05 satisfied: Cloudflare debug verifier accepts a request signed by our SDK in <2 seconds end-to-end (CI smoke test + dedicated daily canary workflow)
- The Phase 1 exit criterion (`crawltest.com/cdn-cgi/web-bot-auth` returns 200) is met and is gated by CI on every push/PR
- Daily canary (Pitfall 12 mitigation) is configured to catch CF-side spec drift during the unmaintained period
- 01-04-SUMMARY.md documents: any TS/Python signature divergence found and how it was resolved (per A8); the actual signature_value bytes for vector 01 (for future-debugging reference); confirmation that vector 05 picked an actual CF quirk (uppercase host or other)
- All Phase 1 ROADMAP success criteria #2, #3, #4 are met (criterion #1 was Plan 01; criterion #5 was Plan 03's IDENT-07)
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundation-cryptographic-root/01-04-SUMMARY.md` summarizing:
- Vectors authored (filenames + a one-line description of each)
- Test counts: pytest (test_vectors.py — should be ~25 cases), vitest (vectors.test.ts — 4 cases + 1 skipped)
- Smoke test result: live `python -m wbauth._smoke.cloudflare_debug` exit code + produced kid
- Vector 05's actual quirk chosen (e.g., "uppercase hostname → @authority lowercased")
- Any cross-language divergence found (TS vs Python signer output): if any, which way conformance went per A8
- A note that Phase 1 is COMPLETE: every requirement IDENT-01..08 + DIR-06 has been satisfied; the cryptographic root is locked; Phase 2 may proceed
</output>
