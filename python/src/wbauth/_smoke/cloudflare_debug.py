"""Sign a request with the publicly-known RFC 9421 test key, hit Cloudflare's
OPEN-spec verifier at ``http-message-signatures-example.research.cloudflare.com/``,
assert HTTP 200 + success banner.

Designed to be run as ``python -m wbauth._smoke.cloudflare_debug``. Exits
non-zero on any failure (CI gate per IDENT-05). Prints diagnostic information
to stderr on failure so the CI log is self-explanatory.

Plan 02-03 refactor (preserves Phase-1 behavior):

The original ``run() -> int`` did sign + GET + parse-banner inline. Plan 02-03
introduces ``wbauth verify --domain <domain>`` (CLI-03), which needs the
same machinery returning a structured dict instead of printing diagnostics.
We split the shared probe into ``_probe_verifier(identity) -> dict`` and add
``run_against_domain(domain, identity_path) -> dict`` for the CLI; ``run()``
is preserved 1:1 for the daily cron at ``.github/workflows/cloudflare-debug.yml``
(it now calls ``_probe_verifier`` internally and produces identical output).

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

import asyncio
import datetime
import sys

import httpx

from wbauth import Identity, NormalizedRequest, sign

CF_RESEARCH_VERIFIER_URL = (
    "https://http-message-signatures-example.research.cloudflare.com/"
)
SUCCESS_BANNER = "You successfully authenticated as owning the test public key"
FAILURE_BANNER = "The Signature you sent does not validate against test public key"


async def _probe_verifier(identity: Identity) -> dict:
    """Sign a probe request with ``identity`` and check Cloudflare's research verifier.

    Returns a structured result dict consumed by both ``run()`` (for the daily
    cron diagnostic output) and ``run_against_domain()`` (for the CLI).

    The dict carries ``signature_input`` / ``signature`` / ``signature_agent``
    so ``run()`` can print them on failure for diagnostics; CLI callers
    (``wbauth verify --json``) MUST strip those keys before emitting JSON
    (see T-02-03-02 in the plan's threat model — handled in ``cli.py``).

    Result shape:
      {
        "result":          "pass" | "fail",
        "exit_code":       0 | 2,
        "kid":             "<identity.kid>",
        "status":          <int>,
        "banner":          "<SUCCESS|FAILURE|(no banner)>",
        "verifier_url":    CF_RESEARCH_VERIFIER_URL,
        "signature_input": <str — internal-only, callers must strip>,
        "signature":       <str — internal-only, callers must strip>,
        "signature_agent": <str — internal-only, callers must strip>,
      }
    """
    req = NormalizedRequest(method="GET", url=CF_RESEARCH_VERIFIER_URL, headers={})
    sig = sign(req, identity, created=datetime.datetime.now(datetime.timezone.utc))

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            CF_RESEARCH_VERIFIER_URL,
            headers={
                "Signature": sig.signature,
                "Signature-Input": sig.signature_input,
                "Signature-Agent": sig.signature_agent,
            },
        )

    # Pass only when the verifier explicitly says success AND status is 200.
    # Anything else — failure banner, neither banner, or non-200 — is a fail.
    if response.status_code == 200 and SUCCESS_BANNER in response.text:
        result_kind = "pass"
        banner = SUCCESS_BANNER
    elif FAILURE_BANNER in response.text:
        result_kind = "fail"
        banner = FAILURE_BANNER
    else:
        result_kind = "fail"
        banner = "(no banner)"

    return {
        "result": result_kind,
        "exit_code": {"pass": 0, "fail": 2}[result_kind],
        "kid": identity.kid,
        "status": response.status_code,
        "banner": banner,
        "verifier_url": CF_RESEARCH_VERIFIER_URL,
        "signature_input": sig.signature_input,
        "signature": sig.signature,
        "signature_agent": sig.signature_agent,
    }


async def run_against_domain(
    domain: str, identity_path: str | None = None
) -> dict:
    """Async helper for ``wbauth verify --domain <domain>`` (CLI-03).

    v1: ALWAYS uses ``Identity.from_test_key`` regardless of ``identity_path``
    (open question #5 resolution). The Cloudflare research verifier only
    validates the RFC 9421 Appendix B.1.4 test key; using a real user key
    produces the FAILURE banner. ``identity_path`` is preserved in the
    signature for forward compatibility — Phase 3+ wires it to a
    domain-specific verifier path after directory registration.

    The ``domain`` arg is informational in v1: surfaced in the result dict
    (so ``--json`` consumers see it) but does NOT change the HTTP target
    (always CF_RESEARCH_VERIFIER_URL). The CLI prints a clarifying note.
    """
    identity = Identity.from_test_key(signature_agent_url=CF_RESEARCH_VERIFIER_URL)
    result = await _probe_verifier(identity)
    result["domain"] = domain
    return result


def run() -> int:
    """Phase-1 daily-cron entry. Preserved 1:1 modulo the internal refactor.

    Calls ``_probe_verifier`` and reproduces the original Phase-1 stdout/stderr
    diagnostic shape so ``.github/workflows/cloudflare-debug.yml`` keeps
    working unchanged. Returns 0 on pass, 1 on fail (matches the Phase-1
    contract — NOT the Plan 02-03 CLI exit-code matrix; this entry is for the
    cron, not the user-facing CLI).
    """
    identity = Identity.from_test_key(signature_agent_url=CF_RESEARCH_VERIFIER_URL)
    result = asyncio.run(_probe_verifier(identity))

    # Pass: same OK line as Phase 1 — keeps the cron log shape stable.
    if result["result"] == "pass":
        print(
            f"OK: Cloudflare research verifier accepted (status={result['status']}, "
            f"kid={result['kid']}, banner='{SUCCESS_BANNER}')"
        )
        return 0

    # Fail diagnostics — three sub-cases preserved from the Phase-1 module so
    # the CI log keeps the same self-explanatory shape on regression.
    if result["status"] != 200:
        print(
            "FAIL: Cloudflare research verifier returned non-200 (network or CDN issue?).\n"
            f"  status={result['status']}\n"
            f"  kid={result['kid']}\n"
            f"  Signature-Input={result['signature_input']}\n"
            f"  Signature={result['signature']}\n"
            f"  Signature-Agent={result['signature_agent']}",
            file=sys.stderr,
        )
    elif result["banner"] == FAILURE_BANNER:
        print(
            "FAIL: Cloudflare research verifier rejected our signature.\n"
            "  banner: 'The Signature you sent does not validate against test public key'\n"
            f"  kid={result['kid']}\n"
            f"  Signature-Input={result['signature_input']}\n"
            f"  Signature={result['signature']}\n"
            f"  Signature-Agent={result['signature_agent']}\n"
            "  Diagnosis: signer regression. Check RESEARCH Pitfalls 1, 2, 6.\n"
            "  Re-run pytest test_signer to confirm regression detection.",
            file=sys.stderr,
        )
    else:
        # Neither banner — verifier may have changed shape.
        print(
            "FAIL: Cloudflare research verifier response unexpected (no success or "
            "failure banner). Verifier may have changed; investigate.\n"
            f"  status={result['status']}\n"
            f"  kid={result['kid']}",
            file=sys.stderr,
        )
    # Phase-1 contract: 1 on fail (not 2 — the CLI matrix is separate).
    return 1


if __name__ == "__main__":
    sys.exit(run())
