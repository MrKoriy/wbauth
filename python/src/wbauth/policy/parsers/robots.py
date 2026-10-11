"""robots.txt parser — protego wrapper with HTML-200 detection (Pitfall 1).

D-19: an HTML body served as /robots.txt MUST raise RobotsParseError so
the verdict engine maps to "forbidden" instead of silently allowing.

Parsing and evaluation are split so the inspector can cache the parsed
rules once per host (:class:`RobotsSource`) and evaluate them per target
path and per user-agent — a cached verdict for ``/public`` must never be
reused for ``/private``.
"""
from __future__ import annotations

from dataclasses import dataclass

from protego import Protego

from ..._version import __version__
from ..errors import RobotsParseError
from ..policy import RobotsResult

DEFAULT_USER_AGENT = f"wbauth/{__version__}"


@dataclass(frozen=True)
class RobotsSource:
    """Parsed robots.txt rules, independent of target path and user-agent."""

    parser: Protego
    raw: str


def parse_robots_source(text: str, content_type: str | None) -> RobotsSource:
    """Parse robots.txt once. Raises :class:`RobotsParseError` on HTML bodies."""
    # RFC 9309 §2.2: a leading UTF-8 BOM must not hide the first group.
    text = text.lstrip("\ufeff")
    sniff = text.lstrip()[:1]
    if sniff == "<" or (content_type and "html" in content_type.lower()):
        raise RobotsParseError(
            "robots.txt response looks like HTML — origin likely returned a "
            "catch-all SPA page; cannot evaluate; assuming disallowed"
        )
    return RobotsSource(parser=Protego.parse(text), raw=text)


def evaluate_robots(
    source: RobotsSource, target_url: str, user_agent: str = DEFAULT_USER_AGENT
) -> RobotsResult:
    """Evaluate cached rules for one ``(target_url, user_agent)`` pair."""
    rp = source.parser
    return RobotsResult(
        can_fetch_url=rp.can_fetch(target_url, user_agent),
        sitemaps=list(rp.sitemaps),
        raw=source.raw,
        user_agent_evaluated=user_agent,
        crawl_delay=rp.crawl_delay(user_agent),
    )


def parse_robots(
    text: str,
    content_type: str | None,
    target_url: str,
    user_agent: str = DEFAULT_USER_AGENT,
) -> RobotsResult:
    """Parse + evaluate in one step (convenience wrapper)."""
    return evaluate_robots(parse_robots_source(text, content_type), target_url, user_agent)
