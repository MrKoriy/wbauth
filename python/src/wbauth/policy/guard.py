"""PolicyGuard — enforce the pre-flight verdict and Crawl-delay automatically.

    guard = PolicyGuard(user_agent=identity.user_agent)
    async with signed_async_client(identity, policy_guard=guard) as client:
        await client.get("https://example.com/a")   # inspected + paced
        await client.get("https://example.com/b")   # waits Crawl-delay first

* ``forbidden`` → :class:`PolicyForbiddenError` (the request is never sent).
* ``restricted`` → sent by default; pass ``block_restricted=True`` to refuse.
* robots.txt ``Crawl-delay`` (or ``min_delay``) spaces requests per origin.

Only the *async* httpx client is supported: inspection is async I/O.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from .errors import PolicyError
from .inspector import _origin_host, inspect
from .policy import SitePolicy


class PolicyForbiddenError(PolicyError):
    """The site's policy forbids this request; it was not sent."""

    def __init__(self, policy: SitePolicy):
        self.policy = policy
        super().__init__(
            f"{policy.verdict}: {policy.url} — " + "; ".join(policy.reasons[-2:])
        )


class PolicyGuard:
    """Per-origin verdict check + Crawl-delay pacing for outgoing requests."""

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        block_restricted: bool = False,
        min_delay: float = 0.0,
        max_delay: float = 60.0,
        inspect_kwargs: dict[str, Any] | None = None,
    ):
        self.user_agent = user_agent
        self.block_restricted = block_restricted
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._inspect_kwargs = inspect_kwargs or {}
        self._next_slot: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def check(self, url: str) -> SitePolicy:
        """Inspect ``url`` (cached) and raise if the request must not be sent."""
        policy = await inspect(url, user_agent=self.user_agent, **self._inspect_kwargs)
        if policy.verdict == "forbidden" or (
            self.block_restricted and policy.verdict == "restricted"
        ):
            raise PolicyForbiddenError(policy)
        return policy

    async def wait_turn(self, url: str, policy: SitePolicy | None = None) -> None:
        """Sleep until the origin's Crawl-delay since the previous request elapsed."""
        origin = _origin_host(url)
        delay = self.min_delay
        if policy is not None and policy.robots is not None and policy.robots.crawl_delay:
            delay = max(delay, float(policy.robots.crawl_delay))
        delay = min(delay, self.max_delay)
        if delay <= 0:
            return
        lock = self._locks.setdefault(origin, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            slot = self._next_slot.get(origin, now)
            if slot > now:
                await asyncio.sleep(slot - now)
            self._next_slot[origin] = max(slot, now) + delay

    async def before_request(self, url: str) -> None:
        policy = await self.check(url)
        await self.wait_turn(url, policy)


class PolicyEnforcingTransport(httpx.AsyncBaseTransport):
    """Async transport that runs :class:`PolicyGuard` before every hop."""

    def __init__(self, guard: PolicyGuard, transport: httpx.AsyncBaseTransport):
        self._guard = guard
        self._transport = transport

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await self._guard.before_request(str(request.url))
        return await self._transport.handle_async_request(request)

    async def aclose(self) -> None:
        await self._transport.aclose()
