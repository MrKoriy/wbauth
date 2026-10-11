"""Shared adapter helpers (internal — not part of the public surface).

The signer auto-includes ``content-digest`` in covered components for
POST/PUT/PATCH with a body; adapters call :func:`ensure_content_digest`
before ``sign()`` so that precondition is met. RFC 9530 sha-256 in
structured-fields form (``sha-256=:<b64>:``).
"""
from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Iterable, MutableMapping

_DIGEST_METHODS = ("POST", "PUT", "PATCH")

# Default UAs set by HTTP libraries. An Identity UA replaces these, but an
# explicit caller-supplied UA always wins.
_LIBRARY_DEFAULT_UA = re.compile(r"^(python-requests|python-httpx|python-urllib)/", re.I)


def ensure_content_digest(method: str, headers: dict, body: bytes | None) -> None:
    """Add ``Content-Digest`` for POST/PUT/PATCH with a non-empty body.

    No-op when the body is empty, the method carries no body, or the caller
    already supplied a Content-Digest (case-insensitive).
    """
    if not body:
        return
    if method.upper() not in _DIGEST_METHODS:
        return
    if any(k.lower() == "content-digest" for k in headers):
        return
    if not isinstance(body, (bytes, bytearray, memoryview)):
        raise TypeError(
            f"body must be bytes to compute Content-Digest, got {type(body).__name__}"
        )
    digest = hashlib.sha256(body).digest()
    b64 = base64.b64encode(digest).decode("ascii")
    headers["Content-Digest"] = f"sha-256=:{b64}:"


def should_apply_user_agent(current: str | None) -> bool:
    """True when the current UA is absent or a library default."""
    return not current or bool(_LIBRARY_DEFAULT_UA.match(current))


def apply_user_agent(headers: MutableMapping[str, str], user_agent: str | None) -> None:
    """Set ``User-Agent`` unless the caller explicitly chose a non-default one."""
    if not user_agent:
        return
    key = next((k for k in headers if k.lower() == "user-agent"), None)
    current = headers[key] if key is not None else None
    if should_apply_user_agent(current):
        if key is not None:
            del headers[key]
        headers["User-Agent"] = user_agent


def host_matches(hostname: str, allow: Iterable[str]) -> bool:
    """Match ``hostname`` against exact hosts or ``*.example.com`` wildcards.

    A wildcard also matches the bare apex (``*.example.com`` ⊇ ``example.com``).
    """
    h = hostname.lower().rstrip(".")
    for raw in allow:
        a = raw.lower().rstrip(".")
        if a.startswith("*."):
            base = a[2:]
            if h == base or h.endswith("." + base):
                return True
        elif h == a:
            return True
    return False
