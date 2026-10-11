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
from urllib.parse import urlsplit

from wbauth.adapters._utils import apply_user_agent, ensure_content_digest, host_matches
from wbauth.normalized_request import NormalizedRequest
from wbauth.signer import sign


async def attach_signing(
    page,
    identity,
    *,
    hosts: Iterable[str] | None = None,
    should_sign: Callable[[str], bool] | None = None,
    pattern: str = "**/*",
) -> None:
    """Register a route handler on ``page`` that signs matching requests.

    Args:
        hosts: Only sign requests to these hosts (``example.com``,
            ``*.example.com``). ``None`` = sign every http(s) request.
        should_sign: Custom predicate on the request URL; overrides ``hosts``.
        pattern: Route glob passed to ``page.route``.
    """
    allow = list(hosts) if hosts is not None else None

    def _decide(url: str) -> bool:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return False
        if should_sign is not None:
            return bool(should_sign(url))
        if allow is not None:
            return host_matches(parts.hostname, allow)
        return True

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
