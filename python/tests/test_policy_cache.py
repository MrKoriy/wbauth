"""Tests for wbauth.policy.cache.PolicyCache.

Per-host LRU cache (cachetools.TTLCache buckets per endpoint) honoring
origin Cache-Control: no-store/no-cache/private/max-age=0 by skipping
the cache (D-22, Pitfall 5).
"""
from __future__ import annotations

import pytest

from wbauth.policy.cache import PolicyCache, _parse_cache_control


# --- _parse_cache_control unit tests --------------------------------------

@pytest.mark.parametrize("header,expected_cacheable,expected_max_age", [
    (None, True, None),
    ("", True, None),
    ("no-store", False, None),
    ("no-cache", False, None),
    ("private", False, None),
    ("public, no-store", False, None),
    ("public, max-age=300", True, 300),
    ("max-age=0", True, 0),
    ("max-age=86400, public", True, 86400),
    # case-insensitive
    ("NO-STORE", False, None),
    ("Max-Age=42", True, 42),
])
def test_parse_cache_control_branches(header, expected_cacheable, expected_max_age):
    cacheable, max_age = _parse_cache_control(header)
    assert cacheable is expected_cacheable
    assert max_age == expected_max_age


# --- PolicyCache integration tests ----------------------------------------

def test_cache_set_then_get_returns_value():
    cache = PolicyCache()
    cache.set("example.com", "robots", {"hello": "world"})
    entry = cache.get("example.com", "robots")
    assert entry is not None
    assert entry.value == {"hello": "world"}


def test_cache_no_store_skips():
    cache = PolicyCache()
    cache.set("example.com", "robots", "v", cache_control="no-store")
    assert cache.get("example.com", "robots") is None


def test_cache_no_cache_skips():
    cache = PolicyCache()
    cache.set("example.com", "robots", "v", cache_control="no-cache")
    assert cache.get("example.com", "robots") is None


def test_cache_private_skips():
    cache = PolicyCache()
    cache.set("example.com", "robots", "v", cache_control="private, max-age=300")
    assert cache.get("example.com", "robots") is None


def test_cache_max_age_zero_skips():
    cache = PolicyCache()
    cache.set("example.com", "robots", "v", cache_control="max-age=0")
    assert cache.get("example.com", "robots") is None


def test_cache_max_age_positive_caches():
    cache = PolicyCache()
    cache.set("example.com", "robots", "v", cache_control="max-age=86400")
    entry = cache.get("example.com", "robots")
    assert entry is not None
    assert entry.value == "v"


def test_cache_two_endpoints_separate_buckets():
    """(host, endpoint) keying: same host, different endpoints → separate values."""
    cache = PolicyCache()
    cache.set("example.com", "robots", "robots-value")
    cache.set("example.com", "ai_txt", "ai-value")
    assert cache.get("example.com", "robots").value == "robots-value"
    assert cache.get("example.com", "ai_txt").value == "ai-value"


def test_cache_two_hosts_separate_entries():
    """Same endpoint bucket, different host keys → separate values."""
    cache = PolicyCache()
    cache.set("a.example.com", "robots", "value-a")
    cache.set("b.example.com", "robots", "value-b")
    assert cache.get("a.example.com", "robots").value == "value-a"
    assert cache.get("b.example.com", "robots").value == "value-b"


def test_cache_etag_stored_alongside_value():
    cache = PolicyCache()
    cache.set("example.com", "robots", "v", etag='"abc123"')
    entry = cache.get("example.com", "robots")
    assert entry.etag == '"abc123"'


def test_cache_unknown_endpoint_raises_key_error():
    """Defensive: unknown endpoint name raises rather than silently inserting."""
    cache = PolicyCache()
    with pytest.raises(KeyError):
        cache.set("example.com", "not_an_endpoint", "v")


def test_cache_get_miss_returns_none():
    cache = PolicyCache()
    assert cache.get("never-set.example.com", "robots") is None
