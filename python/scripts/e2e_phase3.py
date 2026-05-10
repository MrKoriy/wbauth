"""Phase 3 exit-criterion gate (D-52).

Manual run, NOT CI. Run before tagging Phase 3 complete:

    cd python
    uv run python ../python/scripts/e2e_phase3.py [--directory https://wbauth.silov801.workers.dev]

Steps:
  1. Generate a fresh Identity in a tempdir (real Ed25519 keypair)
  2. Register it with the live Worker via wbauth.cli._do_register
  3. Fetch the JWKS from the registered directory_url and verify it's signed
  4. Sign a probe request via wbauth.sign() with the registered directory URL
  5. POST to Cloudflare research verifier; assess outcome

Outcomes (per 03-RESEARCH.md §8 NOTE):
  - PASS: research verifier returns SUCCESS banner. Full chain validated.
  - PARTIAL: research verifier returns FAILURE banner (verifier limited to test key).
            Steps 1-4 still proved out — internal chain works. Cloudflare-side
            verification deferred to DIST-08 (Phase 5) where we register with
            Cloudflare's verified-bots gate.
  - FAIL: any earlier step (register, fetch, sign) failed. Real bug.

Always writes a result line to stderr with STATUS: PASS|PARTIAL|FAIL plus
diagnostic detail. The wrapper checkpoint task captures stderr into
E2E-RESULT.md.

Note: each successful run leaves a `wbauth-e2e-<kid_prefix>` agent in the
live D1. This is intentional — the registered agents serve as a smoke-test
corpus and discoverability proof. Do NOT clean them up.

Anti-pattern guard: this script MUST NOT be referenced from any
.github/workflows/*.yml file. D-52 is explicit: manual run only. Running on
every CI push spams our own directory and burns the 100k req/day cap.
URL signature for the audit grep: wbauth.silov801.workers.dev
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import sys
import tempfile
from pathlib import Path

import httpx

from wbauth import Identity, NormalizedRequest, sign
from wbauth.cli import _do_register

CF_VERIFIER = "https://http-message-signatures-example.research.cloudflare.com/"
SUCCESS_BANNER = "You successfully authenticated as owning the test public key"
FAILURE_BANNER = "The Signature you sent does not validate against test public key"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--directory",
        default="https://wbauth.silov801.workers.dev",
        help="Directory base URL (default: production Phase 3 Worker).",
    )
    args = parser.parse_args()

    print(f"[setup] Directory: {args.directory}", file=sys.stderr)

    with tempfile.TemporaryDirectory() as td:
        keypath = Path(td) / "key.pem"

        # ---- Step 1: fresh identity --------------------------------------
        # Construct with a placeholder URL just to read .kid (RFC 7638 thumbprint
        # is deterministic from the public key — no server round-trip required).
        # We re-load with the canonical URL after registration in Step 4.
        placeholder_url = (
            f"{args.directory}/.well-known/http-message-signatures-directory/_temp"
        )
        identity = Identity.load_or_generate(
            keypath, signature_agent_url=placeholder_url,
        )
        kid = identity.kid
        print(f"[1/5] Generated kid: {kid}", file=sys.stderr)

        # ---- Step 2: register --------------------------------------------
        try:
            result = await _do_register(
                identity_path=str(keypath),
                directory_url=args.directory,
                client_name=f"wbauth-e2e-{kid[:8]}",
                purpose="Phase 3 E2E exit-criterion test (D-52)",
                client_uri=None,
                expected_user_agent=None,
            )
        except httpx.HTTPStatusError as e:
            print(
                f"[2/5] FAIL: registration HTTP {e.response.status_code} "
                f"{e.response.text[:300]}",
                file=sys.stderr,
            )
            print("STATUS: FAIL (registration step)", file=sys.stderr)
            return 1
        except Exception as e:  # noqa: BLE001 — last-resort error path
            print(f"[2/5] FAIL: {type(e).__name__}: {e}", file=sys.stderr)
            print("STATUS: FAIL (registration step)", file=sys.stderr)
            return 1
        directory_url = result["directory_url"]
        print(f"[2/5] Registered: directory_url={directory_url}", file=sys.stderr)

        # ---- Step 3: fetch + validate JWKS -------------------------------
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                r = await client.get(directory_url)
                r.raise_for_status()
            except Exception as e:  # noqa: BLE001
                print(f"[3/5] FAIL: JWKS fetch {type(e).__name__}: {e}", file=sys.stderr)
                print("STATUS: FAIL (jwks fetch step)", file=sys.stderr)
                return 1
            if "Signature" not in r.headers:
                print("[3/5] FAIL: JWKS response missing Signature header", file=sys.stderr)
                print("STATUS: FAIL (jwks signing step)", file=sys.stderr)
                return 1
            try:
                jwks = r.json()
                if not any(k.get("kid") == kid for k in jwks.get("keys", [])):
                    print(f"[3/5] FAIL: kid {kid} not in fetched JWKS", file=sys.stderr)
                    print("STATUS: FAIL (jwks contents step)", file=sys.stderr)
                    return 1
            except Exception as e:  # noqa: BLE001
                print(f"[3/5] FAIL: JWKS parse {type(e).__name__}: {e}", file=sys.stderr)
                print("STATUS: FAIL (jwks parse step)", file=sys.stderr)
                return 1
            cache_control = r.headers.get("cache-control", "")
            if "immutable" in cache_control:
                # Pitfall 1 regression: if Plan 03-01 accidentally re-introduced
                # 'immutable' on a kid-keyed JWKS endpoint, surface it here.
                print(
                    f"[3/5] WARN: Cache-Control includes 'immutable' (Pitfall 1): {cache_control}",
                    file=sys.stderr,
                )
            print(
                f"[3/5] JWKS fetched + signed (Signature header present, kid present, "
                f"cache-control={cache_control!r})",
                file=sys.stderr,
            )

        # ---- Step 4: sign a probe with the registered URL ----------------
        # Re-load identity with the canonical signature-agent URL (from the
        # registered directory_url) so the signature commits to it.
        identity_canonical = Identity.load_or_generate(
            keypath, signature_agent_url=directory_url,
        )
        req = NormalizedRequest(method="GET", url=CF_VERIFIER, headers={})
        sig = sign(req, identity_canonical, created=datetime.datetime.now(datetime.timezone.utc))
        print(f"[4/5] Signed probe: kid={identity_canonical.kid}", file=sys.stderr)

        # ---- Step 5: POST to Cloudflare research verifier ----------------
        # The verifier is GET-based (returns 200 + a banner in the body).
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                r = await client.get(
                    CF_VERIFIER,
                    headers={
                        "Signature": sig.signature,
                        "Signature-Input": sig.signature_input,
                        "Signature-Agent": sig.signature_agent,
                    },
                )
            except Exception as e:  # noqa: BLE001
                print(f"[5/5] FAIL: verifier POST {type(e).__name__}: {e}", file=sys.stderr)
                print("STATUS: FAIL (verifier network step)", file=sys.stderr)
                return 1

        if r.status_code == 200 and SUCCESS_BANNER in r.text:
            print(f"[5/5] PASS: Cloudflare research verifier accepted (status=200)", file=sys.stderr)
            print("STATUS: PASS", file=sys.stderr)
            return 0
        if r.status_code == 200 and FAILURE_BANNER in r.text:
            # Per 03-RESEARCH.md §8 NOTE — research verifier currently validates ONLY
            # the RFC 9421 test key. Our register→fetch→sign chain proved internally.
            # External verification awaits Phase 5 / DIST-08 (Cloudflare verified-bots).
            print(
                "[5/5] PARTIAL: Cloudflare research verifier returned FAILURE banner.\n"
                "  Internal chain (register->fetch->sign) succeeded; Cloudflare\n"
                "  research verifier currently validates ONLY the RFC 9421 test key\n"
                "  (per Phase 1 plan 04 SUMMARY + 03-RESEARCH.md §8 NOTE). External\n"
                "  end-to-end verification deferred to DIST-08 in Phase 5.",
                file=sys.stderr,
            )
            print("STATUS: PARTIAL", file=sys.stderr)
            # Exit 0 — PARTIAL is an accepted outcome per 03-RESEARCH.md §8 + Open Question
            # rationale; the actual Phase 3 exit criterion is the internal chain working.
            return 0
        print(
            f"[5/5] FAIL: unexpected verifier response status={r.status_code}\n"
            f"  body[:500]={r.text[:500]!r}",
            file=sys.stderr,
        )
        print("STATUS: FAIL (verifier response step)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
