"""Async pre-flight policy inspector (POLICY-01..08).

Public entry point::

    from wbauth import inspect
    policy = await inspect("https://example.com/path", user_agent="MyBot/1.0")

The inspector fans out four parallel HTTPS GETs (per POLICY-02, each
bounded at 3 s) to the user-supplied origin's well-known endpoints,
parses each response, computes a deterministic strict verdict (D-18),
and returns a frozen ``SitePolicy``.

Behaviour worth knowing:

  1. **Redirects** — followed manually, up to 5 hops (RFC 9309 §2.3.1.2). A
     longer chain means robots.txt is treated as *unavailable*. A redirect
     from a public origin to a loopback / private / link-local address (or
     a non-http(s) scheme) is refused — SSRF guard.
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
  6. **Scheme** — policy files are fetched from the target's own origin
     (scheme, host, port), so ``http://host:8080/x`` reads
     ``http://host:8080/robots.txt`` (RFC 9309 §2.3).
  7. **De-duplication** — concurrent ``inspect()`` calls for the same origin
     share one in-flight fetch per endpoint.
  8. **Revalidation** — expired entries with an ``ETag`` / ``Last-Modified``
     are revalidated with a conditional GET; ``304`` reuses the cached body.

**POLICY-08 invariant.** Inspector makes ZERO HTTP calls to wbauth-controlled
domains — only to the user-supplied origin.
"""
from __future__ import annotations

import asyncio
import datetime
import ipaddress
import json
import os
import re
import socket
import tempfile
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

import httpx

from .cache import Absent, CacheEntry, Failed, PolicyCache, normalize_host
from .errors import FetchError, PrivateAddressError, RobotsParseError
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

FAILURE_TTL = 60.0
"""Network failures/timeouts are negatively cached this long, so a dead
origin does not cost PER_ENDPOINT_TIMEOUT on every inspect() call."""

# Module-level singleton cache (D-22). Per-process; tests reset it.
_CACHE = PolicyCache()


def _reset_cache_for_tests() -> None:
    """Reset the module-level cache (test isolation hook)."""
    global _CACHE
    _CACHE = PolicyCache()
    _INFLIGHT.clear()
    _SHARED_CLIENTS.clear()


def _origin_host(url: str) -> str:
    """Return the cache/origin key: ``host[:port]`` for https (default port
    stripped), ``http://host[:port]`` for plain http. No userinfo; IPv6
    literals bracketed."""
    parsed = urlsplit(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"inspect: URL has no host: {url!r}")
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"inspect: URL must be http(s): {url!r}")
    host = f"[{hostname}]" if ":" in hostname else hostname
    port = parsed.port
    default = 443 if scheme == "https" else 80
    if port and port != default:
        host = f"{host}:{port}"
    host = host.rstrip(".")
    return f"http://{host}" if scheme == "http" else host


def _endpoints(host: str) -> dict[str, str]:
    base = host if host.startswith("http://") else f"https://{host}"
    return {
        "robots": f"{base}/robots.txt",
        "ai_txt": f"{base}/ai.txt",
        "llms_txt": f"{base}/llms.txt",
        "signing_directory": (
            f"{base}/.well-known/http-message-signatures-directory"
        ),
    }


_LEGACY_V4_RE = re.compile(r"^(0x[0-9a-f]+|[0-9]+)(\.(0x[0-9a-f]+|[0-9]+)){0,3}$")


def _ip_is_private(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
        or ip.is_multicast or ip.is_unspecified
    )


def _is_private_host(host: str) -> bool:
    """True for loopback / private / link-local / reserved IP literals and
    ``localhost``-style names. Legacy IPv4 spellings (``2130706433``,
    ``0x7f000001``, ``127.1``) are normalised. Hostnames are not resolved
    here — see :func:`_resolves_private`."""
    h = host.strip("[]").lower().rstrip(".")
    if h == "localhost" or h.endswith((".localhost", ".local", ".internal")):
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        if not _LEGACY_V4_RE.match(h):
            return False
        try:
            ip = ipaddress.ip_address(socket.inet_aton(h))
        except OSError:
            return False
    return _ip_is_private(ip)


async def _resolves_private(host: str) -> bool:
    """True when ``host`` is private by name/literal OR any address it resolves
    to is private (catches ``127.0.0.1.nip.io``-style names). Resolution
    failures return False — the fetch itself will then fail normally."""
    if _is_private_host(host):
        return True
    h = host.strip("[]")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(h, None)
    except (OSError, UnicodeError):
        return False
    for info in infos:
        try:
            if _ip_is_private(ipaddress.ip_address(info[4][0])):
                return True
        except ValueError:
            continue
    return False


_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_DROP_ON_REBUILD = ("content-encoding", "content-length", "transfer-encoding")


async def _fetch_one(
    client: httpx.AsyncClient,
    name: str,
    url: str,
    user_agent: str,
    validators: dict[str, str] | None = None,
    allow_private: bool = True,
) -> httpx.Response:
    """Stream one endpoint with a byte cap; raise on non-2xx (304 passes).

    Redirects are followed by hand so every hop can be vetted (SSRF guard).
    With ``allow_private=False`` the origin itself must also be public
    (by literal and by DNS resolution).
    """
    cap = ROBOTS_MAX_BYTES if name == "robots" else OTHER_MAX_BYTES
    headers = {"User-Agent": user_agent, **(validators or {})}
    current = httpx.URL(url)
    if not allow_private and await _resolves_private(current.host):
        raise PrivateAddressError(f"{name}: private/loopback origin {current.host!r} refused")
    origin_private = allow_private and _is_private_host(current.host)
    for hop in range(MAX_REDIRECTS + 1):
        async with client.stream(
            "GET",
            current,
            follow_redirects=False,
            headers=headers,
            timeout=PER_ENDPOINT_TIMEOUT,
        ) as response:
            if response.status_code in _REDIRECT_CODES and "location" in response.headers:
                if hop == MAX_REDIRECTS:
                    raise httpx.TooManyRedirects(
                        f"{name}: more than {MAX_REDIRECTS} redirects",
                        request=response.request,
                    )
                nxt = current.join(response.headers["location"])
                if nxt.scheme not in ("http", "https"):
                    raise FetchError(f"{name}: redirect to unsupported scheme {nxt.scheme!r}")
                if not origin_private and await _resolves_private(nxt.host):
                    raise PrivateAddressError(
                        f"{name}: redirect to private/loopback address {nxt.host!r} refused"
                    )
                if nxt.host != current.host:
                    headers.pop("If-None-Match", None)
                    headers.pop("If-Modified-Since", None)
                current = nxt
                continue
            if response.status_code == 304:
                return httpx.Response(
                    304, headers=response.headers.multi_items(), request=response.request
                )
            response.raise_for_status()
            buf = bytearray()
            async for chunk in response.aiter_bytes():
                buf += chunk
                if len(buf) > cap:
                    if name == "robots":
                        del buf[cap:]
                        # Never parse a half line: cut at the last newline.
                        nl = buf.rfind(b"\n")
                        if nl >= 0:
                            del buf[nl + 1:]
                        break
                    raise FetchError(f"{name} body exceeds {cap} bytes")
            rebuilt = [
                (k, v) for k, v in response.headers.multi_items()
                if k.lower() not in _DROP_ON_REBUILD
            ]
            return httpx.Response(
                response.status_code,
                headers=rebuilt,
                content=bytes(buf),
                request=response.request,
            )
    raise AssertionError("unreachable")  # pragma: no cover


# (loop id, origin, endpoint, user-agent, allow_private, client id)
#   -> shared in-flight task (single-flight).
_INFLIGHT: dict[tuple, asyncio.Future] = {}

# One pooled AsyncClient per event loop, used when the caller passes none.
# Reusing it saves a TCP+TLS handshake per inspect() and — unlike a
# per-call ``async with`` client — it cannot be closed under a task that a
# concurrent caller is still awaiting.
_SHARED_CLIENTS: dict[int, tuple[asyncio.AbstractEventLoop, httpx.AsyncClient]] = {}


def _shared_client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    for k, (lp, _c) in list(_SHARED_CLIENTS.items()):
        if lp.is_closed():
            _SHARED_CLIENTS.pop(k, None)
    entry = _SHARED_CLIENTS.get(id(loop))
    if entry is None or entry[0] is not loop or entry[1].is_closed:
        try:
            client = httpx.AsyncClient(timeout=PER_ENDPOINT_TIMEOUT, http2=True)
        except ImportError:  # h2 not installed (optional extra)
            client = httpx.AsyncClient(timeout=PER_ENDPOINT_TIMEOUT)
        _SHARED_CLIENTS[id(loop)] = (loop, client)
        return client
    return entry[1]


async def aclose_shared_clients() -> None:
    """Close the pooled client of the running loop (optional cleanup)."""
    entry = _SHARED_CLIENTS.pop(id(asyncio.get_running_loop()), None)
    if entry is not None:
        await entry[1].aclose()


async def _fetch_missing(
    host: str,
    missing: list[str],
    user_agent: str,
    client: httpx.AsyncClient | None,
    validators: dict[str, dict[str, str]] | None = None,
    allow_private: bool = True,
) -> dict[str, httpx.Response | BaseException]:
    """Fetch every endpoint in ``missing`` in parallel; never raises.

    Concurrent callers for the same origin+endpoint+UA share one request.
    The UA is part of the key because origins may vary content by UA.
    """
    if not missing:
        return {}
    urls = _endpoints(host)
    loop_id = id(asyncio.get_running_loop())
    origin = normalize_host(host)
    validators = validators or {}
    c = client if client is not None else _shared_client()

    waits: list[asyncio.Future] = []
    for name in missing:
        key = (loop_id, origin, name, user_agent, allow_private, id(c))
        task = _INFLIGHT.get(key)
        if task is None:
            task = asyncio.ensure_future(
                asyncio.wait_for(
                    _fetch_one(c, name, urls[name], user_agent, validators.get(name),
                               allow_private=allow_private),
                    timeout=PER_ENDPOINT_TIMEOUT,
                )
            )
            _INFLIGHT[key] = task
            task.add_done_callback(lambda _t, k=key: _INFLIGHT.pop(k, None))
        waits.append(asyncio.shield(task))
    results = await asyncio.gather(*waits, return_exceptions=True)
    return dict(zip(missing, results, strict=True))


def _parse_text(name: str, text: str, ct: str | None) -> Any:
    """Dispatch to the per-endpoint parser (robots returns RobotsSource)."""
    if name == "robots":
        return parse_robots_source(text, ct)
    if name == "ai_txt":
        return parse_ai_txt(text)
    if name == "llms_txt":
        return parse_llms_txt(text)
    if name == "signing_directory":
        return parse_signing_directory(text, ct)
    raise ValueError(f"unknown endpoint {name!r}")  # defensive


def _parse_response(name: str, response: httpx.Response) -> Any:
    return _parse_text(name, response.text, response.headers.get("content-type"))


def save_cache(path: str | os.PathLike) -> int:
    """Persist the process-wide policy cache to ``path`` (JSON). Returns the
    number of entries written. Only raw bodies are stored, never secrets."""
    items = _CACHE.dump()
    target = os.fspath(path)
    fd, tmp = tempfile.mkstemp(
        prefix=".wbauth-cache-", suffix=".tmp", dir=os.path.dirname(target) or "."
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "entries": items}, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return sum(1 for it in items if not it.get("stale"))


def load_cache(path: str | os.PathLike) -> int:
    """Load entries written by :func:`save_cache`. Missing/corrupt file → 0."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return 0
    if not isinstance(data, dict) or data.get("version") != 1:
        return 0
    return _CACHE.restore(list(data.get("entries") or []), _parse_text)


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
    endpoints: Iterable[str] | None = None,
    stop_on_forbidden: bool = False,
    allow_private: bool = True,
) -> SitePolicy:
    """Run the pre-flight inspector against ``url``.

    Args:
        url: Target URL, e.g. ``https://example.com/articles/42``.
        user_agent: The agent's User-Agent. robots.txt rules are evaluated for
            it and it is sent on the policy fetches. Default ``"wbauth/<ver>"``.
        client: Optional shared ``httpx.AsyncClient`` for connection reuse.
            It is not closed by ``inspect``. Without it a pooled per-loop
            client is used.
        endpoints: Subset of ``robots``, ``ai_txt``, ``llms_txt``,
            ``signing_directory`` to consult (default: all four). Skipped
            endpoints are ``None`` and never counted as errors.
        stop_on_forbidden: fetch robots.txt first and skip the other
            endpoints when it already yields ``forbidden``.
        allow_private: when ``False``, refuse origins that are (or resolve
            to) loopback/private/link-local addresses — use this when the
            URL comes from untrusted input (SSRF). Redirects from a public
            origin into private space are always refused.

    Raises:
        ValueError: when the URL is not http(s), has no host, or an unknown
            endpoint name is passed.
    """
    host = _origin_host(url)
    ua = user_agent or DEFAULT_USER_AGENT
    urls = _endpoints(host)
    wanted = tuple(endpoints) if endpoints is not None else _ENDPOINT_NAMES
    unknown = set(wanted) - set(_ENDPOINT_NAMES)
    if unknown:
        raise ValueError(f"inspect: unknown endpoint(s): {sorted(unknown)}")

    raw: dict[str, Any] = {ep: None for ep in _ENDPOINT_NAMES}
    errors: dict[str, Exception] = {}
    missing: list[str] = []
    for ep in wanted:
        entry = _CACHE.get(host, ep)
        if entry is None:
            missing.append(ep)
        elif isinstance(entry.value, Absent):
            errors[ep] = _absent_error(urls[ep], entry.value.status_code)
        elif isinstance(entry.value, Failed):
            errors[ep] = entry.value.error
        else:
            raw[ep] = entry.value

    skipped_reason: str | None = None
    if stop_on_forbidden and "robots" in missing and len(missing) > 1:
        await _inspect_fetch(host, ["robots"], ua, client, allow_private, raw, errors)
        missing.remove("robots")
        if _robots_forbids(raw.get("robots"), errors.get("robots"), url, ua):
            skipped_reason = (
                "stop_on_forbidden: robots.txt forbids this path; skipped "
                + ", ".join(missing)
            )
            missing = []
    elif stop_on_forbidden and _robots_forbids(raw.get("robots"), errors.get("robots"),
                                               url, ua):
        skipped_reason = "stop_on_forbidden: robots.txt forbids this path"
        missing = []

    await _inspect_fetch(host, missing, ua, client, allow_private, raw, errors)
    return _build_policy(url, ua, raw, errors, skipped_reason)


def _robots_forbids(src: Any, err: Exception | None, url: str, ua: str) -> bool:
    from .verdict import compute_verdict as _cv

    robots = evaluate_robots(src, url, ua) if isinstance(src, RobotsSource) else None
    verdict, _ = _cv(robots=robots, ai_txt=None, llms_txt=None, signing_directory=None,
                     errors={"robots": err} if err is not None else {}, partial=False)
    return verdict == "forbidden"


async def _inspect_fetch(
    host: str,
    missing: list[str],
    ua: str,
    client: httpx.AsyncClient | None,
    allow_private: bool,
    raw: dict[str, Any],
    errors: dict[str, Exception],
) -> None:
    """Fetch + parse + cache ``missing`` endpoints into ``raw`` / ``errors``."""
    if not missing:
        return

    validators: dict[str, dict[str, str]] = {}
    stale: dict[str, CacheEntry] = {}
    for ep in missing:
        old = _CACHE.get_stale(host, ep)
        if old is None:
            continue
        stale[ep] = old
        v: dict[str, str] = {}
        if old.etag:
            v["If-None-Match"] = old.etag
        if old.last_modified:
            v["If-Modified-Since"] = old.last_modified
        validators[ep] = v

    fetched = await _fetch_missing(host, missing, ua, client, validators, allow_private)

    for ep, fr in fetched.items():
        if isinstance(fr, BaseException):
            if isinstance(fr, asyncio.TimeoutError) and not isinstance(
                fr, httpx.TimeoutException
            ):
                errors[ep] = httpx.TimeoutException(
                    f"{ep} fetch exceeded {PER_ENDPOINT_TIMEOUT}s"
                )
                _CACHE.set(host, ep, Failed(errors[ep]), ttl_override=FAILURE_TTL)
            elif isinstance(fr, httpx.RequestError):
                errors[ep] = fr
                _CACHE.set(host, ep, Failed(fr), ttl_override=FAILURE_TTL)
            elif isinstance(fr, httpx.HTTPStatusError):
                errors[ep] = fr
                status = fr.response.status_code
                if is_unavailable_status(status):
                    _CACHE.set(
                        host, ep, Absent(status),
                        cache_control=fr.response.headers.get("cache-control"),
                    )
                else:  # 429 / 5xx — retry soon, but not on every call
                    _CACHE.set(host, ep, Failed(fr), ttl_override=FAILURE_TTL)
            elif isinstance(fr, Exception):
                errors[ep] = fr
            else:  # pragma: no cover — BaseException not Exception (e.g. CancelledError)
                errors[ep] = RuntimeError(repr(fr))
            continue
        if fr.status_code == 304 and ep in stale:
            old = stale[ep]
            raw[ep] = old.value
            _CACHE.set(
                host, ep, old.value,
                cache_control=fr.headers.get("cache-control"),
                age=fr.headers.get("age"),
                etag=fr.headers.get("etag") or old.etag,
                last_modified=fr.headers.get("last-modified") or old.last_modified,
                raw=old.raw, content_type=old.content_type,
            )
            continue
        if fr.status_code == 304:  # unsolicited 304 — nothing to reuse
            errors[ep] = FetchError(f"{ep}: unexpected 304 without a cached body")
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
            age=fr.headers.get("age"),
            etag=fr.headers.get("etag"),
            last_modified=fr.headers.get("last-modified"),
            raw=fr.text,
            content_type=fr.headers.get("content-type"),
        )



def _build_policy(
    url: str,
    ua: str,
    raw: dict[str, Any],
    errors: dict[str, Exception],
    skipped_reason: str | None = None,
) -> SitePolicy:
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
        target_path=urlsplit(url).path or "/",
    )
    if skipped_reason:
        reasons = [*reasons, skipped_reason]
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


def inspect_sync(url: str, **kwargs: Any) -> SitePolicy:
    """Blocking wrapper around :func:`inspect` for non-async code.

    Must not be called from inside a running event loop (use ``await
    inspect(...)`` there).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("inspect_sync() called from a running event loop; "
                           "use `await inspect(...)` instead")

    async def _run() -> SitePolicy:
        try:
            return await inspect(url, **kwargs)
        finally:
            if kwargs.get("client") is None:
                await aclose_shared_clients()

    return asyncio.run(_run())
