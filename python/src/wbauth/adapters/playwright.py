"""Playwright async helper for Web Bot Auth (ADAPT-03).

Registers a page.route handler that intercepts every outgoing request,
signs it via wbauth.sign(), and continues with the signed headers.
Stateless per D-15; async-only per D-13.

PITFALL 6: Call attach_signing(page, identity) BEFORE the first
page.goto()/page.click() that should produce signed requests. page.route
must be registered before navigation begins, or the navigation request
leaves the browser unsigned.

PITFALL 7 (iframe coverage): page.route("**/*", handler) covers all
sub-frame requests by default. If the target site uses Service Workers,
set serviceWorkers="block" on the BrowserContext (Playwright option).
"""
from __future__ import annotations
from wbauth.adapters._utils import ensure_content_digest
from wbauth.normalized_request import NormalizedRequest
from wbauth.signer import sign


async def attach_signing(page, identity) -> None:
    """Register a route handler on `page` that signs every outgoing request.

    Idempotent contract: caller is responsible for calling once per page;
    registering twice yields two handlers and only the first wins
    (Playwright default for overlapping routes).
    """
    async def _handler(route, request):
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
        ua = getattr(identity, "user_agent", None)
        if ua and "user-agent" not in {k.lower() for k in headers}:
            headers["User-Agent"] = ua
        await route.continue_(headers=headers)
    await page.route("**/*", _handler)
