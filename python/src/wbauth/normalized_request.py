"""Input shape for `wbauth.signer.sign()`.

A NormalizedRequest is a dumb dataclass — methods/url/headers/body — that the signer
mutates in place to add the Signature, Signature-Input, and Signature-Agent headers.
This is the canonical request representation across HTTP-client adapters (Phase 2).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NormalizedRequest:
    """A request to be signed.

    The signer mutates `headers` in place (per http_message_signatures' API) and also
    returns a `SignatureHeaders` dataclass for callers that want the values directly.

    Attributes:
        method: HTTP method, e.g. "GET", "POST". Case-preserving — the signer
            normalizes via .upper() where needed.
        url: Absolute request URL. Used for `@authority` derivation.
        headers: Mutable header dict. Signer adds Signature*, Signature-Input,
            Signature-Agent. Caller may pre-populate Content-Digest, etc.
        body: Optional request body bytes. Presence triggers content-digest
            inclusion in the covered components for POST/PUT/PATCH.
    """

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None
