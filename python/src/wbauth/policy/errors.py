"""Policy-inspector exception taxonomy (D-31).

The base ``PolicyError`` lets callers catch every wbauth.policy.* error
in one ``except`` clause. ``RobotsParseError`` is the only exception
type whose presence in ``SitePolicy.errors`` directly drives the verdict
(verdict engine maps it to ``"forbidden"`` per D-19).
"""
from __future__ import annotations


class PolicyError(Exception):
    """Base class for all wbauth.policy exceptions."""


class RobotsParseError(PolicyError):
    """Raised when /robots.txt response is non-parseable.

    Triggered by:
      - HTML response (content-type starts with text/html OR first
        non-whitespace byte is ``<``) — Pitfall 1.
      - 403 / 5xx response (uncertain access policy) — D-19.

    The verdict engine maps this to ``verdict="forbidden"``.
    """


class FetchError(PolicyError):
    """Raised when an inspector fetch fails in a way the verdict engine
    must surface as a non-terminal restriction signal."""


class VerdictError(PolicyError):
    """Raised on internal verdict engine inconsistency (defensive check
    for unit tests; should never reach the user)."""
