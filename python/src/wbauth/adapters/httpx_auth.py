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
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

import httpx

from wbauth.adapters._utils import (
    ensure_content_digest,
    make_sign_decider,
    should_apply_user_agent,
    strip_signature_headers,
)
from wbauth.normalized_request import NormalizedRequest
from wbauth.signer import sign

if TYPE_CHECKING:
    from wbauth.identity import Identity

class RedirectNotSignedWarning(UserWarning):
    """A redirect was followed with ``auth=WebBotAuth`` and could not be re-signed."""


def _sign_request(identity: "Identity", request: httpx.Request, body: bytes | None) -> None:
    headers = dict(request.headers)
    ensure_content_digest(request.method, headers, body)
    cd = next((v for k, v in headers.items() if k.lower() == "content-digest"), None)
    if cd is not None:
        request.headers["Content-Digest"] = cd
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

    def __init__(
        self,
        identity: "Identity",
        *,
        hosts: Iterable[str] | None = None,
        should_sign: Callable[[str], bool] | None = None,
        allow_insecure: bool = False,
    ):
        self._identity = identity
        self._decide = make_sign_decider(hosts, should_sign, allow_insecure)

    def _maybe_sign(self, request: httpx.Request) -> None:
        if self._decide(str(request.url)):
            _sign_request(self._identity, request, request.content or None)
        else:
            strip_signature_headers(request.headers)

    def sync_auth_flow(self, request):
        self._maybe_sign(request)
        response = yield request
        self._check(response)

    async def async_auth_flow(self, request):
        self._maybe_sign(request)
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


class _DecidingTransport:
    def _setup(self, identity, hosts, should_sign, allow_insecure) -> None:
        self._identity = identity
        self._decide = make_sign_decider(hosts, should_sign, allow_insecure)

    def _prepare(self, request: httpx.Request, body: bytes | None) -> None:
        if self._decide(str(request.url)):
            _sign_request(self._identity, request, body)
        else:
            # Never forward the previous hop's signature to a host we don't sign for.
            strip_signature_headers(request.headers)


class SigningTransport(_DecidingTransport, httpx.BaseTransport):
    """Sync transport wrapper that signs at send time — covers every redirect hop.

    ``hosts`` / ``should_sign`` restrict which hosts receive your identity;
    plain-http requests are sent unsigned unless ``allow_insecure=True``.
    """

    def __init__(
        self,
        identity: "Identity",
        transport: httpx.BaseTransport | None = None,
        *,
        hosts: Iterable[str] | None = None,
        should_sign: Callable[[str], bool] | None = None,
        allow_insecure: bool = False,
    ):
        self._setup(identity, hosts, should_sign, allow_insecure)
        self._transport = transport or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        body = request.read() or None
        self._prepare(request, body)
        return self._transport.handle_request(request)

    def close(self) -> None:
        self._transport.close()


class AsyncSigningTransport(_DecidingTransport, httpx.AsyncBaseTransport):
    """Async transport wrapper that signs at send time — covers every redirect hop."""

    def __init__(
        self,
        identity: "Identity",
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        hosts: Iterable[str] | None = None,
        should_sign: Callable[[str], bool] | None = None,
        allow_insecure: bool = False,
    ):
        self._setup(identity, hosts, should_sign, allow_insecure)
        self._transport = transport or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = (await request.aread()) or None
        self._prepare(request, body)
        return await self._transport.handle_async_request(request)

    async def aclose(self) -> None:
        await self._transport.aclose()


def signed_client(
    identity: "Identity",
    *,
    transport: httpx.BaseTransport | None = None,
    hosts: Iterable[str] | None = None,
    should_sign: Callable[[str], bool] | None = None,
    allow_insecure: bool = False,
    **kwargs: Any,
) -> httpx.Client:
    """``httpx.Client`` whose every request **and redirect hop** is signed
    (restricted to ``hosts`` / ``should_sign`` when given)."""
    t = SigningTransport(identity, transport, hosts=hosts, should_sign=should_sign,
                         allow_insecure=allow_insecure)
    return httpx.Client(transport=t, **kwargs)


def signed_async_client(
    identity: "Identity",
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    hosts: Iterable[str] | None = None,
    should_sign: Callable[[str], bool] | None = None,
    allow_insecure: bool = False,
    policy_guard: Any = None,
    respect_policy: bool = False,
    **kwargs: Any,
) -> httpx.AsyncClient:
    """``httpx.AsyncClient`` whose every request **and redirect hop** is signed.

    ``respect_policy=True`` (or an explicit ``policy_guard=PolicyGuard(...)``)
    inspects each origin first: ``forbidden`` raises ``PolicyForbiddenError``
    and robots.txt ``Crawl-delay`` is honoured.
    """
    t: httpx.AsyncBaseTransport = AsyncSigningTransport(
        identity, transport, hosts=hosts, should_sign=should_sign,
        allow_insecure=allow_insecure,
    )
    if policy_guard is None and respect_policy:
        from wbauth.policy.guard import PolicyGuard

        policy_guard = PolicyGuard(user_agent=getattr(identity, "user_agent", None))
    if policy_guard is not None:
        from wbauth.policy.guard import PolicyEnforcingTransport

        t = PolicyEnforcingTransport(policy_guard, t)
    return httpx.AsyncClient(transport=t, **kwargs)
