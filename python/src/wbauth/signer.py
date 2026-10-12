"""Pure-function signer for Web Bot Auth (RFC 9421).

Implements IDENT-03: `sign(NormalizedRequest, Identity) -> SignatureHeaders` with
the Web Bot Auth profile baked in (Ed25519, tag="web-bot-auth", expires=created+60s,
covered_components=("@authority","signature-agent") + content-digest for bodies).

The signature base is built directly (see ``_sign_fast``) instead of going
through ``http-message-signatures``' generic serializer — same bytes, ~2x
faster. ``@authority`` is normalized per RFC 9421 §2.2.3 (no userinfo, no
default port), matching Cloudflare and the TypeScript SDK.
"""

from __future__ import annotations

import base64
import datetime
import re
import secrets
import urllib.parse
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .identity import Identity
    from .normalized_request import NormalizedRequest

# ---------- Module constants (HARD-CODED — typos = silent Cloudflare reject) ----------

WEB_BOT_AUTH_TAG = "web-bot-auth"
"""IETF Web Bot Auth profile mandate. NEVER change. Pitfall 6."""

DEFAULT_LABEL = "sig1"
"""Canonical Signature label. Most verifier examples assume this."""

DEFAULT_EXPIRES_SECONDS = 60
"""Default expires window. 30s is too short given http-message-signatures'
5s max_clock_skew + network latency. Pitfall 3."""

MAX_EXPIRES_SECONDS = 3600
"""Hard upper bound for the validity window. A long-lived signature is a
replayable bearer credential for every covered (@authority, agent) pair."""

NONCE_BYTES = 64
"""Random bytes in the default nonce (standard base64), matching
web-bot-auth's ``NONCE_LENGTH_IN_BYTES`` and the TypeScript SDK."""

_RESIGN_HEADERS = frozenset({"signature", "signature-input", "signature-agent"})

DEFAULT_COMPONENTS: tuple[str, ...] = ("@authority", "signature-agent")
"""Cloudflare-safe profile. Do NOT add @query-params or @status. Pitfall 2."""

# ---------- Public dataclass ----------


@dataclass(frozen=True)
class SignatureHeaders:
    """The three headers sign() produces, returned for callers that don't want
    to read them out of `request.headers` themselves."""

    signature: str
    signature_input: str
    signature_agent: str


# ---------- Components ----------


def _components_for(method: str, has_body: bool) -> tuple[str, ...]:
    """Pick the covered components for a request.

    Always includes DEFAULT_COMPONENTS. Any request with a non-empty body
    (POST/PUT/PATCH but also DELETE, QUERY, ...) also covers "content-digest"
    so the body cannot be swapped in transit. The caller (or an adapter via
    ``ensure_content_digest``) must set Content-Digest BEFORE calling sign().
    """
    base = list(DEFAULT_COMPONENTS)
    if has_body:
        base.append("content-digest")
    return tuple(base)


# ---------- Fast path (RFC 9421 base built directly) ----------
#
# ``http-message-signatures`` spends >50% of sign() time in its generic
# structured-field serializer. Our profile is fixed (three possible
# components, six well-known parameters), so we can build the exact same
# bytes directly. ``tests/test_signer_fastpath.py`` cross-checks the output
# against the library on randomized inputs.

_SF_KEY_RE = re.compile(r"^[a-z*][a-z0-9_\-.*]*$")
_DEFAULT_PORTS = {"https": 443, "http": 80}


def _sf_string(value: str) -> str:
    """Serialize an RFC 8941 sf-string (printable ASCII only)."""
    if any(not (0x20 <= ord(ch) <= 0x7E) for ch in value):
        raise ValueError(f"value is not a valid structured-field string: {value!r}")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def normalize_authority(url: str) -> str:
    """RFC 9421 §2.2.3 ``@authority``: lower-case host, no userinfo, port only
    when it is not the scheme default. Matches what Cloudflare (and the
    TypeScript SDK via WHATWG ``URL.host``) compute from the ``Host`` header.
    """
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname
    if not host:
        raise ValueError(f"URL has no host: {url!r}")
    if ":" in host:
        host = f"[{host}]"
    port = parts.port
    if port is not None and port != _DEFAULT_PORTS.get(parts.scheme.lower()):
        return f"{host}:{port}"
    return host


def _header(headers, name: str) -> str | None:
    for k, v in headers.items():
        if k.lower() == name:
            return v
    return None


def _sign_fast(
    request: "NormalizedRequest",
    identity: "Identity",
    covered: tuple[str, ...],
    created: datetime.datetime,
    expires: datetime.datetime,
    nonce: str,
    label: str,
) -> tuple[str, str]:
    if not _SF_KEY_RE.match(label):
        raise ValueError(f"label must be an RFC 8941 key, got: {label!r}")
    values = {
        "@authority": normalize_authority(request.url),
        "signature-agent": request.headers["Signature-Agent"],
    }
    if "content-digest" in covered:
        cd = _header(request.headers, "content-digest")
        if cd is None:
            raise ValueError(
                'Covered header field "content-digest" not found in the message. '
                "Use ensure_content_digest() or one of the adapters, which add it."
            )
        values["content-digest"] = cd.strip()
    params = (
        "(" + " ".join(f'"{c}"' for c in covered) + ")"
        f";created={int(created.timestamp())}"
        f";keyid={_sf_string(identity.kid)}"
        ';alg="ed25519"'
        f";expires={int(expires.timestamp())}"
        f";nonce={_sf_string(nonce)}"
        f";tag={_sf_string(WEB_BOT_AUTH_TAG)}"
    )
    base = "\n".join(f'"{c}": {values[c]}' for c in covered)
    base += f'\n"@signature-params": {params}'
    raw_sig = identity._active.private_key.sign(base.encode())
    return f"{label}={params}", f"{label}=:{base64.b64encode(raw_sig).decode()}:"


# ---------- Public API ----------


def sign(
    request: "NormalizedRequest",
    identity: "Identity",
    *,
    created: datetime.datetime | None = None,
    expires_after_seconds: int = DEFAULT_EXPIRES_SECONDS,
    nonce: str | None = None,
    label: str = DEFAULT_LABEL,
) -> SignatureHeaders:
    """Sign a request with the Web Bot Auth profile.

    Mutates `request.headers` in place, adding:
    - `Signature-Agent`: the identity's URL wrapped in double quotes (Pitfall 1).
    - `Signature-Input`: the structured-fields signing parameters.
    - `Signature`: the base64-of-Ed25519-signature value.

    Also returns a `SignatureHeaders` dataclass with the same three values, for
    callers who prefer that shape.

    Args:
        request: a NormalizedRequest. `request.headers` will be mutated.
        identity: the long-lived `Identity` holding the active Ed25519 keypair.
        created: signing timestamp. Defaults to `datetime.now(UTC)`. Override
            for test-vector reproducibility.
        expires_after_seconds: window during which the signature is valid.
            Defaults to 60s; 5s+ NTP slack-safe per Pitfall 3.
        nonce: anti-replay nonce. Defaults to 64 random bytes, base64.
            Override for test-vector reproducibility.
        label: Signature label (the `sig1=` prefix). Defaults to "sig1".

    Raises:
        ValueError: if the identity's signature_agent_url is not https://.
            (Defensive re-check — Identity.__init__ also enforces this.)
    """
    # 1. Defensive URL check (Identity.__init__ enforces this too; duck-typed
    # identities would otherwise leak http:// or break the sf-string). Pitfall 1.
    from .identity import validate_signature_agent_url

    validate_signature_agent_url(identity.signature_agent_url)

    if (
        isinstance(expires_after_seconds, bool)
        or not isinstance(expires_after_seconds, (int, float))
        or not 0 < expires_after_seconds <= MAX_EXPIRES_SECONDS
    ):
        raise ValueError(
            f"expires_after_seconds must be a number in (0, {MAX_EXPIRES_SECONDS}], "
            f"got: {expires_after_seconds!r}"
        )

    # Drop stale signature headers in ANY casing. Retried / redirected
    # requests still carry the previous hop's values; leaving them produces
    # duplicated headers that every verifier rejects.
    for k in [k for k in request.headers if k.lower() in _RESIGN_HEADERS]:
        del request.headers[k]

    # 2. Signature-Agent header (RFC 8941 Structured Field — string in quotes).
    request.headers["Signature-Agent"] = _sf_string(identity.signature_agent_url)

    # 3. Defaults for created/expires/nonce.
    if created is None:
        created = datetime.datetime.now(datetime.timezone.utc)
    expires = created + datetime.timedelta(seconds=expires_after_seconds)
    if nonce is None:
        nonce = base64.b64encode(secrets.token_bytes(NONCE_BYTES)).decode("ascii")

    # 4. Covered components: any non-empty body is bound via content-digest.
    has_body = bool(getattr(request, "body", None))
    covered = _components_for(request.method, has_body)

    # 5. Build the RFC 9421 base and sign it with the active key.
    sig_input, signature = _sign_fast(
        request, identity, covered, created, expires, nonce, label
    )
    request.headers["Signature-Input"] = sig_input
    request.headers["Signature"] = signature

    # 6. Pull the produced headers back out for the typed return value.
    return SignatureHeaders(
        signature=request.headers["Signature"],
        signature_input=request.headers["Signature-Input"],
        signature_agent=request.headers["Signature-Agent"],
    )
