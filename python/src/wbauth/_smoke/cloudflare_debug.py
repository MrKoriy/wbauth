"""Sign a request with the publicly-known RFC 9421 test key, hit Cloudflare's
OPEN-spec verifier at ``http-message-signatures-example.research.cloudflare.com/``,
assert HTTP 200 + success banner.

Designed to be run as ``python -m wbauth._smoke.cloudflare_debug``. Exits
non-zero on any failure (CI gate per IDENT-05). Prints diagnostic information
to stderr on failure so the CI log is self-explanatory.

Why NOT crawltest.com (the original plan choice):
====================================================

RESEARCH §6 and CONTEXT.md both pointed at ``https://crawltest.com/cdn-cgi/web-bot-auth``
as the exit gate. Empirical investigation during Plan 04 implementation
(2026-05-03) revealed that endpoint is the **closed verified-bots** verifier
which requires the kid to be registered via Cloudflare's Bot Submission Form
(manual dashboard step + Cloudflare-side approval — out of Phase 1 scope).

  $ curl https://crawltest.com/cdn-cgi/web-bot-auth -H 'Signature: <valid-sig>' \\
                                                    -H 'Signature-Input: <...>' \\
                                                    -H 'Signature-Agent: "<jwks>"'
  HTTP/2 401
  unknown public key or unknown verified bot ID for keyid

This 401 happens even though the cryptographic signature is valid AND the kid
is published in the Signature-Agent JWKS — Cloudflare's verified-bots gate
also requires the kid to be in their internal allowlist. Per Cloudflare's
docs (https://developers.cloudflare.com/bots/reference/bot-verification/web-bot-auth/
step 3): "Register your bot and key directory" via Bot Submission Form.

The CORRECT open-spec verifier (verified live):
================================================

``https://http-message-signatures-example.research.cloudflare.com/`` validates
incoming requests against the published RFC 9421 Appendix B.1.4 test key:

- No signature             → 200 + default homepage
- VALID signed request     → 200 + banner "You successfully authenticated as
                              owning the test public key"
- INVALID signed request   → 200 + banner "The Signature you sent does not
                              validate against test public key"

So the verifier ALWAYS returns 200; success/failure is in the response BODY.
This module checks for the success banner and exits non-zero if absent. This
is the actual open-spec exit gate that proves end-to-end RFC 9421 + Web Bot
Auth conformance without depending on Cloudflare's closed verified-bots gate.

Phase 1 hard exit criterion (IDENT-05) restated:
================================================

"Cloudflare's OPEN-SPEC research verifier accepts a request signed by our SDK"
(redirected from crawltest.com to the research server because crawltest.com
is the closed verified-bots gate; verified-bots registration is out of Phase 1
scope and tracked separately in the deferred work).
"""
from __future__ import annotations

import datetime
import sys

import httpx

from wbauth import Identity, NormalizedRequest, sign

CF_RESEARCH_VERIFIER_URL = (
    "https://http-message-signatures-example.research.cloudflare.com/"
)
SUCCESS_BANNER = "You successfully authenticated as owning the test public key"
FAILURE_BANNER = "The Signature you sent does not validate against test public key"


def run() -> int:
    identity = Identity.from_test_key(signature_agent_url=CF_RESEARCH_VERIFIER_URL)
    req = NormalizedRequest(method="GET", url=CF_RESEARCH_VERIFIER_URL, headers={})
    sig = sign(req, identity, created=datetime.datetime.now(datetime.timezone.utc))

    response = httpx.get(
        CF_RESEARCH_VERIFIER_URL,
        headers={
            "Signature": sig.signature,
            "Signature-Input": sig.signature_input,
            "Signature-Agent": sig.signature_agent,
        },
        timeout=10.0,
    )

    # Diagnostic helpers. The verifier always returns 200; the verification
    # result is in the response body. Status != 200 implies network/CDN issue.
    if response.status_code != 200:
        print(
            "FAIL: Cloudflare research verifier returned non-200 (network or CDN issue?).\n"
            f"  status={response.status_code}\n"
            f"  body[:400]={response.text[:400]!r}\n"
            f"  kid={identity.kid}\n"
            f"  Signature-Input={sig.signature_input}\n"
            f"  Signature={sig.signature}\n"
            f"  Signature-Agent={sig.signature_agent}",
            file=sys.stderr,
        )
        return 1

    if FAILURE_BANNER in response.text:
        print(
            "FAIL: Cloudflare research verifier rejected our signature.\n"
            "  banner: 'The Signature you sent does not validate against test public key'\n"
            f"  kid={identity.kid}\n"
            f"  Signature-Input={sig.signature_input}\n"
            f"  Signature={sig.signature}\n"
            f"  Signature-Agent={sig.signature_agent}\n"
            "  Diagnosis: signer regression. Check RESEARCH Pitfalls 1, 2, 6.\n"
            "  Re-run pytest test_signer to confirm regression detection.",
            file=sys.stderr,
        )
        return 1

    if SUCCESS_BANNER not in response.text:
        # Neither banner present — verifier may have changed format.
        print(
            "FAIL: Cloudflare research verifier response unexpected (no success or "
            "failure banner). Verifier may have changed; investigate.\n"
            f"  status={response.status_code}\n"
            f"  body[:600]={response.text[:600]!r}\n"
            f"  kid={identity.kid}",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: Cloudflare research verifier accepted (status=200, kid={identity.kid}, "
        "banner='You successfully authenticated as owning the test public key')"
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
