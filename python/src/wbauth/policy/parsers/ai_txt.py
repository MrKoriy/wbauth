"""ai.txt v1.1.1 parser.

Grammar (per ai-visibility.org.uk/specifications/ai-txt/):
  - Section headers are ``[name]`` (lowercase, bracketed) on their own line.
  - Comments start with ``#``.
  - Inside ``[identity]`` / ``[contact]``: ``key: value`` pairs, one per line.
  - Inside ``[permissions]`` / ``[restrictions]`` / ``[attribution]``:
    bullet items starting with ``-``, ``*``, ``+`` or ``•``.
  - Inside ``[content-types]``: nested bullet lists per spec — for v1 we
    return ``content_types={}`` (Assumption A6).
  - Blank lines separate sections.

Defensive cap: bodies > 1 MB raise FetchError to bound parser DoS surface
(threat T-02-02-02).
"""
from __future__ import annotations

import re

from ..errors import FetchError
from ..policy import AiTxtResult

_MAX_BYTES = 1_000_000

# "- item", "-item", "* item", "+ item", "• item"
_BULLET_RE = re.compile(r"^[-*+\u2022]\s*(.*)$")


def _strip_inline_comment(line: str) -> str:
    """Drop a trailing `` # comment`` (only when preceded by whitespace)."""
    idx = line.find(" #")
    return line[:idx].rstrip() if idx > 0 else line


def parse_ai_txt(text: str) -> AiTxtResult:
    """Parse an ai.txt body; never raises on malformed structure.

    Raises:
      FetchError: if the body exceeds 1 MB (DoS bound).
    """
    if len(text) > _MAX_BYTES:
        raise FetchError(f"ai.txt body exceeds 1 MB cap ({len(text)} bytes)")

    text = text.lstrip("\ufeff")
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = _strip_inline_comment(line)
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].lower()
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)

    def _kv(lines: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for ln in lines:
            if ":" in ln:
                k, v = ln.split(":", 1)
                out[k.strip().lower()] = v.strip()
        return out

    def _bullets(lines: list[str]) -> list[str]:
        out: list[str] = []
        for ln in lines:
            m = _BULLET_RE.match(ln)
            if m and m.group(1).strip():
                out.append(m.group(1).strip())
        return out

    return AiTxtResult(
        identity=_kv(sections.get("identity", [])),
        permissions=_bullets(sections.get("permissions", [])),
        restrictions=_bullets(sections.get("restrictions", [])),
        attribution=_bullets(sections.get("attribution", [])),
        contact=_kv(sections.get("contact", [])),
        content_types={},  # full nested-list parser is post-v1 if needed (A6)
        raw=text,
    )
