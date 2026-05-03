"""Shared adapter helpers (internal — not part of the public surface).

Phase 1 left a TODO in signer.py:
    "the caller is responsible for setting the Content-Digest header BEFORE
    calling sign() (Phase 2 will add a helper)."

That helper lives here. The signer auto-includes `content-digest` in covered
components for POST/PUT/PATCH requests with a body; if the request hasn't
already set the header, we compute it (RFC 9530 sha-256 in structured-fields
form) so the canonicalization succeeds.
"""
from __future__ import annotations

import base64
import hashlib

_DIGEST_METHODS = ("POST", "PUT", "PATCH")


def ensure_content_digest(method: str, headers: dict, body: bytes | None) -> None:
    """Mutate `headers` in place to add Content-Digest when warranted.

    Adds nothing if:
      - method is not POST/PUT/PATCH,
      - body is None or empty,
      - the request already carries a Content-Digest header (case-insensitive).
    """
    if not body:
        return
    if method.upper() not in _DIGEST_METHODS:
        return
    if any(k.lower() == "content-digest" for k in headers):
        return
    digest = hashlib.sha256(body).digest()
    b64 = base64.b64encode(digest).decode("ascii")
    headers["Content-Digest"] = f"sha-256=:{b64}:"
