"""Per-host LRU cache for policy inspector (D-22).

One ``cachetools.TTLCache`` per endpoint type, each with its own default
TTL bucket. Origin Cache-Control: ``no-store`` / ``no-cache`` / ``private``
or ``max-age=0`` cause the entry NOT to be cached (Pitfall 5).

**Assumption A7** (per-entry-TTL approximation): ``cachetools.TTLCache``
uses ONE TTL per cache instance, not per entry. We approximate per-entry
TTL by maintaining a separate TTLCache per endpoint type. Sub-default TTL
(when origin sends ``max-age=N`` with N < default) is honored only by
"don't cache when N=0"; smaller positive N values are still cached at the
bucket's default TTL. Sub-default-TTL fidelity is a v1.x add. This trade-off
is documented in RESEARCH §"Note on the per-entry-TTL approximation".

Cache is per-process and resets on restart (D-23 — no persistence).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from cachetools import TTLCache

# Per-endpoint default TTLs from D-22.
DEFAULT_TTLS = {
    "robots": 24 * 3600,             # 24h
    "ai_txt": 1 * 3600,              # 1h
    "llms_txt": 24 * 3600,           # 24h
    "signing_directory": 5 * 60,     # 5min
}

# ~1 KB per parsed result × 1024 = ~1 MB total per bucket. With four buckets,
# the cache occupies ~4 MB worst-case — trivial for an agent process.
MAX_ENTRIES = 1024

_MAX_AGE_RE = re.compile(r"max-age\s*=\s*(\d+)", re.IGNORECASE)


@dataclass
class CacheEntry:
    """One cached parsed Result + optional ETag for future conditional GET."""

    value: object
    etag: str | None = None


def _parse_cache_control(header: str | None) -> tuple[bool, int | None]:
    """Parse a Cache-Control header → ``(cacheable, max_age_seconds_or_none)``.

    Per Pitfall 5: ``no-store`` / ``no-cache`` / ``private`` are checked
    BEFORE ``max-age``. If any is present, we report not cacheable.
    """
    if not header:
        return True, None
    h = header.lower()
    if "no-store" in h or "no-cache" in h or "private" in h:
        return False, None
    m = _MAX_AGE_RE.search(h)
    if m:
        return True, int(m.group(1))
    return True, None


class PolicyCache:
    """Per-(host, endpoint) cache with origin Cache-Control honoring.

    Internal architecture: one ``TTLCache`` instance per endpoint type, each
    sized at ``MAX_ENTRIES`` and with that endpoint's default TTL. See
    Assumption A7 in the module docstring for the per-entry-TTL trade-off.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, TTLCache] = {
            ep: TTLCache(maxsize=MAX_ENTRIES, ttl=DEFAULT_TTLS[ep])
            for ep in DEFAULT_TTLS
        }

    def get(self, host: str, endpoint: str) -> CacheEntry | None:
        """Look up ``(host, endpoint)`` → CacheEntry or None on miss/expiry.

        Raises:
          KeyError: if ``endpoint`` is not one of the four known names.
        """
        bucket = self._buckets[endpoint]
        return bucket.get(host)

    def set(
        self,
        host: str,
        endpoint: str,
        value: object,
        cache_control: str | None = None,
        etag: str | None = None,
    ) -> None:
        """Store ``value`` under ``(host, endpoint)`` honoring Cache-Control.

        Skips storage if Cache-Control forbids caching (no-store / no-cache /
        private / max-age=0). Otherwise stores at the bucket's default TTL
        per Assumption A7.

        Raises:
          KeyError: if ``endpoint`` is not one of the four known names.
        """
        bucket = self._buckets[endpoint]  # raises KeyError on unknown endpoint
        cacheable, max_age = _parse_cache_control(cache_control)
        if not cacheable:
            return
        if max_age == 0:
            return
        bucket[host] = CacheEntry(value=value, etag=etag)
