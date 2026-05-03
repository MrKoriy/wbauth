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
4. Asserts `response.status_code == 200`.

## Why no `input.json`/`expected.json`

This vector cannot be byte-equal: the `created` timestamp must be `now()` (within
Cloudflare's clock-skew tolerance), and the `nonce` must be fresh (a 64-byte
random value). The "expected" output is simply HTTP 200 from the Cloudflare
verifier — see `python/src/wbauth/_smoke/cloudflare_debug.py` for the assertion.

## Failure modes (status != 200)

- **400** — malformed signature (most likely a regression in the signer; check
  RESEARCH Pitfalls 1, 2, 6 — Signature-Agent quoting, derived components,
  `tag="web-bot-auth"` literal).
- **401** — key unknown (the JWKS URL was unreachable, OR the kid mismatch —
  verify `Identity.from_test_key(...).kid == "poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U"`
  matches what the CF research server publishes at
  `https://http-message-signatures-example.research.cloudflare.com/.well-known/http-message-signatures-directory`).
- **5xx** — Cloudflare-side outage; retry; if persistent, escalate to Cloudflare
  research team / wait it out (rare).

## How to debug locally

```bash
uv run python -m wbauth._smoke.cloudflare_debug
```

Exits 0 on HTTP 200; exits 1 (with a diagnostic to stderr) on anything else.
