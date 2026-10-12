"""Shared adapter helpers (internal — not part of the public surface).

The signer auto-includes ``content-digest`` in covered components for
any request with a body; adapters call :func:`ensure_content_digest`
before ``sign()`` so that precondition is met. RFC 9530 sha-256 in
structured-fields form (``sha-256=:<b64>:``).
"""
from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Callable, Iterable, MutableMapping
from urllib.parse import urlsplit

SIGNATURE_HEADERS = frozenset({"signature", "signature-input", "signature-agent"})


# Default UAs set by HTTP libraries. An Identity UA replaces these, but an
# explicit caller-supplied UA always wins.
_LIBRARY_DEFAULT_UA = re.compile(r"^(python-requests|python-httpx|python-urllib)/", re.I)


def ensure_content_digest(method: str, headers: dict, body: bytes | None) -> None:
    """Add ``Content-Digest`` for any request with a non-empty body.

    No-op when the body is empty or the caller
    already supplied a Content-Digest (case-insensitive).
    """
    if not body:
        return
    if not isinstance(body, (bytes, bytearray, memoryview)):
        raise TypeError(
            f"body must be bytes to compute Content-Digest, got {type(body).__name__}"
        )
    digest = hashlib.sha256(body).digest()
    b64 = base64.b64encode(digest).decode("ascii")
    key = next((k for k in headers if k.lower() == "content-digest"), None)
    if key is not None:
        m = re.search(r"(?:^|,)\s*sha-256=:([A-Za-z0-9+/=]+):", headers[key])
        if m is None or m.group(1) == b64:
            return  # caller's own digest (other algorithm) or still correct
        del headers[key]  # stale digest (e.g. a previous redirect hop) — replace
    headers["Content-Digest"] = f"sha-256=:{b64}:"


def strip_signature_headers(headers: MutableMapping[str, str]) -> None:
    """Remove Signature / Signature-Input / Signature-Agent in any casing."""
    for k in [k for k in headers if k.lower() in SIGNATURE_HEADERS]:
        del headers[k]


def make_sign_decider(
    hosts: Iterable[str] | None = None,
    should_sign: Callable[[str], bool] | None = None,
    allow_insecure: bool = False,
) -> Callable[[str], bool]:
    """Build the "sign this URL?" predicate shared by every adapter.

    * Only http(s) URLs with a host are ever signed.
    * Plain ``http://`` is NOT signed unless ``allow_insecure=True`` — a
      signature sent in clear text can be captured and replayed.
    * ``should_sign(url)`` (if given) decides; otherwise ``hosts`` is an
      allow-list (``example.com``, ``*.example.com``); ``None`` = any host.
    """
    allow = list(hosts) if hosts is not None else None

    def decide(url: str) -> bool:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme not in ("http", "https") or not parts.hostname:
            return False
        if scheme == "http" and not allow_insecure:
            return False
        if should_sign is not None:
            return bool(should_sign(url))
        if allow is not None:
            return host_matches(parts.hostname, allow)
        return True

    return decide


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
