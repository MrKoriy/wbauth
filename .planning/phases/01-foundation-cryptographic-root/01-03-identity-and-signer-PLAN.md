---
phase: 01-foundation-cryptographic-root
plan: 03
type: execute
wave: 3
depends_on: [02]
files_modified:
  - python/src/wbauth/__init__.py
  - python/src/wbauth/identity.py
  - python/src/wbauth/signer.py
  - python/src/wbauth/normalized_request.py
  - python/src/wbauth/cli.py
  - python/src/wbauth/_redaction.py
  - python/tests/test_identity.py
  - python/tests/test_signer.py
  - python/tests/test_cli.py
autonomous: true
requirements: [IDENT-01, IDENT-02, IDENT-03, IDENT-06, IDENT-07, IDENT-08]

must_haves:
  truths:
    - "Identity.load_or_generate(path, signature_agent_url='https://...') returns a long-lived Identity with Ed25519 keypair (IDENT-02)"
    - "Generating a new key writes the file via os.open(O_WRONLY|O_CREAT|O_EXCL, 0o600), race-free; mode is 0o600 on POSIX (IDENT-01)"
    - "Loading a key file with mode wider than 0o600 raises PermissionError with remediation message before reading any bytes (IDENT-01)"
    - "identity.kid returns base64url-no-pad SHA-256 of canonical Ed25519 JWK per RFC 7638; for the RFC 9421 Appendix B.1.4 test key, kid == 'poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U' (IDENT-06)"
    - "identity.export_jwks() returns {'keys':[...]} with one entry (active only) or two entries (active + retiring) (IDENT-06, IDENT-07)"
    - "Identity.rotate(new_path) returns a new Identity whose _active is the new key and _retiring is the previously-active; double rotation drops the oldest (IDENT-07)"
    - "repr(identity) and str(identity) return '<Identity REDACTED kid=... sig_agent=...>' — no key material leaks (IDENT-08)"
    - "pickle.dumps(identity) raises TypeError (IDENT-08)"
    - "sign(NormalizedRequest, Identity) produces RFC 9421 Signature + Signature-Input + Signature-Agent headers using tag='web-bot-auth', expires=created+60s, covered_components=('@authority','signature-agent'), Ed25519 (IDENT-03)"
    - "Signature-Agent header value is the URL wrapped in double quotes (RFC 8941 Structured Field); signer raises ValueError if URL is not https://"
    - "wbauth keygen --output <path> generates a keypair, prints kid, returns exit 0 (IDENT-01 CLI half)"
  artifacts:
    - path: python/src/wbauth/identity.py
      provides: "Identity class, KeyPair dataclass, _compute_kid, load/generate"
      contains: "class Identity"
      min_lines: 150
    - path: python/src/wbauth/signer.py
      provides: "sign() pure function with Web Bot Auth defaults; SignatureHeaders dataclass"
      contains: "def sign"
      min_lines: 70
    - path: python/src/wbauth/normalized_request.py
      provides: "NormalizedRequest dataclass — input shape of sign()"
      contains: "class NormalizedRequest"
    - path: python/src/wbauth/cli.py
      provides: "argparse CLI; wbauth keygen subcommand"
      contains: "def main"
    - path: python/src/wbauth/_redaction.py
      provides: "REDACTED repr/str helper used by Identity"
    - path: python/tests/test_identity.py
      provides: "Tests for IDENT-01, 02, 06, 07, 08"
    - path: python/tests/test_signer.py
      provides: "Tests for IDENT-03 — Web Bot Auth profile defaults"
    - path: python/tests/test_cli.py
      provides: "Tests for wbauth keygen CLI (IDENT-01 CLI half)"
  key_links:
    - from: "python/src/wbauth/__init__.py"
      to: "Identity, sign, SignatureHeaders, NormalizedRequest"
      via: "re-export"
      pattern: "from \\.identity import Identity"
    - from: "python/src/wbauth/signer.py"
      to: "http_message_signatures.HTTPMessageSigner"
      via: "delegated signing"
      pattern: "from http_message_signatures import"
    - from: "python/src/wbauth/identity.py"
      to: "cryptography.hazmat.primitives.asymmetric.ed25519"
      via: "Ed25519PrivateKey.generate / load"
      pattern: "Ed25519PrivateKey"
    - from: "python/src/wbauth/cli.py"
      to: "Identity.load_or_generate"
      via: "wbauth keygen subcommand"
      pattern: "Identity\\.load_or_generate"
---

<objective>
Implement the cryptographic root: Identity class, pure-function sign(), JWKS thumbprint per RFC 7638, multi-key rotation, REDACTED repr/str, and `wbauth keygen` CLI. Satisfies IDENT-01, IDENT-02, IDENT-03, IDENT-06, IDENT-07, IDENT-08.

Purpose: Per ROADMAP, "the cryptographic root that gates every downstream feature." Plan 04 validates output against test vectors and Cloudflare's debug verifier. Phase 2 wraps this signer in HTTP-client adapters. Phase 4's TS SDK will be byte-equivalent. Wrong here = every downstream feature broken.

Output: A complete `python/src/wbauth/` module that generates Ed25519 keys with strict 0o600 race-free writes, refuses to load files with mode > 0o600 on POSIX, computes RFC 7638 thumbprint (verified against canonical kid `poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U`), exports JWKS with one or two keys, returns REDACTED for repr/str, refuses pickling, signs requests via `http-message-signatures` 2.0.1 with Web Bot Auth defaults, and ships a `wbauth keygen` CLI. CI runs all tests every push via Plan 02's python.yml workflow.
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
@.planning/phases/01-foundation-cryptographic-root/01-02-SUMMARY.md
@python/pyproject.toml
@python/src/wbauth/__init__.py

<interfaces>
<!-- Canonical implementation code lives in 01-RESEARCH.md §3 (Identity) and §4 (Signer).
     Use those code blocks verbatim and only deviate where this plan explicitly says so. -->

Source-of-truth references in 01-RESEARCH.md:
- §3 "Identity API Implementation Reference" — full identity.py source
- §4 "Signer Implementation Reference" — full signer.py source
- §"Code Examples" → "Compute kid (RFC 7638 thumbprint)" and "Generate a key with strict 0o600"
- §3 "CLI for IDENT-01" — cli.py source. **MODIFICATION:** rename argparse program from `agentid` to `wbauth` (Plan 02 already updated REQUIREMENTS.md and pyproject.toml script entry to `wbauth = "wbauth.cli:main"`).

Module constants (HARD-CODE — not magic strings):
```
WEB_BOT_AUTH_TAG = "web-bot-auth"        # Pitfall 6 — typo = silent CF reject
DEFAULT_LABEL = "sig1"                   # canonical signature label
DEFAULT_EXPIRES_SECONDS = 60             # 30 too short per Pitfall 3
DEFAULT_COMPONENTS = ("@authority", "signature-agent")
DEFAULT_KEY_PATH = Path("~/.config/wbauth/key.pem").expanduser()
```

Test key (publicly known, RFC 9421 Appendix B.1.4):
```
TEST_KEY_D = "n4Ni-HpISpVObnQMW0wOhCKROaIKqKtW_2ZYb2p9KcU"   # base64url no padding
TEST_KEY_X = "JrQLj5P_89iXES9-vFgrIy29clF9CC_oPPsw3c5D0bs"   # base64url no padding
TEST_KEY_KID = "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U" # expected SHA-256 thumbprint
```

NormalizedRequest dataclass:
```python
from dataclasses import dataclass

@dataclass(frozen=False)   # mutable: HTTPMessageSigner.sign() mutates request.headers in place
class NormalizedRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: bytes | None = None
```

SignatureHeaders dataclass (lives in signer.py):
```python
@dataclass(frozen=True)
class SignatureHeaders:
    signature: str
    signature_input: str
    signature_agent: str
```

Final `python/src/wbauth/__init__.py`:
```python
"""wbauth: Web Bot Auth (RFC 9421) Python SDK."""
from .identity import Identity, KeyPair
from .normalized_request import NormalizedRequest
from .signer import sign, SignatureHeaders

__version__ = "0.1.0"
__all__ = ["Identity", "KeyPair", "sign", "SignatureHeaders", "NormalizedRequest", "__version__"]
```

Implementation-time uncertainties from RESEARCH §"Open Questions" + §"Assumptions Log" — verify in Task 2 and document outcomes in SUMMARY:
- A3: `algorithms.ED25519` should emit `alg="ed25519"` (lowercase). If not, wrap algorithm class.
- A4: `_IdentityResolver.resolve_private_key()` returning `Ed25519PrivateKey` should work. If library wants raw bytes, return `private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())` (32 bytes).
- A6: `tag="web-bot-auth"` should appear with double quotes in Signature-Input. If bare `tag=web-bot-auth`, manually quote.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Implement Identity, KeyPair, NormalizedRequest, _redaction with strict key handling and JWKS thumbprint</name>
  <read_first>
    - python/src/wbauth/__init__.py (Plan 02 stub — will be partially updated)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §3 "Identity API Implementation Reference" (verbatim source)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §"Pitfalls" 4 (key leakage), 8 (Windows chmod no-op)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §"Code Examples" → "Compute kid" + "Generate a key with strict 0o600"
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §"Security Domain" V6/V7/V8
  </read_first>
  <behavior>
    Test-first behaviors (1:1 with test functions in `python/tests/test_identity.py`):

    - test_kid_matches_rfc9421_test_key: `Identity.from_test_key("https://example.test/")` produces `kid == "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U"`. [IDENT-06]
    - test_load_or_generate_creates_new_key: against non-existent path generates a key; file mode is 0o600 on POSIX. [IDENT-01]
    - test_generate_uses_o_excl_no_overwrite: `_generate_keypair_to(existing_path)` raises FileExistsError. [IDENT-01]
    - test_load_refuses_world_readable: file with chmod 0o644 → PermissionError mentioning "0o644" and "chmod 600 <path>". SKIP on Windows. [IDENT-01]
    - test_load_existing_returns_same_kid: generate, then load — same kid. [IDENT-02]
    - test_signature_agent_url_must_be_https: `Identity(..., signature_agent_url="http://...")` → ValueError. [Pitfall 1]
    - test_export_jwks_one_key_when_no_retiring: `len(id.export_jwks()["keys"]) == 1`; entry's kid == id.kid. [IDENT-06]
    - test_export_jwks_two_keys_after_rotation: `id2 = id.rotate(new_path)` → 2 keys; first is new active, second is now-retiring. [IDENT-07]
    - test_double_rotation_drops_oldest: `id3 = id2.rotate(...)` → 2 keys (id3 + id2); original id.kid gone. [IDENT-07]
    - test_repr_returns_REDACTED: `repr(identity)` matches `r"^<Identity REDACTED kid='[A-Za-z0-9_-]{43}' sig_agent='https://[^']+'>$"` and contains literal "REDACTED". [IDENT-08]
    - test_str_returns_REDACTED: `str(identity) == repr(identity)`. [IDENT-08]
    - test_pickle_raises: `pickle.dumps(identity)` raises TypeError. [IDENT-08]
    - test_from_test_key_does_not_persist: `from_test_key` writes no files. [IDENT-02]
    - test_load_non_ed25519_raises_typeerror: PEM-encoded RSA key → TypeError "Expected Ed25519". [defensive]
  </behavior>
  <action>
    TDD: write failing tests first, then implement.

    1. Create `python/src/wbauth/normalized_request.py` from `<interfaces>`.

    2. Create `python/src/wbauth/_redaction.py`:
       ```python
       """Helpers for REDACTED repr/str on objects holding key material.
       Greppable for security review: anywhere __repr__/__str__ touch keys, reuse this.
       """

       def redacted_repr(class_name: str, **public_fields) -> str:
           parts = " ".join(f"{k}={v!r}" for k, v in public_fields.items())
           return f"<{class_name} REDACTED {parts}>"
       ```

    3. Write `python/tests/test_identity.py` with all 14 test functions from `<behavior>`. Use `tmp_path`, `pytest.raises`, `re.match`, `import pickle`. Example for the trickiest test:
       ```python
       import sys, pytest
       from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
       from cryptography.hazmat.primitives import serialization

       @pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes only")
       def test_load_refuses_world_readable(tmp_path):
           keyfile = tmp_path / "key.pem"
           pem = Ed25519PrivateKey.generate().private_bytes(
               encoding=serialization.Encoding.PEM,
               format=serialization.PrivateFormat.PKCS8,
               encryption_algorithm=serialization.NoEncryption(),
           )
           keyfile.write_bytes(pem)
           keyfile.chmod(0o644)
           from wbauth import Identity
           with pytest.raises(PermissionError) as exc:
               Identity.load_or_generate(keyfile, signature_agent_url="https://example.test/")
           assert "0o644" in str(exc.value)
           assert "chmod 600" in str(exc.value)
       ```
       Run `uv run pytest python/tests/test_identity.py -v` — expect ImportError (RED step).

    4. Implement `python/src/wbauth/identity.py` from RESEARCH §3 verbatim:
       - `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)` for keyfile creation (race-free, refuses overwrite).
       - On POSIX, `if (os.stat(path).st_mode & 0o777) & 0o077: raise PermissionError(...)` before reading bytes.
       - On Windows (`sys.platform == "win32"`), skip permission check with `warnings.warn(...)`.
       - `_compute_kid`: `json.dumps(jwk, sort_keys=True, separators=(",", ":"))` → SHA-256 → base64url-no-pad.
       - `Identity.__repr__` uses `_redaction.redacted_repr("Identity", kid=self.kid, sig_agent=self.signature_agent_url)`.
       - `Identity.__str__ = __repr__`.
       - `Identity.__reduce__` raises `TypeError("Identity is not pickleable (would leak private key material)")`.
       - `Identity.from_test_key(signature_agent_url)`: pad b64url then `Ed25519PrivateKey.from_private_bytes(base64.urlsafe_b64decode(TEST_KEY_D + "="*(-len(TEST_KEY_D) % 4)))`.
       - `Identity.rotate(new_path)`: generate new keypair, return new Identity with `_active=new`, `_retiring=self._active` (drops anything currently in `_retiring`).

       Run `uv run pytest python/tests/test_identity.py -v` — all 14 tests should PASS (GREEN step).

    5. Update `python/src/wbauth/__init__.py` partially (signer comes in Task 2):
       ```python
       from .identity import Identity, KeyPair
       from .normalized_request import NormalizedRequest
       __version__ = "0.1.0"
       __all__ = ["Identity", "KeyPair", "NormalizedRequest", "__version__"]
       # Task 2 will add: from .signer import sign, SignatureHeaders
       ```
  </action>
  <verify>
    <automated>uv run pytest python/tests/test_identity.py -v --tb=short &amp;&amp; uv run python -c "from wbauth import Identity; i = Identity.from_test_key('https://example.test/'); assert i.kid == 'poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U'; assert 'REDACTED' in repr(i); print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `python/src/wbauth/identity.py` exists, ≥150 lines, defines `Identity` with `load_or_generate`, `from_test_key`, `rotate`, `kid` property, `export_jwks`, `__repr__`, `__str__`, `__reduce__`
    - `python/src/wbauth/normalized_request.py` exists with `NormalizedRequest` dataclass (mutable headers dict)
    - `python/src/wbauth/_redaction.py` exists with `redacted_repr` helper
    - `python/tests/test_identity.py` has all 14 test functions from `<behavior>`
    - `uv run pytest python/tests/test_identity.py -v` exits 0
    - `Identity.from_test_key('https://example.test/').kid == 'poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U'`
    - `repr(identity)` contains "REDACTED" and never the private key bytes
    - `pickle.dumps(identity)` raises TypeError
    - `grep -q "O_EXCL" python/src/wbauth/identity.py` succeeds (race-free keyfile creation)
    - Loading 0o644 file raises PermissionError with "0o644" and "chmod 600" in message
  </acceptance_criteria>
  <done>
    Identity, KeyPair, NormalizedRequest implemented and tested. RFC 7638 thumbprint produces canonical value. Key file safety enforced. REDACTED guarantees verified. Multi-key rotation works.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement sign() pure function with Web Bot Auth profile defaults</name>
  <read_first>
    - python/src/wbauth/identity.py (just created — `_active.private_key` access pattern)
    - python/src/wbauth/normalized_request.py (just created — input shape)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §4 "Signer Implementation Reference" (verbatim source)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §"Code Examples" → "Sign a request"
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §"Pitfalls" 1, 2, 3, 6
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §"Open Questions" Q1, Q2, Q6 + §"Assumptions Log" A3, A4, A6
  </read_first>
  <behavior>
    Test functions for `python/tests/test_signer.py`:

    - test_sign_produces_three_headers: returns `SignatureHeaders` with non-empty `signature`, `signature_input`, `signature_agent` AND mutates `req.headers` to include all three. [IDENT-03]
    - test_signature_agent_is_double_quoted: `result.signature_agent == f'"{identity.signature_agent_url}"'`. [Pitfall 1]
    - test_tag_appears_in_signature_input: `'tag="web-bot-auth"'` substring present. [Pitfall 6 + IDENT-03]
    - test_alg_appears_in_signature_input: `'alg="ed25519"'` substring present (verifies A3). [IDENT-03]
    - test_keyid_appears_in_signature_input: `f'keyid="{identity.kid}"'` substring present. [IDENT-03 + IDENT-06]
    - test_default_components_are_authority_and_signature_agent: regex `r'\("@authority" "signature-agent"\)'` matches Signature-Input. [IDENT-03 + Pitfall 2]
    - test_default_expires_is_60_seconds: with fixed `created`, `expires - created == 60`. [Pitfall 3]
    - test_custom_expires_after_seconds: `expires_after_seconds=300` → diff is 300. [parameter plumbing]
    - test_post_with_body_adds_content_digest_component: POST with body has `"content-digest"` in components. [IDENT-03]
    - test_get_does_not_add_content_digest: GET without body does NOT include `"content-digest"`. [symmetry]
    - test_signature_value_is_deterministic: same key + same created + same nonce → identical Signature bytes. [IDENT-04 prep]
    - test_label_is_sig1_by_default: `signature_input.startswith("sig1=")` and `signature.startswith("sig1=")`.
    - test_signer_does_not_leak_key: capture stdout/stderr — neither contains TEST_KEY_D bytes. [IDENT-08 + Pitfall 4]

    Implementation-time verifications (perform during this task; document outcomes in SUMMARY):
    - A3: dump first signature_input — confirm `alg="ed25519"` literally. If different, wrap algorithm class.
    - A4: if `_IdentityResolver.resolve_private_key()` returning `Ed25519PrivateKey` causes TypeError, change to return raw bytes via `.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())`.
    - A6: confirm `tag="web-bot-auth"` (with quotes). If bare, manually quote.
  </behavior>
  <action>
    TDD: write failing tests first.

    1. Write `python/tests/test_signer.py` with all 13 functions from `<behavior>`. Helper for parsing Signature-Input parameters:
       ```python
       import re

       def get_param(sig_input: str, name: str) -> str | None:
           m = re.search(rf';{re.escape(name)}="([^"]+)"', sig_input)
           if m: return m.group(1)
           m = re.search(rf';{re.escape(name)}=(\d+)', sig_input)
           return m.group(1) if m else None
       ```
       Use a fixed timestamp + nonce for determinism:
       ```python
       import datetime
       FIXED_CREATED = datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
       FIXED_NONCE = "test-nonce-fixed"
       ```
       Run `uv run pytest python/tests/test_signer.py -v` — RED (ImportError).

    2. Implement `python/src/wbauth/signer.py` from RESEARCH §4:
       - Constants exactly per `<interfaces>` block.
       - `_IdentityResolver` returns `identity._active.private_key` (the `Ed25519PrivateKey` object); if A4 fails, wrap with `.private_bytes(...)`.
       - `_components_for(method, has_body)`: returns base + `("content-digest",)` if `has_body and method.upper() in ("POST","PUT","PATCH")`.
       - `sign()` signature: `def sign(request, identity, *, created=None, expires_after_seconds=DEFAULT_EXPIRES_SECONDS, nonce=None, label=DEFAULT_LABEL) -> SignatureHeaders`
       - First action: `if not identity.signature_agent_url.startswith("https://"): raise ValueError(...)`; then `request.headers["Signature-Agent"] = f'"{identity.signature_agent_url}"'`.
       - If `nonce is None`, `nonce = secrets.token_urlsafe(16)`.
       - If `created is None`, `created = datetime.datetime.now(datetime.timezone.utc)`.
       - `expires = created + datetime.timedelta(seconds=expires_after_seconds)`.
       - Construct `HTTPMessageSigner(signature_algorithm=algorithms.ED25519, key_resolver=_IdentityResolver(identity))`.
       - Call `.sign(request, key_id=identity.kid, created=created, expires=expires, nonce=nonce, label=label, tag=WEB_BOT_AUTH_TAG, covered_component_ids=_components_for(request.method, has_body))` where `has_body = bool(getattr(request, "body", None))`.
       - Return `SignatureHeaders(signature=..., signature_input=..., signature_agent=...)` from `request.headers`.

       Define `SignatureHeaders` in this same file (frozen dataclass per `<interfaces>`).

       Run `uv run pytest python/tests/test_signer.py -v`. Apply A3/A4/A6 wraps as needed until GREEN.

    3. At top of `signer.py`, add a comment recording the verified library behavior:
       ```
       # Implementation-time verifications (Plan 03):
       # - http-message-signatures 2.0.1 emits alg="..." [confirmed/wrapped — record outcome]
       # - _IdentityResolver returning Ed25519PrivateKey directly [confirmed/changed to bytes]
       # - tag="web-bot-auth" appears with double quotes [confirmed/manually wrapped]
       ```

    4. Update `python/src/wbauth/__init__.py` to add signer re-exports (final form per `<interfaces>`).

    5. Smoke-test the full surface (this is a single-line python -c, kept minimal to avoid quoting hell):
       ```bash
       uv run python -c "from wbauth import Identity, NormalizedRequest, sign; i = Identity.from_test_key('https://example.test/'); req = NormalizedRequest(method='GET', url='https://crawltest.com/cdn-cgi/web-bot-auth', headers={}); h = sign(req, i); assert 'web-bot-auth' in h.signature_input and 'ed25519' in h.signature_input; print('signer OK')"
       ```
  </action>
  <verify>
    <automated>uv run pytest python/tests/test_signer.py -v --tb=short &amp;&amp; uv run python -c "from wbauth import Identity, NormalizedRequest, sign; i = Identity.from_test_key('https://example.test/'); req = NormalizedRequest(method='GET', url='https://crawltest.com/cdn-cgi/web-bot-auth', headers={}); h = sign(req, i); assert 'web-bot-auth' in h.signature_input; assert 'ed25519' in h.signature_input; assert h.signature_agent.startswith('\"') and h.signature_agent.endswith('\"'); print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `python/src/wbauth/signer.py` exists, ≥70 lines, defines `WEB_BOT_AUTH_TAG = "web-bot-auth"` as module constant
    - Imports `from http_message_signatures import HTTPMessageSigner, HTTPSignatureKeyResolver, algorithms`
    - `sign()` is a pure function (no I/O beyond mutating the passed request.headers) with signature matching the action description
    - `SignatureHeaders` is a frozen dataclass with `signature`, `signature_input`, `signature_agent` fields
    - `python/tests/test_signer.py` has all 13 test functions from `<behavior>`
    - `uv run pytest python/tests/test_signer.py -v` exits 0
    - `'tag="web-bot-auth"'` appears literally in the produced Signature-Input (verifies A6 + Pitfall 6)
    - `'alg="ed25519"'` appears literally in the produced Signature-Input (verifies A3)
    - `python/src/wbauth/__init__.py` re-exports `sign`, `SignatureHeaders` alongside `Identity`, `KeyPair`, `NormalizedRequest`
    - `signer.py` head comment records the actual outcome of A3/A4/A6 verifications (text replaces the placeholder `[confirmed/...]`)
  </acceptance_criteria>
  <done>
    sign() implemented and tested. Web Bot Auth defaults baked in. Signature-Agent properly quoted. Implementation-time uncertainties (A3/A4/A6) verified and documented.
  </done>
</task>

<task type="auto">
  <name>Task 3: Implement `wbauth keygen` CLI subcommand and test it via subprocess</name>
  <read_first>
    - python/src/wbauth/identity.py (just created)
    - python/pyproject.toml (script entry: `wbauth = "wbauth.cli:main"`)
    - .planning/phases/01-foundation-cryptographic-root/01-RESEARCH.md §3 "CLI for IDENT-01" (source code — modify program name from `agentid` to `wbauth`)
    - .planning/phases/01-foundation-cryptographic-root/01-CONTEXT.md D-09 (default key path proposal: `~/.config/wbauth/key.pem`)
  </read_first>
  <action>
    Implement `python/src/wbauth/cli.py` and a smoke test via subprocess (so we exercise the actual entry point that pip-installed users would call).

    1. Create `python/src/wbauth/cli.py`:
       ```python
       """wbauth CLI. Phase 1: only `keygen` subcommand. Phase 2: inspect, verify, register, serve."""
       import sys, argparse
       from .identity import Identity, DEFAULT_KEY_PATH


       def main(argv: list[str] | None = None) -> int:
           parser = argparse.ArgumentParser(
               prog="wbauth",
               description="Web Bot Auth (RFC 9421) toolkit for AI agents.",
           )
           sub = parser.add_subparsers(dest="cmd", required=True)

           kg = sub.add_parser("keygen", help="Generate an Ed25519 keypair")
           kg.add_argument("--output", default=str(DEFAULT_KEY_PATH),
                           help=f"Where to write the private key (default: {DEFAULT_KEY_PATH})")
           kg.add_argument("--signature-agent-url", default="https://example.invalid/placeholder",
                           help="Placeholder URL — `wbauth keygen` only needs the kid; "
                                "real value goes into Identity construction in code.")

           args = parser.parse_args(argv)
           if args.cmd == "keygen":
               try:
                   identity = Identity.load_or_generate(
                       args.output, signature_agent_url=args.signature_agent_url
                   )
               except (PermissionError, FileExistsError) as e:
                   print(f"error: {e}", file=sys.stderr)
                   return 2
               print(f"Wrote key to {args.output} (mode 0o600)")
               print(f"kid: {identity.kid}")
               return 0
           return 1


       if __name__ == "__main__":
           sys.exit(main())
       ```

    2. Create `python/tests/test_cli.py` testing both happy path and error path via subprocess (which exercises the entry-point script registered by pyproject.toml):
       ```python
       import subprocess, sys, os, stat


       def test_keygen_creates_key_at_path(tmp_path):
           keyfile = tmp_path / "key.pem"
           result = subprocess.run(
               ["uv", "run", "wbauth", "keygen", "--output", str(keyfile)],
               capture_output=True, text=True,
           )
           assert result.returncode == 0, result.stderr
           assert "Wrote key to" in result.stdout
           assert "kid:" in result.stdout
           assert keyfile.exists()
           if sys.platform != "win32":
               mode = stat.S_IMODE(os.stat(keyfile).st_mode)
               assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


       def test_keygen_prints_kid_to_stdout(tmp_path):
           keyfile = tmp_path / "key.pem"
           result = subprocess.run(
               ["uv", "run", "wbauth", "keygen", "--output", str(keyfile)],
               capture_output=True, text=True,
           )
           assert result.returncode == 0
           # kid is base64url-no-pad SHA-256: 43 chars from [A-Za-z0-9_-]
           kid_lines = [l for l in result.stdout.splitlines() if l.startswith("kid: ")]
           assert len(kid_lines) == 1
           kid = kid_lines[0].removeprefix("kid: ")
           assert len(kid) == 43
           import re
           assert re.fullmatch(r"[A-Za-z0-9_-]{43}", kid)


       def test_keygen_existing_file_errors(tmp_path):
           keyfile = tmp_path / "key.pem"
           keyfile.write_bytes(b"placeholder")
           if sys.platform != "win32":
               keyfile.chmod(0o600)
           result = subprocess.run(
               ["uv", "run", "wbauth", "keygen", "--output", str(keyfile)],
               capture_output=True, text=True,
           )
           # Existing file with placeholder content is not Ed25519 PEM → exit non-zero
           assert result.returncode != 0
           assert "error:" in result.stderr.lower() or result.stderr  # non-empty stderr
       ```

    3. Run the test suite for the whole module to confirm nothing regressed:
       ```bash
       uv run pytest python/tests/ -v
       ```
       All test_identity, test_signer, and test_cli tests should pass.
  </action>
  <verify>
    <automated>uv run pytest python/tests/ -v --tb=short &amp;&amp; OUTDIR=$(mktemp -d) &amp;&amp; uv run wbauth keygen --output "$OUTDIR/key.pem" &gt; /tmp/wbauth_keygen_out.txt 2&gt;&amp;1 &amp;&amp; grep -q "Wrote key to" /tmp/wbauth_keygen_out.txt &amp;&amp; grep -qE "^kid: [A-Za-z0-9_-]{43}$" /tmp/wbauth_keygen_out.txt &amp;&amp; test -f "$OUTDIR/key.pem" &amp;&amp; ([ "$(uname)" = "Windows" ] || [ "$(stat -f '%Lp' "$OUTDIR/key.pem" 2&gt;/dev/null || stat -c '%a' "$OUTDIR/key.pem")" = "600" ])</automated>
  </verify>
  <acceptance_criteria>
    - `python/src/wbauth/cli.py` exists with `def main(argv=None) -> int` entry point
    - `argparse` program name is `wbauth` (not `agentid`); has at least the `keygen` subcommand with `--output` flag
    - `python/tests/test_cli.py` exists with three test functions: happy path, kid format check, existing-file error path
    - `uv run pytest python/tests/ -v` exits 0 (all identity, signer, cli tests pass)
    - `uv run wbauth keygen --output <path>` succeeds, writes key with mode 0o600 on POSIX, prints `Wrote key to ...` and `kid: <43-char-base64url-no-pad>`
    - Error path: `uv run wbauth keygen --output <existing-non-ed25519-file>` exits non-zero with error on stderr
    - Help output (`uv run wbauth --help` and `uv run wbauth keygen --help`) renders without errors
  </acceptance_criteria>
  <done>
    `wbauth keygen` CLI works. `pyproject.toml` script entry resolves correctly. Subprocess tests prove the installed entry-point works (not just direct imports). All Phase 1 cryptographic-root tests green.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| filesystem → Identity | Loading reads PEM bytes from a path; loader enforces 0o600 mode and Ed25519 type before parsing. |
| Identity → process memory | Private key held in a single `Ed25519PrivateKey` object inside `KeyPair`. |
| signer → http_message_signatures library | Pure-function call boundary; no I/O; no env/state. |
| process → log/stderr | `__repr__`/`__str__` return REDACTED; `__reduce__` raises to refuse pickling. |
| CLI → user shell | `wbauth keygen` writes a key file and prints the kid to stdout; private key bytes never reach stdout/stderr. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-03-01 | Information Disclosure | private key leaked via log/stack trace | mitigate | `Identity.__repr__` and `__str__` return REDACTED via `_redaction.redacted_repr`; test `test_repr_returns_REDACTED` enforces. Pitfall 4. |
| T-01-03-02 | Information Disclosure | key file world-readable due to umask | mitigate | `os.open(path, O_WRONLY\|O_CREAT\|O_EXCL, 0o600)` — mode at syscall, no race. Loader refuses mode > 0o600 on POSIX. Test `test_load_refuses_world_readable` enforces. |
| T-01-03-03 | Information Disclosure | key serialized via `pickle.dumps` to a debug log | mitigate | `Identity.__reduce__` raises TypeError; test `test_pickle_raises` enforces. |
| T-01-03-04 | Tampering | overwrite of existing key file (race or bug) | mitigate | `O_EXCL` flag in `os.open` causes `FileExistsError`; `_generate_keypair_to` checks `path.exists()` first; test `test_generate_uses_o_excl_no_overwrite` enforces. |
| T-01-03-05 | Spoofing | `Signature-Agent` URL downgraded to http:// | mitigate | `Identity.__init__` raises ValueError if URL doesn't start with `https://`; `sign()` re-checks defensively; test `test_signature_agent_url_must_be_https` enforces. |
| T-01-03-06 | Tampering | `tag="web-bot-auth"` typo (e.g., `webbotauth`) accepted silently | mitigate | Hard-coded module constant `WEB_BOT_AUTH_TAG`; test `test_tag_appears_in_signature_input` enforces literal string in produced header. Pitfall 6. |
| T-01-03-07 | Spoofing (replay) | signed request reused after intended expiry | mitigate | `expires=created+60` default; `nonce=secrets.token_urlsafe(16)` per signature; both signed parameters. Pitfall 3. |
| T-01-03-08 | Information Disclosure | test fixture using a real production key | mitigate | `Identity.from_test_key` is the ONLY way to construct from publicly-known RFC 9421 Appendix B.1.4 key; docstring says "NEVER use in production"; tests use this exclusively. |
| T-01-03-09 | Tampering | wrong derived components signed (e.g., `@query-params`) | mitigate | `DEFAULT_COMPONENTS = ("@authority", "signature-agent")` — Cloudflare-safe profile only; `_components_for` adds only `content-digest` for bodies; test `test_default_components_are_authority_and_signature_agent` enforces. Pitfall 2. |
| T-01-03-10 | Information Disclosure | retiring key's private bytes returned by resolver | mitigate | `_IdentityResolver.resolve_private_key` returns ONLY `identity._active.private_key`; retiring key is never returned. Verified by code structure (single field accessed). |
| T-01-03-11 | Information Disclosure | non-Ed25519 PEM (e.g., RSA) loaded silently | mitigate | `_load_keypair` raises TypeError("Expected Ed25519, got ...") if `serialization.load_pem_private_key` returns a non-Ed25519 key; test `test_load_non_ed25519_raises_typeerror` enforces. |
</threat_model>

<verification>
1. `uv run pytest python/tests/ -v` exits 0 (all identity, signer, cli tests pass — IDENT-01..03, 06, 07, 08 covered).
2. `uv run python -c "from wbauth import Identity; assert Identity.from_test_key('https://example.test/').kid == 'poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U'"` exits 0 (IDENT-06 against canonical RFC 9421 thumbprint).
3. `uv run wbauth keygen --output /tmp/wbauth-test.pem` succeeds, writes file mode 0o600 on POSIX, prints kid (IDENT-01 CLI half).
4. `grep -q "REDACTED" python/src/wbauth/_redaction.py` succeeds (IDENT-08 mechanism present).
5. `grep -q "O_EXCL" python/src/wbauth/identity.py` succeeds (IDENT-01 race-free creation).
6. `grep -q 'WEB_BOT_AUTH_TAG = "web-bot-auth"' python/src/wbauth/signer.py` succeeds (Pitfall 6 prevention).
7. The signer.py top comment records actual A3/A4/A6 verification outcomes (no `[confirmed/...]` placeholders remain — verifiable via `! grep -q "\\[confirmed/" python/src/wbauth/signer.py`).
</verification>

<success_criteria>
- IDENT-01 satisfied: keygen via Python API + CLI; 0o600; loader refuses wider modes
- IDENT-02 satisfied: long-lived Identity object with keypair + signature_agent_url + user_agent
- IDENT-03 satisfied: pure `sign(NormalizedRequest, Identity) -> SignatureHeaders` with Web Bot Auth profile defaults
- IDENT-06 satisfied: `kid = base64url(sha256(JWK))` per RFC 7638; verified canonical value
- IDENT-07 satisfied: multi-key Identity (active + retiring); rotate() lifecycle; only one overlap
- IDENT-08 satisfied: REDACTED repr/str; pickle refused
- All 30+ tests across test_identity, test_signer, test_cli pass via `uv run pytest`
- Implementation-time uncertainties (A3, A4, A6) resolved and documented in signer.py header comment
- Plan 04 can use `from wbauth import Identity, NormalizedRequest, sign` to author and verify test vectors
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundation-cryptographic-root/01-03-SUMMARY.md` summarizing:
- Files created and line counts
- Test count (should be ~30 across 3 test files)
- Resolution of implementation-time uncertainties:
  - A3: actual `alg=` string emitted (e.g., `"ed25519"` lowercase, or whatever the library produces; document any wrap applied)
  - A4: whether resolver returned `Ed25519PrivateKey` directly or had to wrap with `.private_bytes(...)` raw bytes
  - A6: whether `tag` was auto-quoted by `http_sfv` or required manual wrap
- Confirmation that `Identity.from_test_key(...).kid` matches the canonical RFC 9421 Appendix B.1.4 thumbprint
- Hand-off note to Plan 04: the signer is ready to generate `expected.json` for test vectors per RESEARCH §5
</output>
