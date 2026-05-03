"""Async pre-flight policy inspector (POLICY-01..08).

Public entry point::

    from wbauth import inspect
    policy = await inspect("https://example.com/path")

The inspector fans out four parallel HTTPS GETs (per POLICY-02, each
bounded at 3 s) to the user-supplied origin's well-known endpoints,
parses each response, computes a deterministic strict verdict (D-18),
and returns a frozen ``SitePolicy``.

**Open-question resolutions encoded here** (locked in the planner phase;
documented inline so users don't have to chase the planning docs):

  1. **Redirects** — every well-known fetch passes
     ``follow_redirects=True, max_redirects=3``. Some origins serve
     ``/robots.txt`` via 301 → ``/robots.txt.gz`` etc.; capping at 3 hops
     bounds the worst-case latency while accommodating the common case.

  2. **Robots evaluation** — ``protego.can_fetch(target_url, "wbauth/0.1")``
     is invoked with the **input URL's full path** (not "/"). This answers
     "can I crawl THIS URL?" — matching user intent.

  3. **Cache key** — ``(host, endpoint_name)`` for the parsed result. The
     cache holds ``RobotsResult`` etc.; the verdict (which is path-dependent
     for robots) is computed per-call from the cached parse. This keeps the
     cache compact while remaining RFC 9309-correct.

**POLICY-08 invariant.** Inspector makes ZERO HTTP calls to wbauth-controlled
domains — only to the user-supplied origin. Verified by (a) the grep gate in
the plan's verification step (must return zero non-comment matches for any
wbauth-owned hostname literal) and (b) ``test_only_user_supplied_host_is_fetched``
end-to-end via pytest-httpx.

**Pitfall 7.** The ``httpx.AsyncClient`` is always entered with ``async with``
to ensure the connection pool is closed on every code path (including
exception propagation).
"""
from __future__ import annotations

import asyncio
import datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from .cache import PolicyCache
from .errors import RobotsParseError
from .parsers import (
    parse_ai_txt,
    parse_llms_txt,
    parse_robots,
    parse_signing_directory,
)
from .policy import SitePolicy
from .verdict import compute_verdict

PER_ENDPOINT_TIMEOUT = 3.0  # POLICY-02
USER_AGENT = "wbauth/0.1"   # D-20 — every fetch sends User-Agent: wbauth/0.1
MAX_REDIRECTS = 3           # Open question #1

_ENDPOINT_NAMES = ("robots", "ai_txt", "llms_txt", "signing_directory")

# Module-level cache singleton (D-23: per-process, no persistence).
_CACHE = PolicyCache()


def _reset_cache_for_tests() -> None:
    """Test-only seam: clear the inspector cache between cases.

    Not part of the public API — name is leading-underscore by convention.
    """
    global _CACHE
    _CACHE = PolicyCache()


def _endpoints(host: str) -> dict[str, str]:
    return {
        "robots": f"https://{host}/robots.txt",
        "ai_txt": f"https://{host}/ai.txt",
        "llms_txt": f"https://{host}/llms.txt",
        "signing_directory": (
            f"https://{host}/.well-known/http-message-signatures-directory"
        ),
    }


async def _fetch_one(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """One bounded fetch. Caller wraps in wait_for + gather(return_exceptions=True).

    Raises ``httpx.HTTPStatusError`` on 4xx/5xx (so the verdict engine sees
    the status code in ``errors[endpoint]``).
    """
    response = await client.get(
        url,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return response


async def _fetch_missing(
    host: str, missing: list[str]
) -> dict[str, httpx.Response | BaseException]:
    """Fetch the named endpoints in parallel; isolate per-endpoint failures.

    Returns ``{endpoint_name: Response | Exception}``. ``return_exceptions=True``
    on ``asyncio.gather`` ensures one failed endpoint doesn't tank the others
    (Pitfall 4).
    """
    if not missing:
        return {}
    urls = _endpoints(host)
    async with httpx.AsyncClient(
        timeout=PER_ENDPOINT_TIMEOUT, max_redirects=MAX_REDIRECTS
    ) as client:
        coros = [
            asyncio.wait_for(
                _fetch_one(client, urls[name]), timeout=PER_ENDPOINT_TIMEOUT
            )
            for name in missing
        ]
        results = await asyncio.gather(*coros, return_exceptions=True)
    return dict(zip(missing, results, strict=True))


def _parse_response(name: str, response: httpx.Response, target_url: str) -> Any:
    """Dispatch to the right parser by endpoint name."""
    ct = response.headers.get("content-type")
    if name == "robots":
        return parse_robots(response.text, ct, target_url, USER_AGENT)
    if name == "ai_txt":
        return parse_ai_txt(response.text)
    if name == "llms_txt":
        return parse_llms_txt(response.text)
    if name == "signing_directory":
        return parse_signing_directory(response.text, ct)
    raise ValueError(f"unknown endpoint {name!r}")  # defensive


async def inspect(url: str) -> SitePolicy:
    """Run the pre-flight policy inspector for ``url`` and return a SitePolicy.

    Args:
      url: target URL the agent intends to fetch (must include scheme + host).

    Returns:
      A frozen ``SitePolicy`` with all 9 fields populated per D-17. The
      ``verdict`` is one of ``"allowed"`` / ``"restricted"`` / ``"forbidden"``;
      the ``reasons`` list explains what drove that verdict. ``partial=True``
      iff any endpoint failed (errors keyed by endpoint name in ``errors``).

    Raises:
      ValueError: if the URL has no host component.

    Notes:
      - Errors may include the input URL in their messages; sanitize tokens
        from URLs before passing them to ``inspect()``.
      - Do not pass untrusted URLs (SSRF surface — same trust model as
        ``requests.get(url)``).
    """
    parsed = urlsplit(url)
    host = parsed.netloc
    if not host:
        raise ValueError(f"inspect: URL has no host: {url!r}")

    # 1. Cache lookup per (host, endpoint).
    results: dict[str, Any] = {ep: None for ep in _ENDPOINT_NAMES}
    missing: list[str] = []
    for ep in _ENDPOINT_NAMES:
        entry = _CACHE.get(host, ep)
        if entry is not None:
            results[ep] = entry.value
        else:
            missing.append(ep)

    # 2. Fetch missing endpoints in parallel (POLICY-02 + Pitfall 4).
    fetched = await _fetch_missing(host, missing)

    errors: dict[str, Exception] = {}

    # 3. Parse newly fetched responses + populate cache for successes.
    for ep, fr in fetched.items():
        if isinstance(fr, BaseException):
            # asyncio.TimeoutError → surface as httpx.TimeoutException so the
            # verdict engine's robots-timeout branch matches uniformly.
            if isinstance(fr, asyncio.TimeoutError) and not isinstance(
                fr, httpx.TimeoutException
            ):
                errors[ep] = httpx.TimeoutException(
                    f"{ep} fetch exceeded {PER_ENDPOINT_TIMEOUT}s"
                )
            elif isinstance(fr, Exception):
                errors[ep] = fr
            else:  # pragma: no cover — BaseException not Exception (e.g. CancelledError)
                errors[ep] = RuntimeError(repr(fr))
            continue
        try:
            parsed_value = _parse_response(ep, fr, url)
            results[ep] = parsed_value
            _CACHE.set(
                host,
                ep,
                parsed_value,
                cache_control=fr.headers.get("cache-control"),
                etag=fr.headers.get("etag"),
            )
        except RobotsParseError as e:
            errors[ep] = e  # let verdict engine map to "forbidden"
        except Exception as e:
            errors[ep] = e

    # `partial` reflects unresolved or terminal failures only. A 404 on any
    # endpoint is "absent" not "errored" per the verdict rule table — robots-404
    # is allow-leaning (RFC 9309) and ai/llms/signing-directory-404 are neutral.
    # Treating 404s as partial would trigger the D-18 downgrade and turn every
    # well-behaved minimal site into `restricted`. Errors are still surfaced in
    # `errors` so the verdict engine can read them; partial is the trigger for
    # the strict-philosophy downgrade and should fire only on real failures.
    def _is_partial_failure(exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
            return False
        return True

    partial = any(_is_partial_failure(e) for e in errors.values())
    verdict, reasons = compute_verdict(
        robots=results["robots"],
        ai_txt=results["ai_txt"],
        llms_txt=results["llms_txt"],
        signing_directory=results["signing_directory"],
        errors=errors,
        partial=partial,
    )
    return SitePolicy(
        url=url,
        robots=results["robots"],
        ai_txt=results["ai_txt"],
        llms_txt=results["llms_txt"],
        signing_directory=results["signing_directory"],
        verdict=verdict,
        reasons=reasons,
        partial=partial,
        errors=errors,
        fetched_at=datetime.datetime.now(datetime.timezone.utc),
    )
