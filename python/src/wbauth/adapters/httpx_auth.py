"""httpx ``Auth`` adapter: signs every request (sync and async clients).

    client = httpx.Client(auth=WebBotAuth(identity))

Each redirect hop is re-signed for its own ``@authority``; stale signature
headers from the previous hop are replaced, never merged.
"""
from __future__ import annotations

import httpx

from wbauth.adapters._utils import ensure_content_digest, should_apply_user_agent
from wbauth.normalized_request import NormalizedRequest
from wbauth.signer import sign


class WebBotAuth(httpx.Auth):
    """Drop-in ``httpx.Auth`` that adds Web Bot Auth signatures."""

    requires_request_body = True  # body must be readable for content-digest

    def __init__(self, identity):
        self._identity = identity

    def sync_auth_flow(self, request):
        self._sign(request)
        yield request

    async def async_auth_flow(self, request):
        self._sign(request)
        yield request  # signing is pure CPU

    def _sign(self, request: httpx.Request) -> None:
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
        if ua and should_apply_user_agent(request.headers.get("user-agent")):
            request.headers["User-Agent"] = ua
