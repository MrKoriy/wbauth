"""llms.txt parser (llmstxt.org informal spec).

Grammar:
  - H1 (``# Title``) — required.
  - Blockquote (``> description``) — recommended; first one wins.
  - H2 (``## Section``) — sections containing markdown link lists.
  - Link list items: ``- [title](url): notes`` (notes optional).

The ``enforcement`` field is the literal ``"voluntary"`` per D-21 — this
parser surfaces llms.txt content but it MUST NOT be sold as access control.

Defensive cap: bodies > 1 MB raise FetchError to bound parser DoS surface
(threat T-02-02-02).
"""
from __future__ import annotations

import re

from ..errors import FetchError
from ..policy import LlmsTxtLink, LlmsTxtResult, LlmsTxtSection

_MAX_BYTES = 1_000_000

# matches: - [title](url): notes      OR      - [title](url)
_LINK_RE = re.compile(r"^-\s*\[([^\]]+)\]\(([^)]+)\)(?::\s*(.*))?$")


def parse_llms_txt(text: str) -> LlmsTxtResult:
    """Parse an llms.txt body; never raises on malformed structure.

    Raises:
      FetchError: if the body exceeds 1 MB (DoS bound).
    """
    if len(text) > _MAX_BYTES:
        raise FetchError(f"llms.txt body exceeds 1 MB cap ({len(text)} bytes)")

    title = ""
    description = ""
    sections: list[LlmsTxtSection] = []
    current: LlmsTxtSection | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not title and line.startswith("# "):
            title = line[2:].strip()
            continue
        if not description and line.startswith(">"):
            description = line.lstrip("> ").strip()
            continue
        if line.startswith("## "):
            current = LlmsTxtSection(name=line[3:].strip(), links=[])
            sections.append(current)
            continue
        m = _LINK_RE.match(line.strip())
        if m and current is not None:
            current.links.append(
                LlmsTxtLink(
                    title=m.group(1),
                    url=m.group(2),
                    notes=(m.group(3) or "").strip(),
                )
            )

    return LlmsTxtResult(
        title=title,
        description=description,
        sections=sections,
        raw=text,
        enforcement="voluntary",
    )
