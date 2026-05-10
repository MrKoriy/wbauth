"""httpx.Auth adapter for Web Bot Auth (ADAPT-01).

Delegates crypto to wbauth.sign() (L-02). Stateless per D-15. If
`identity.user_agent` is set AND the outgoing request has no User-Agent
header (case-insensitive), the adapter sets it; otherwise UA is left
untouched (Plan 02-01 open question #4). For POST/PUT/PATCH with a body,
computes Content-Digest if absent (RFC 9530, sha-256).
"""
from __future__ import annotations
import httpx
from wbauth.adapters._utils import ensure_content_digest
from wbauth.normalized_request import NormalizedRequest
from wbauth.signer import sign


class WebBotAuth(httpx.Auth):
    """Drop-in httpx Auth: httpx.Client(auth=WebBotAuth(identity)).get(url).
    Same instance works with httpx.AsyncClient too."""

    requires_request_body = True  # body must be readable for content-digest

    def __init__(self, identity):
        self._identity = identity

    def sync_auth_flow(self, request):
        self._sign(request)
        yield request

    async def async_auth_flow(self, request):
        self._sign(request)
        yield request  # signing is pure CPU

    def _sign(self, request):
        body = request.content if request.content else None
        headers = dict(request.headers)
        ensure_content_digest(request.method, headers, body)
        if "Content-Digest" in headers:
            request.headers["Content-Digest"] = headers["Content-Digest"]
        normalized = NormalizedRequest(
            method=request.method, url=str(request.url),
            headers=headers, body=body,
        )
        sig = sign(normalized, self._identity)
        request.headers["Signature"] = sig.signature
        request.headers["Signature-Input"] = sig.signature_input
        request.headers["Signature-Agent"] = sig.signature_agent
        ua = getattr(self._identity, "user_agent", None)
        if ua and "user-agent" not in {k.lower() for k in request.headers}:
            request.headers["User-Agent"] = ua
