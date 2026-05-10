"""Pure-function signer for Web Bot Auth (RFC 9421).

Implements IDENT-03: `sign(NormalizedRequest, Identity) -> SignatureHeaders` with
the Web Bot Auth profile baked in (Ed25519, tag="web-bot-auth", expires=created+60s,
covered_components=("@authority","signature-agent") + content-digest for bodies).

Implementation-time verifications (Plan 03 — performed live against
http-message-signatures 2.0.1 on 2026-05-03):
- A3 confirmed: `algorithms.ED25519` emits `alg="ed25519"` (lowercase) natively
  via the library's `signature_algorithm.algorithm_id` — no wrap needed.
- A4 confirmed: `_IdentityResolver.resolve_private_key()` may return the
  `Ed25519PrivateKey` object directly; no need to unwrap to raw 32 bytes.
- A6 confirmed: `tag="web-bot-auth"` appears with double quotes in the produced
  Signature-Input — the http_sfv library auto-quotes string parameters per
  RFC 8941 Item Parameters.
"""
from __future__ import annotations

import datetime
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

from http_message_signatures import (
    HTTPMessageSigner,
    HTTPSignatureKeyResolver,
    algorithms,
)

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


# ---------- Internal resolver bridging Identity → http-message-signatures ----------


class _IdentityResolver(HTTPSignatureKeyResolver):
    """Adapter from `wbauth.Identity` to the library's resolver interface.

    SECURITY: only ever returns the ACTIVE key's private bytes. The retiring
    key is exported in JWKS for verifiers but is NEVER used to sign new
    requests. T-01-03-10.
    """

    def __init__(self, identity: "Identity"):
        self._identity = identity

    def resolve_private_key(self, key_id: str):
        # Library accepts Ed25519PrivateKey directly (verified A4).
        return self._identity._active.private_key

    def resolve_public_key(self, key_id: str):
        return self._identity._active.private_key.public_key()


def _components_for(method: str, has_body: bool) -> tuple[str, ...]:
    """Pick the covered components for a request.

    Always includes DEFAULT_COMPONENTS. For POST/PUT/PATCH with a body, also
    appends "content-digest" — the caller is responsible for setting the
    Content-Digest header BEFORE calling sign() (Phase 2 will add a helper).
    """
    base = list(DEFAULT_COMPONENTS)
    if has_body and method.upper() in ("POST", "PUT", "PATCH"):
        base.append("content-digest")
    return tuple(base)


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
        nonce: anti-replay nonce. Defaults to 16 random url-safe bytes.
            Override for test-vector reproducibility.
        label: Signature label (the `sig1=` prefix). Defaults to "sig1".

    Raises:
        ValueError: if the identity's signature_agent_url is not https://.
            (Defensive re-check — Identity.__init__ also enforces this.)
    """
    # 1. Defensive https:// check (Identity.__init__ enforces this, but a future
    # caller bypassing the constructor would otherwise leak http://). Pitfall 1.
    if not identity.signature_agent_url.startswith("https://"):
        raise ValueError(
            f"signature_agent_url must be https://, got: "
            f"{identity.signature_agent_url!r}"
        )

    # 2. Set Signature-Agent header (RFC 8941 Structured Field — string in quotes).
    request.headers["Signature-Agent"] = f'"{identity.signature_agent_url}"'

    # 3. Defaults for created/expires/nonce.
    if created is None:
        created = datetime.datetime.now(datetime.timezone.utc)
    expires = created + datetime.timedelta(seconds=expires_after_seconds)
    if nonce is None:
        nonce = secrets.token_urlsafe(16)

    # 4. Determine covered components based on body presence.
    has_body = bool(getattr(request, "body", None))
    covered = _components_for(request.method, has_body)

    # 5. Delegate to http-message-signatures library — it handles signing-base
    # canonicalization, structured-field encoding, and Ed25519 signing.
    signer = HTTPMessageSigner(
        signature_algorithm=algorithms.ED25519,
        key_resolver=_IdentityResolver(identity),
    )
    signer.sign(
        request,
        key_id=identity.kid,
        created=created,
        expires=expires,
        nonce=nonce,
        label=label,
        tag=WEB_BOT_AUTH_TAG,
        covered_component_ids=covered,
    )

    # 6. Pull the produced headers back out for the typed return value.
    return SignatureHeaders(
        signature=request.headers["Signature"],
        signature_input=request.headers["Signature-Input"],
        signature_agent=request.headers["Signature-Agent"],
    )
