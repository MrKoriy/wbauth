"""Emit randomized Web Bot Auth-signed requests as JSON (Python → TS check).

    uv run python python/scripts/cross_sign.py 200 > /tmp/py-signed.json
    npx tsx typescript/scripts/cross-verify.ts /tmp/py-signed.json
"""

from __future__ import annotations

import base64
import json
import random
import sys

from wbauth import Identity
from wbauth.adapters._utils import ensure_content_digest
from wbauth.normalized_request import NormalizedRequest
from wbauth.signer import sign


def main(n: int = 100, seed: int = 9421) -> None:
    rnd = random.Random(seed)
    ident = Identity.from_test_key("https://agent.example/.well-known/http-message-signatures-directory")
    out = []
    for i in range(n):
        host = rnd.choice(["example.com", "Crawltest.COM", "a.b.example.org", "[::1]", "127.0.0.1"])
        port = rnd.choice(["", "", ":443", ":8443"])
        path = "/" + "/".join(rnd.choice(["a", "b", "x-y", "%20"]) for _ in range(rnd.randint(0, 3)))
        query = rnd.choice(["", "?q=1", "?a=b&c=d"])
        method = rnd.choice(["GET", "POST", "PUT", "PATCH", "DELETE"])
        body = None if method == "GET" or rnd.random() < 0.3 else rnd.randbytes(rnd.randint(1, 64))
        url = f"https://{host}{port}{path}{query}"
        headers: dict = {}
        ensure_content_digest(method, headers, body)
        req = NormalizedRequest(method=method, url=url, headers=headers, body=body)
        sign(req, ident, nonce=base64.b64encode(rnd.randbytes(64)).decode())
        out.append({
            "id": i, "method": method, "url": url, "headers": dict(req.headers),
            "body_b64": base64.b64encode(body).decode() if body else None,
        })
    json.dump({"jwks": ident.export_jwks(), "requests": out}, sys.stdout)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 100)
