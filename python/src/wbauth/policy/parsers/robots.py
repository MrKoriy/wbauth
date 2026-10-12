"""robots.txt parser — protego wrapper with HTML-200 detection (Pitfall 1).

D-19: an HTML body served as /robots.txt MUST raise RobotsParseError so
the verdict engine maps to "forbidden" instead of silently allowing.

Parsing and evaluation are split so the inspector can cache the parsed
rules once per host (:class:`RobotsSource`) and evaluate them per target
path and per user-agent — a cached verdict for ``/public`` must never be
reused for ``/private``.
"""
from __future__ import annotations

import re
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


_CONTENT_SIGNAL_RE = re.compile(r"^\s*content-signal\s*:\s*(.+?)\s*(?:#.*)?$", re.I)
_UA_LINE_RE = re.compile(r"^\s*user-agent\s*:\s*(.+?)\s*(?:#.*)?$", re.I)


def product_token(user_agent: str) -> str:
    """RFC 9309 §2.2.1: robots groups match the UA *product token*
    (``ExampleBot`` in ``ExampleBot/1.0 (+https://…)``)."""
    token = re.split(r"[/\s(]", user_agent.strip(), maxsplit=1)[0]
    return token or user_agent


def parse_content_signals(text: str, user_agent: str) -> dict[str, str]:
    """Parse Cloudflare-style ``Content-Signal: search=yes, ai-train=no``
    lines (contentsignals.org). Signals in a group whose User-agent matches
    the product token (or ``*``) apply; the specific group wins over ``*``."""
    token = product_token(user_agent).lower()
    groups: list[tuple[set[str], dict[str, str]]] = []
    agents: set[str] = set()
    signals: dict[str, str] = {}
    last_was_ua = False
    for line in text.splitlines():
        m = _UA_LINE_RE.match(line)
        if m:
            if not last_was_ua:
                if agents:
                    groups.append((agents, signals))
                agents, signals = set(), {}
            agents.add(m.group(1).lower())
            last_was_ua = True
            continue
        if line.strip() and not line.lstrip().startswith("#"):
            last_was_ua = False
        m = _CONTENT_SIGNAL_RE.match(line)
        if m:
            for part in m.group(1).split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    signals[k.strip().lower()] = v.strip().lower()
    if agents:
        groups.append((agents, signals))
    generic: dict[str, str] = {}
    specific: dict[str, str] = {}
    for ags, sig in groups:
        if "*" in ags:
            generic.update(sig)
        if any(a != "*" and a in token for a in ags):
            specific.update(sig)
    return {**generic, **specific}


def evaluate_robots(
    source: RobotsSource, target_url: str, user_agent: str = DEFAULT_USER_AGENT
) -> RobotsResult:
    """Evaluate cached rules for one ``(target_url, user_agent)`` pair."""
    rp = source.parser
    token = product_token(user_agent)
    return RobotsResult(
        can_fetch_url=rp.can_fetch(target_url, token),
        sitemaps=list(rp.sitemaps),
        raw=source.raw,
        user_agent_evaluated=user_agent,
        crawl_delay=rp.crawl_delay(token),
        content_signals=parse_content_signals(source.raw, user_agent),
    )


def parse_robots(
    text: str,
    content_type: str | None,
    target_url: str,
    user_agent: str = DEFAULT_USER_AGENT,
) -> RobotsResult:
    """Parse + evaluate in one step (convenience wrapper)."""
    return evaluate_robots(parse_robots_source(text, content_type), target_url, user_agent)
