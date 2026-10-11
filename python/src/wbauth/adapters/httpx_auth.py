"""httpx adapters: sign every request (sync and async clients).

Recommended — signs **every hop**, including redirects::

    client = signed_client(identity, follow_redirects=True)
    async_client = signed_async_client(identity)

Drop-in ``auth=`` form::

    client = httpx.Client(auth=WebBotAuth(identity))

**Redirects.** httpx runs an ``Auth`` flow once per ``send()`` and follows
redirects *inside* that flow, so with ``follow_redirects=True`` the redirect
target would receive the first hop's signature (bound to the first host's
``@authority``) — invalid there, and replayable at the first host for the
signature's lifetime. :class:`WebBotAuth` cannot intercept those hops, so it
emits :class:`RedirectNotSignedWarning` when it sees one. Use :func:`signed_client` /
:func:`signed_async_client` (or mount :class:`SigningTransport`) to re-sign
each hop for its own ``@authority``.
"""

from __future__ import annotations

import warnings
from typing import Any

import httpx

from wbauth.adapters._utils import ensure_content_digest, should_apply_user_agent
from wbauth.normalized_request import NormalizedRequest
from wbauth.signer import sign

class RedirectNotSignedWarning(UserWarning):
    """A redirect was followed with ``auth=WebBotAuth`` and could not be re-signed."""


def _sign_request(identity: Any, request: httpx.Request, body: bytes | None) -> None:
    headers = dict(request.headers)
    ensure_content_digest(request.method, headers, body)
    if "Content-Digest" in headers:
        request.headers["Content-Digest"] = headers["Content-Digest"]
    normalized = NormalizedRequest(
        method=request.method, url=str(request.url), headers=headers, body=body
    )
    sig = sign(normalized, identity)
    request.headers["Signature"] = sig.signature
    request.headers["Signature-Input"] = sig.signature_input
    request.headers["Signature-Agent"] = sig.signature_agent
    ua = getattr(identity, "user_agent", None)
    if ua and should_apply_user_agent(request.headers.get("user-agent")):
        request.headers["User-Agent"] = ua


class WebBotAuth(httpx.Auth):
    """Drop-in ``httpx.Auth`` that adds Web Bot Auth signatures."""

    requires_request_body = True  # body must be readable for content-digest

    def __init__(self, identity):
        self._identity = identity

    def sync_auth_flow(self, request):
        _sign_request(self._identity, request, request.content or None)
        response = yield request
        self._check(response)

    async def async_auth_flow(self, request):
        _sign_request(self._identity, request, request.content or None)
        response = yield request  # signing is pure CPU
        self._check(response)

    @staticmethod
    def _check(response: httpx.Response | None) -> None:
        if response is not None and response.history:
            warnings.warn(
                "redirects were followed with auth=WebBotAuth; only hops sent "
                "through wbauth.adapters.signed_client() are re-signed",
                RedirectNotSignedWarning,
                stacklevel=3,
            )

    # Back-compat for callers/tests that used the private helper.
    def _sign(self, request: httpx.Request) -> None:
        _sign_request(self._identity, request, request.content or None)


class SigningTransport(httpx.BaseTransport):
    """Sync transport wrapper that signs at send time — covers every redirect hop."""

    def __init__(self, identity, transport: httpx.BaseTransport | None = None):
        self._identity = identity
        self._transport = transport or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body = request.read() or None
        _sign_request(self._identity, request, body)
        return self._transport.handle_request(request)

    def close(self) -> None:
        self._transport.close()


class AsyncSigningTransport(httpx.AsyncBaseTransport):
    """Async transport wrapper that signs at send time — covers every redirect hop."""

    def __init__(self, identity, transport: httpx.AsyncBaseTransport | None = None):
        self._identity = identity
        self._transport = transport or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = (await request.aread()) or None
        _sign_request(self._identity, request, body)
        return await self._transport.handle_async_request(request)

    async def aclose(self) -> None:
        await self._transport.aclose()


def signed_client(identity, *, transport: httpx.BaseTransport | None = None,
                  **kwargs: Any) -> httpx.Client:
    """``httpx.Client`` whose every request **and redirect hop** is signed."""
    return httpx.Client(transport=SigningTransport(identity, transport), **kwargs)


def signed_async_client(identity, *, transport: httpx.AsyncBaseTransport | None = None,
                        **kwargs: Any) -> httpx.AsyncClient:
    """``httpx.AsyncClient`` whose every request **and redirect hop** is signed."""
    return httpx.AsyncClient(transport=AsyncSigningTransport(identity, transport), **kwargs)
