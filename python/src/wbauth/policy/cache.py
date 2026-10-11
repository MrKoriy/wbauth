"""Per-process policy cache for the inspector (D-22).

One ``cachetools.TLRUCache`` keyed by ``(host, endpoint)`` with a
**per-entry** time-to-live:

* No ``Cache-Control`` → the endpoint's default TTL (``DEFAULT_TTLS``).
* ``max-age=N`` → ``N`` seconds, clamped to ``MAX_TTL`` (24 h).
* ``no-store`` / ``no-cache`` / ``private`` / ``max-age=0`` → not cached.

Hosts are normalised (lower-case, trailing dot and default port stripped),
so ``EXAMPLE.com`` and ``example.com:443`` share one entry.

Negative results (an endpoint answered 4xx, i.e. "not published") are cached
too — as :class:`Absent` — so repeated ``inspect()`` calls do not re-download
404s. Cache is per-process and resets on restart (D-23 — no persistence).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

from cachetools import TLRUCache

DEFAULT_TTLS = {
    "robots": 24 * 3600,             # 24h
    "ai_txt": 1 * 3600,              # 1h
    "llms_txt": 24 * 3600,           # 24h
    "signing_directory": 5 * 60,     # 5min
}
"""Fallback TTL (seconds) per endpoint when the origin sends no max-age."""

MAX_TTL = 24 * 3600
"""Upper bound for origin-supplied max-age (RFC 9309 §2.4: ≤ 24 h for robots)."""

MAX_ENTRIES = 4096

_MAX_AGE_RE = re.compile(r"(?:^|[,\s])(?:s-)?max-age\s*=\s*\"?(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class Absent:
    """Negative-cache marker: the endpoint answered ``status_code`` (4xx)."""

    status_code: int


@dataclass
class CacheEntry:
    """Cached parsed value plus validators."""

    value: object
    etag: str | None = None
    ttl: float = 0.0


def normalize_host(host: str) -> str:
    """Lower-case, strip trailing dot and the default https port."""
    h = host.strip().lower()
    if h.endswith(":443"):
        h = h[: -len(":443")]
    return h.rstrip(".")


def _parse_cache_control(header: str | None) -> tuple[bool, int | None]:
    """Return ``(cacheable, max_age_seconds_or_None)``."""
    if not header:
        return True, None
    h = header.lower()
    if "no-store" in h or "no-cache" in h or "private" in h:
        return False, None
    m = _MAX_AGE_RE.search(h)
    if m:
        return True, int(m.group(1))
    return True, None


def _ttu(_key: object, value: CacheEntry, now: float) -> float:
    return now + value.ttl


class PolicyCache:
    """``(host, endpoint)`` → :class:`CacheEntry` with per-entry TTL."""

    def __init__(self, maxsize: int = MAX_ENTRIES, timer=time.monotonic) -> None:
        self._cache: TLRUCache = TLRUCache(maxsize=maxsize, ttu=_ttu, timer=timer)

    def get(self, host: str, endpoint: str) -> CacheEntry | None:
        """Return the live entry or ``None`` (miss / expired)."""
        if endpoint not in DEFAULT_TTLS:
            raise KeyError(endpoint)
        return self._cache.get((normalize_host(host), endpoint))

    def set(
        self,
        host: str,
        endpoint: str,
        value: object,
        cache_control: str | None = None,
        etag: str | None = None,
    ) -> None:
        """Store ``value`` honouring the origin's Cache-Control directives."""
        default_ttl = DEFAULT_TTLS[endpoint]  # raises KeyError on unknown endpoint
        cacheable, max_age = _parse_cache_control(cache_control)
        if not cacheable:
            return
        ttl = default_ttl if max_age is None else min(max_age, MAX_TTL)
        if ttl <= 0:
            return
        self._cache[(normalize_host(host), endpoint)] = CacheEntry(
            value=value, etag=etag, ttl=float(ttl)
        )

    def clear(self) -> None:
        self._cache.clear()
