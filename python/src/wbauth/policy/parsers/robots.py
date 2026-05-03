"""robots.txt parser — protego wrapper with HTML-200 detection (Pitfall 1).

D-19: an HTML body served as /robots.txt MUST raise RobotsParseError so
the verdict engine maps to "forbidden" instead of silently allowing.
"""
from __future__ import annotations

from protego import Protego

from ..errors import RobotsParseError
from ..policy import RobotsResult


def parse_robots(
    text: str,
    content_type: str | None,
    target_url: str,
    user_agent: str = "wbauth/0.1",
) -> RobotsResult:
    """Parse robots.txt body and evaluate ``can_fetch(target_url, ua)``.

    Args:
      text: raw robots.txt response body.
      content_type: HTTP Content-Type header (may be None / arbitrary case).
      target_url: the URL the agent intends to fetch (path is what matters).
      user_agent: UA string to evaluate against (D-20: "wbauth/0.1" in v1).

    Returns:
      RobotsResult with can_fetch_url + sitemaps populated.

    Raises:
      RobotsParseError: if the body is HTML (content-type advertises HTML
        OR first non-whitespace byte is ``<``). Pitfall 1 detection.
    """
    # Pitfall 1: detect HTML-200-on-robots silently parsed as "no rules → allow".
    sniff = text.lstrip()[:1]
    if sniff == "<" or (content_type and "html" in content_type.lower()):
        raise RobotsParseError(
            "robots.txt response looks like HTML — origin likely returned a "
            "catch-all SPA page; cannot evaluate; assuming disallowed"
        )

    rp = Protego.parse(text)
    return RobotsResult(
        can_fetch_url=rp.can_fetch(target_url, user_agent),
        sitemaps=list(rp.sitemaps),
        raw=text,
        user_agent_evaluated=user_agent,
    )
