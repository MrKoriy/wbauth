"""Playwright async helper for Web Bot Auth (ADAPT-03).

Registers a page.route handler that intercepts outgoing requests, signs the
matching ones via wbauth.sign(), and continues with the signed headers.
Stateless per D-15; async-only per D-13.

Privacy: without ``hosts`` every http(s) request is signed — including
third-party analytics / CDN hosts, which then learn your agent identity.
Restrict signing to the sites you target::

    await attach_signing(page, identity, hosts=["example.com", "*.example.org"])

Non-http(s) requests (data:, blob:, chrome-extension:) are never signed.
Playwright disables the HTTP cache while a route is active.

PITFALL 6: Call attach_signing(page, identity) BEFORE the first
page.goto()/page.click() that should produce signed requests.

PITFALL 7 (iframe coverage): page.route("**/*", handler) covers all
sub-frame requests by default. If the target site uses Service Workers,
set serviceWorkers="block" on the BrowserContext (Playwright option).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable

from wbauth.adapters._utils import apply_user_agent, ensure_content_digest, make_sign_decider
from wbauth.normalized_request import NormalizedRequest
from wbauth.signer import sign


async def attach_signing(
    page,
    identity,
    *,
    hosts: Iterable[str] | None = None,
    should_sign: Callable[[str], bool] | None = None,
    pattern: str = "**/*",
    allow_insecure: bool = False,
) -> Callable[[], "object"]:
    """Register a route handler on ``page`` that signs matching requests.

    Args:
        hosts: Only sign requests to these hosts (``example.com``,
            ``*.example.com``). ``None`` = sign every http(s) request.
        should_sign: Custom predicate on the request URL; overrides ``hosts``.
        pattern: Route glob passed to ``page.route``.
        allow_insecure: also sign plain ``http://`` requests (off by default).

    Returns:
        An async ``detach()`` callable that removes the route handler.
    """
    _decide = make_sign_decider(hosts, should_sign, allow_insecure)

    async def _handler(route, request):
        if not _decide(request.url):
            fallback = getattr(route, "fallback", None)
            await (fallback() if fallback is not None else route.continue_())
            return
        headers = dict(await request.all_headers())
        body = request.post_data_buffer
        ensure_content_digest(request.method, headers, body)
        normalized = NormalizedRequest(
            method=request.method, url=request.url,
            headers=headers, body=body,
        )
        sig = sign(normalized, identity)
        headers["Signature"] = sig.signature
        headers["Signature-Input"] = sig.signature_input
        headers["Signature-Agent"] = sig.signature_agent
        apply_user_agent(headers, getattr(identity, "user_agent", None))
        await route.continue_(headers=headers)

    await page.route(pattern, _handler)

    async def detach() -> None:
        await page.unroute(pattern, _handler)

    return detach
