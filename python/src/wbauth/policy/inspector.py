"""Async pre-flight policy inspector (POLICY-01..08).

Public entry point::

    from wbauth import inspect
    policy = await inspect("https://example.com/path", user_agent="MyBot/1.0")

The inspector fans out four parallel HTTPS GETs (per POLICY-02, each
bounded at 3 s) to the user-supplied origin's well-known endpoints,
parses each response, computes a deterministic strict verdict (D-18),
and returns a frozen ``SitePolicy``.

Behaviour worth knowing:

  1. **Redirects** — up to 5 hops (RFC 9309 §2.3.1.2). A longer chain means
     robots.txt is treated as *unavailable* (no restriction).
  2. **Robots evaluation** — the parsed rules are cached per host and
     evaluated per call against the **target URL's full path** and the
     caller's ``user_agent``. A cached verdict is never reused across paths.
  3. **Status codes** — 4xx (except 429) = endpoint not published (cached
     negatively); 429 / 5xx / network errors on robots.txt = complete
     disallow (RFC 9309 §2.3.1.4).
  4. **Size caps** — robots.txt is truncated at 500 KiB (RFC 9309 §2.5);
     other endpoints fail with ``FetchError`` above 1 MB. Bodies are
     streamed, so a hostile origin cannot exhaust memory.
  5. **Connection reuse** — pass your own ``httpx.AsyncClient`` (e.g. with
     ``http2=True``) via ``client=`` to reuse connections across calls.

**POLICY-08 invariant.** Inspector makes ZERO HTTP calls to wbauth-controlled
domains — only to the user-supplied origin.
"""
from __future__ import annotations

import asyncio
import datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from .cache import Absent, PolicyCache
from .errors import FetchError, RobotsParseError
from .parsers import (
    parse_ai_txt,
    parse_llms_txt,
    parse_signing_directory,
)
from .parsers.robots import (
    DEFAULT_USER_AGENT,
    RobotsSource,
    evaluate_robots,
    parse_robots_source,
)
from .policy import SitePolicy
from .verdict import compute_verdict, is_unavailable_status

PER_ENDPOINT_TIMEOUT = 3.0  # POLICY-02
USER_AGENT = DEFAULT_USER_AGENT  # back-compat alias
MAX_REDIRECTS = 5           # RFC 9309 §2.3.1.2

ROBOTS_MAX_BYTES = 500 * 1024   # RFC 9309 §2.5 — parse at least 500 KiB, ignore the rest
OTHER_MAX_BYTES = 1_000_000

_ENDPOINT_NAMES = ("robots", "ai_txt", "llms_txt", "signing_directory")

# Module-level singleton cache (D-22). Per-process; tests reset it.
_CACHE = PolicyCache()


def _reset_cache_for_tests() -> None:
    """Reset the module-level cache (test isolation hook)."""
    global _CACHE
    _CACHE = PolicyCache()


def _origin_host(url: str) -> str:
    """Return ``host[:port]`` without userinfo; IPv6 literals bracketed."""
    parsed = urlsplit(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"inspect: URL has no host: {url!r}")
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"inspect: URL must be http(s): {url!r}")
    host = f"[{hostname}]" if ":" in hostname else hostname
    port = parsed.port
    if port and port != 443:
        host = f"{host}:{port}"
    return host.rstrip(".")


def _endpoints(host: str) -> dict[str, str]:
    return {
        "robots": f"https://{host}/robots.txt",
        "ai_txt": f"https://{host}/ai.txt",
        "llms_txt": f"https://{host}/llms.txt",
        "signing_directory": (
            f"https://{host}/.well-known/http-message-signatures-directory"
        ),
    }


_DROP_ON_REBUILD = ("content-encoding", "content-length", "transfer-encoding")


async def _fetch_one(
    client: httpx.AsyncClient, name: str, url: str, user_agent: str
) -> httpx.Response:
    """Stream one endpoint with a byte cap; raise on non-2xx."""
    cap = ROBOTS_MAX_BYTES if name == "robots" else OTHER_MAX_BYTES
    async with client.stream(
        "GET",
        url,
        follow_redirects=True,
        headers={"User-Agent": user_agent},
        timeout=PER_ENDPOINT_TIMEOUT,
    ) as response:
        response.raise_for_status()
        buf = bytearray()
        async for chunk in response.aiter_bytes():
            buf += chunk
            if len(buf) > cap:
                if name == "robots":
                    del buf[cap:]
                    break
                raise FetchError(f"{name} body exceeds {cap} bytes")
        headers = [
            (k, v) for k, v in response.headers.multi_items()
            if k.lower() not in _DROP_ON_REBUILD
        ]
        return httpx.Response(
            response.status_code,
            headers=headers,
            content=bytes(buf),
            request=response.request,
        )


async def _fetch_missing(
    host: str,
    missing: list[str],
    user_agent: str,
    client: httpx.AsyncClient | None,
) -> dict[str, httpx.Response | BaseException]:
    """Fetch every endpoint in ``missing`` in parallel; never raises."""
    if not missing:
        return {}
    urls = _endpoints(host)

    async def run(c: httpx.AsyncClient) -> list[Any]:
        coros = [
            asyncio.wait_for(
                _fetch_one(c, name, urls[name], user_agent),
                timeout=PER_ENDPOINT_TIMEOUT,
            )
            for name in missing
        ]
        return await asyncio.gather(*coros, return_exceptions=True)

    if client is not None:
        results = await run(client)
    else:
        async with httpx.AsyncClient(
            timeout=PER_ENDPOINT_TIMEOUT, max_redirects=MAX_REDIRECTS
        ) as own:
            results = await run(own)
    return dict(zip(missing, results, strict=True))


def _parse_response(name: str, response: httpx.Response) -> Any:
    """Dispatch to the per-endpoint parser (robots returns RobotsSource)."""
    ct = response.headers.get("content-type")
    if name == "robots":
        return parse_robots_source(response.text, ct)
    if name == "ai_txt":
        return parse_ai_txt(response.text)
    if name == "llms_txt":
        return parse_llms_txt(response.text)
    if name == "signing_directory":
        return parse_signing_directory(response.text, ct)
    raise ValueError(f"unknown endpoint {name!r}")  # defensive


def _absent_error(url: str, status: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", url)
    return httpx.HTTPStatusError(
        f"{status} (cached)", request=req, response=httpx.Response(status, request=req)
    )


async def inspect(
    url: str,
    *,
    user_agent: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> SitePolicy:
    """Run the pre-flight inspector against ``url``.

    Args:
        url: Target URL, e.g. ``https://example.com/articles/42``.
        user_agent: The agent's User-Agent. robots.txt rules are evaluated for
            it and it is sent on the policy fetches. Default ``"wbauth/0.1"``.
        client: Optional shared ``httpx.AsyncClient`` for connection reuse.
            It is not closed by ``inspect``.

    Raises:
        ValueError: when the URL is not http(s) or has no host.
    """
    host = _origin_host(url)
    ua = user_agent or DEFAULT_USER_AGENT
    urls = _endpoints(host)

    raw: dict[str, Any] = {ep: None for ep in _ENDPOINT_NAMES}
    errors: dict[str, Exception] = {}
    missing: list[str] = []
    for ep in _ENDPOINT_NAMES:
        entry = _CACHE.get(host, ep)
        if entry is None:
            missing.append(ep)
        elif isinstance(entry.value, Absent):
            errors[ep] = _absent_error(urls[ep], entry.value.status_code)
        else:
            raw[ep] = entry.value

    fetched = await _fetch_missing(host, missing, ua, client)

    for ep, fr in fetched.items():
        if isinstance(fr, BaseException):
            if isinstance(fr, asyncio.TimeoutError) and not isinstance(
                fr, httpx.TimeoutException
            ):
                errors[ep] = httpx.TimeoutException(
                    f"{ep} fetch exceeded {PER_ENDPOINT_TIMEOUT}s"
                )
            elif isinstance(fr, httpx.HTTPStatusError):
                errors[ep] = fr
                status = fr.response.status_code
                if is_unavailable_status(status):
                    _CACHE.set(
                        host, ep, Absent(status),
                        cache_control=fr.response.headers.get("cache-control"),
                    )
            elif isinstance(fr, Exception):
                errors[ep] = fr
            else:  # pragma: no cover — BaseException not Exception (e.g. CancelledError)
                errors[ep] = RuntimeError(repr(fr))
            continue
        try:
            parsed_value = _parse_response(ep, fr)
        except RobotsParseError as e:
            errors[ep] = e  # verdict engine maps to "forbidden"
            continue
        except Exception as e:  # noqa: BLE001 — per-endpoint isolation
            errors[ep] = e
            continue
        raw[ep] = parsed_value
        _CACHE.set(
            host, ep, parsed_value,
            cache_control=fr.headers.get("cache-control"),
            etag=fr.headers.get("etag"),
        )

    robots_src = raw["robots"]
    robots = (
        evaluate_robots(robots_src, url, ua)
        if isinstance(robots_src, RobotsSource)
        else None
    )

    def _is_partial_failure(exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError) and is_unavailable_status(
            exc.response.status_code
        ):
            return False
        return not isinstance(exc, httpx.TooManyRedirects)

    partial = any(_is_partial_failure(e) for e in errors.values())
    verdict, reasons = compute_verdict(
        robots=robots,
        ai_txt=raw["ai_txt"],
        llms_txt=raw["llms_txt"],
        signing_directory=raw["signing_directory"],
        errors=errors,
        partial=partial,
    )
    return SitePolicy(
        url=url,
        robots=robots,
        ai_txt=raw["ai_txt"],
        llms_txt=raw["llms_txt"],
        signing_directory=raw["signing_directory"],
        verdict=verdict,
        reasons=reasons,
        partial=partial,
        errors=errors,
        fetched_at=datetime.datetime.now(datetime.timezone.utc),
    )
