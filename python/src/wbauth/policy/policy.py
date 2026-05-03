"""SitePolicy + per-endpoint Result dataclasses (D-17).

All five dataclasses are ``@dataclass(frozen=True)`` value objects: the
*envelope* is immutable (callers cannot reassign a field), but the field
*values* themselves (lists, dicts) remain mutable in place. This is
acceptable per the Phase-1 precedent (NormalizedRequest.headers is also
a mutable dict on a non-frozen dataclass; SitePolicy's frozen status
protects the envelope.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class RobotsResult:
    """Parsed /robots.txt outcome for a specific (target_url, user_agent)."""

    can_fetch_url: bool
    sitemaps: list[str]
    raw: str
    user_agent_evaluated: str  # always "wbauth/0.1" in v1 (D-20)


@dataclass(frozen=True)
class AiTxtResult:
    """Parsed /ai.txt v1.1.1 result.

    ``content_types`` is intentionally empty in v1 (Assumption A6 — full
    nested-list parsing deferred to v1.x).
    """

    identity: dict[str, str]
    permissions: list[str]
    restrictions: list[str]
    attribution: list[str] = field(default_factory=list)
    contact: dict[str, str] = field(default_factory=dict)
    content_types: dict[str, list[str]] = field(default_factory=dict)
    raw: str = ""


@dataclass(frozen=True)
class LlmsTxtLink:
    """One link inside an llms.txt section."""

    title: str
    url: str
    notes: str = ""


@dataclass(frozen=True)
class LlmsTxtSection:
    """One H2-named section of an llms.txt file."""

    name: str
    links: list[LlmsTxtLink] = field(default_factory=list)


@dataclass(frozen=True)
class LlmsTxtResult:
    """Parsed /llms.txt result.

    ``enforcement`` is the literal ``"voluntary"`` per D-21 — llms.txt is
    advisory only and is never sold as access control.
    """

    title: str
    description: str
    sections: list[LlmsTxtSection] = field(default_factory=list)
    raw: str = ""
    enforcement: Literal["voluntary"] = "voluntary"


@dataclass(frozen=True)
class SigningDirectoryResult:
    """Parsed /.well-known/http-message-signatures-directory result.

    Lightweight — surfaces presence + key count + content-type-correctness
    only. NO JWK validation (verifier's job, not inspector's).
    """

    present: bool
    keys: list[dict]
    content_type_correct: bool
    raw: str


@dataclass(frozen=True)
class SitePolicy:
    """Aggregated pre-flight policy result for a single URL.

    Fields per CONTEXT.md D-17:

    - ``url``: the input URL passed to ``inspect()``.
    - ``robots`` .. ``signing_directory``: parsed Result for each endpoint,
      or ``None`` if the endpoint errored (look in ``errors`` for the
      exception).
    - ``verdict``: deterministic strict outcome per D-18.
    - ``reasons``: ordered list of human-readable strings explaining the
      verdict.
    - ``partial``: ``True`` iff any endpoint failed.
    - ``errors``: keyed by endpoint name (``"robots"`` / ``"ai_txt"`` /
      ``"llms_txt"`` / ``"signing_directory"``).
    - ``fetched_at``: timezone-aware UTC datetime of the inspect() call.

    Frozen at the envelope level; the contained list/dict objects are
    mutable in place — do not modify them.
    """

    url: str
    robots: RobotsResult | None
    ai_txt: AiTxtResult | None
    llms_txt: LlmsTxtResult | None
    signing_directory: SigningDirectoryResult | None
    verdict: Literal["allowed", "restricted", "forbidden"]
    reasons: list[str]
    partial: bool
    errors: dict[str, Exception]
    fetched_at: datetime
