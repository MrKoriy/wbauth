"""Per-process policy cache for the inspector (D-22).

One ``cachetools.TLRUCache`` keyed by ``(host, endpoint)`` with a
**per-entry** time-to-live:

* No ``Cache-Control`` → the endpoint's default TTL (``DEFAULT_TTLS``).
* ``max-age=N`` → ``N`` seconds, clamped to ``MAX_TTL`` (24 h).
* ``no-store`` / ``no-cache`` / ``max-age=0`` → not cached. ``private`` is
  fine: this is a single-user client cache, not a shared one (RFC 9111 §5.2.2.7).

Expired entries that carried an ``ETag`` / ``Last-Modified`` validator are
kept in a small LRU "stale" store so the inspector can revalidate them with a
conditional GET (``If-None-Match`` / ``If-Modified-Since``) instead of
re-downloading the body. :meth:`PolicyCache.dump` / :meth:`PolicyCache.restore`
serialize the cache (raw bodies, not parsed objects) for persistence across
processes — see ``wbauth.policy.save_cache`` / ``load_cache``.

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

from cachetools import LRUCache, TLRUCache

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
    last_modified: str | None = None
    raw: str | None = None           # original body (for persistence)
    content_type: str | None = None  # original Content-Type (for persistence)
    stored_at: float = 0.0           # wall-clock time.time() at store


def normalize_host(host: str) -> str:
    """Lower-case, strip trailing dot and the default port.

    ``https`` origins are keyed by bare ``host[:port]``; plain-``http`` origins
    carry an ``http://`` prefix so the two schemes never share an entry.
    """
    h = host.strip().lower()
    if h.startswith("http://"):
        rest = h[len("http://"):]
        if rest.endswith(":80"):
            rest = rest[: -len(":80")]
        return "http://" + rest.rstrip(".")
    if h.endswith(":443"):
        h = h[: -len(":443")]
    return h.rstrip(".")


def _parse_cache_control(header: str | None) -> tuple[bool, int | None]:
    """Return ``(cacheable, max_age_seconds_or_None)``."""
    if not header:
        return True, None
    h = header.lower()
    if "no-store" in h or "no-cache" in h:
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
        self._stale: LRUCache = LRUCache(maxsize=maxsize)

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
        *,
        last_modified: str | None = None,
        raw: str | None = None,
        content_type: str | None = None,
        ttl_override: float | None = None,
    ) -> None:
        """Store ``value`` honouring the origin's Cache-Control directives."""
        default_ttl = DEFAULT_TTLS[endpoint]  # raises KeyError on unknown endpoint
        key = (normalize_host(host), endpoint)
        entry = CacheEntry(
            value=value, etag=etag, last_modified=last_modified, raw=raw,
            content_type=content_type, stored_at=time.time(),
        )
        if cache_control and "no-store" in cache_control.lower():
            return
        if (etag or last_modified) and not isinstance(value, Absent):
            self._stale[key] = entry  # validators survive expiry
        if ttl_override is not None:
            ttl = ttl_override
        else:
            cacheable, max_age = _parse_cache_control(cache_control)
            if not cacheable:
                return
            ttl = default_ttl if max_age is None else min(max_age, MAX_TTL)
        if ttl <= 0:
            return
        entry.ttl = float(ttl)
        self._cache[key] = entry

    def get_stale(self, host: str, endpoint: str) -> CacheEntry | None:
        """Return an expired-or-live entry that has validators, for revalidation."""
        return self._stale.get((normalize_host(host), endpoint))

    def dump(self) -> list[dict]:
        """Serialize live entries (raw bodies + metadata) to JSON-safe dicts."""
        out: list[dict] = []
        now = time.time()
        for (host, endpoint), e in list(self._cache.items()):
            remaining = e.ttl - (now - e.stored_at)
            if remaining <= 0:
                continue
            item = {
                "host": host, "endpoint": endpoint, "etag": e.etag,
                "last_modified": e.last_modified, "content_type": e.content_type,
                "expires_at": now + remaining,
            }
            if isinstance(e.value, Absent):
                item["absent"] = e.value.status_code
            elif e.raw is not None:
                item["raw"] = e.raw
            else:
                continue
            out.append(item)
        return out

    def restore(self, items: list[dict], parse) -> int:
        """Load entries produced by :meth:`dump`; ``parse(endpoint, raw, ct)``
        rebuilds the parsed value. Returns the number of entries restored."""
        now = time.time()
        n = 0
        for it in items:
            try:
                remaining = float(it["expires_at"]) - now
                endpoint = it["endpoint"]
                if remaining <= 0 or endpoint not in DEFAULT_TTLS:
                    continue
                if "absent" in it:
                    value: object = Absent(int(it["absent"]))
                    raw = None
                else:
                    raw = str(it["raw"])
                    value = parse(endpoint, raw, it.get("content_type"))
            except Exception:  # noqa: BLE001 — a corrupt entry is skipped, never fatal
                continue
            self.set(
                it["host"], endpoint, value, etag=it.get("etag"),
                last_modified=it.get("last_modified"), raw=raw,
                content_type=it.get("content_type"),
                ttl_override=min(remaining, MAX_TTL),
            )
            n += 1
        return n

    def clear(self) -> None:
        self._cache.clear()
        self._stale.clear()
