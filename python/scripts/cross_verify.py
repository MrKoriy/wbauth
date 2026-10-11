"""Verify requests signed by the TypeScript SDK (TS → Python check).

    npx tsx typescript/scripts/cross-sign.ts 200 > /tmp/ts-signed.json
    uv run python python/scripts/cross_verify.py /tmp/ts-signed.json
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import urllib.parse

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from http_message_signatures import HTTPMessageVerifier, HTTPSignatureKeyResolver, algorithms
from requests.structures import CaseInsensitiveDict

from wbauth.normalized_request import NormalizedRequest


def _b64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def main(path: str) -> int:
    data = json.load(open(path))
    keys = {k["kid"]: Ed25519PublicKey.from_public_bytes(_b64u(k["x"])) for k in data["jwks"]["keys"]}

    class R(HTTPSignatureKeyResolver):
        def resolve_public_key(self, key_id):
            return keys[key_id]

    verifier = HTTPMessageVerifier(signature_algorithm=algorithms.ED25519, key_resolver=R())
    verifier.max_clock_skew = __import__("datetime").timedelta(days=1)
    failures = 0
    for r in data["requests"]:
        # Verifiers see the Host header, i.e. the normalized authority.
        parts = urllib.parse.urlsplit(r["url"])
        default = {"https": 443, "http": 80}[parts.scheme]
        host = parts.hostname or ""
        host = f"[{host}]" if ":" in host else host
        netloc = host if parts.port in (None, default) else f"{host}:{parts.port}"
        url = urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))
        headers = CaseInsensitiveDict(r["headers"])
        body = base64.b64decode(r["body_b64"]) if r["body_b64"] else None
        try:
            verifier.verify(NormalizedRequest(method=r["method"], url=url, headers=headers, body=body))
            if body is not None:
                want = f"sha-256=:{base64.b64encode(hashlib.sha256(body).digest()).decode()}:"
                assert headers["content-digest"] == want, "content-digest mismatch"
                assert "content-digest" in headers["signature-input"], "digest not covered"
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"FAIL #{r['id']} {r['method']} {r['url']}: {e!r}", file=sys.stderr)
    total = len(data["requests"])
    print(f"python verified {total - failures}/{total} TypeScript-signed requests")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
