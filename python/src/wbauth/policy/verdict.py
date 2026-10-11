"""Strict verdict engine (D-18). Pure function, no I/O, no state.

Implements the 16-row rule table from
``.planning/phases/02-python-adapters-policy-inspector/02-RESEARCH.md``
§"Verdict Engine Rule Table" verbatim.

Composition (per RESEARCH §"Composition"):

  1. If ANY rule contributes ``forbidden`` → return ``"forbidden"``
     (terminal short-circuit).
  2. Else, if ANY rule contributes ``restricted`` → return ``"restricted"``.
  3. Else, if ``robots`` was fetched cleanly (or was 4xx-unavailable) AND no signals
     against → ``"allowed"``.
  4. Tie-break (D-18): if tentative verdict is ``"allowed"`` AND
     ``partial=True`` → DOWNGRADE to ``"restricted"``.
  5. Else (no clean signals at all) → ``"restricted"`` with reason
     ``"insufficient policy signal"``.

The ``reasons`` list is ORDERED by source: robots first, then ai_txt,
then llms_txt, then signing_directory, then partial-downgrade reason last.
"""
from __future__ import annotations

import re
from typing import Literal

import httpx

from .errors import RobotsParseError
from .policy import (
    AiTxtResult,
    LlmsTxtResult,
    RobotsResult,
    SigningDirectoryResult,
)

# Restrictive phrasing in llms.txt description (Assumption A10 — deliberate
# weak signal; false negatives possible by design per D-18 since llms.txt
# is informational and the authoritative signals come from robots/ai_txt).
_LLMS_RESTRICTIVE_RE = re.compile(
    r"\b(no\s+(automated|ai|bot)\s+access|do\s+not\s+(scrape|crawl))\b",
    re.IGNORECASE,
)


def is_unavailable_status(status: int) -> bool:
    """RFC 9309 §2.3.1.3: 4xx (except 429 Too Many Requests) = "unavailable".

    Unavailable policy files impose no restriction. 429 and 5xx mean the
    server is unreachable, which §2.3.1.4 treats as complete disallow.
    """
    return 400 <= status < 500 and status != 429


def compute_verdict(
    robots: RobotsResult | None,
    ai_txt: AiTxtResult | None,
    llms_txt: LlmsTxtResult | None,
    signing_directory: SigningDirectoryResult | None,
    errors: dict[str, Exception],
    partial: bool,
) -> tuple[Literal["allowed", "restricted", "forbidden"], list[str]]:
    """Compute strict verdict from parsed Result objects + per-endpoint errors.

    See module docstring for the composition rules.
    """
    reasons: list[str] = []
    forbidden_signals: list[str] = []
    restricted_signals: list[str] = []

    # --- Robots branches (RESEARCH rule rows 1-6) ---------------------
    robots_err = errors.get("robots")
    robots_unavailable = False  # RFC 9309 §2.3.1.3 — 4xx / redirect loop
    if isinstance(robots_err, RobotsParseError):
        forbidden_signals.append(
            "robots.txt unparseable (HTML response); assuming disallowed per strict policy"
        )
    elif isinstance(robots_err, httpx.HTTPStatusError):
        status = robots_err.response.status_code
        if is_unavailable_status(status):
            robots_unavailable = True
            label = "absent" if status in (404, 410) else "unavailable"
            reasons.append(
                f"robots.txt {label} ({status}); no robots-based restriction "
                "per RFC 9309 §2.3.1.3"
            )
        else:
            forbidden_signals.append(
                f"robots.txt unreachable ({status}); assuming complete disallow "
                "per RFC 9309 §2.3.1.4"
            )
    elif isinstance(robots_err, httpx.TooManyRedirects):
        robots_unavailable = True
        reasons.append(
            "robots.txt redirect limit exceeded; treated as unavailable "
            "per RFC 9309 §2.3.1.2"
        )
    elif isinstance(robots_err, httpx.TimeoutException):
        forbidden_signals.append(
            "robots.txt fetch timed out; assuming complete disallow per RFC 9309 §2.3.1.4"
        )
    elif isinstance(robots_err, httpx.RequestError):
        forbidden_signals.append(
            f"robots.txt unreachable ({type(robots_err).__name__}); assuming "
            "complete disallow per RFC 9309 §2.3.1.4"
        )
    elif robots_err is not None:
        restricted_signals.append(
            f"robots.txt could not be evaluated ({type(robots_err).__name__})"
        )
    elif robots is not None:
        if robots.can_fetch_url:
            reasons.append("robots.txt allows our user-agent for this path")
        else:
            forbidden_signals.append(
                "robots.txt disallows our user-agent for this path"
            )
        if robots.crawl_delay:
            reasons.append(f"robots.txt Crawl-delay: {robots.crawl_delay:g}s")

    if robots is not None:
        reasons.insert(
            0, f"evaluated against User-Agent='{robots.user_agent_evaluated}'"
        )

    # --- ai.txt branches (rule rows 7-10) -----------------------------
    if ai_txt is not None and ai_txt.restrictions:
        first = ai_txt.restrictions[0]
        snippet = first[:60] + ("..." if len(first) > 60 else "")
        restricted_signals.append(
            f"ai.txt restrictions present: {snippet} ({len(ai_txt.restrictions)} total)"
        )
    elif ai_txt is not None and ai_txt.permissions:
        reasons.append("ai.txt permissions present, no restrictions")

    # --- llms.txt branches (rule rows 11-13) --------------------------
    if llms_txt is not None:
        reasons.append("llms.txt present (informational, enforcement=voluntary)")
        if llms_txt.description:
            m = _LLMS_RESTRICTIVE_RE.search(llms_txt.description)
            if m:
                restricted_signals.append(
                    f"llms.txt description suggests no automated access: {m.group(0)!r}"
                )

    # --- signing-directory branches (rows 14-16) — Pitfall 3 ----------
    if signing_directory is not None and signing_directory.present:
        reasons.append("signing-directory published: signing supported (optional)")

    # --- Composition --------------------------------------------------
    if forbidden_signals:
        return "forbidden", reasons + forbidden_signals + restricted_signals

    if restricted_signals:
        return "restricted", reasons + restricted_signals

    # Tentative allowed — only if robots was fetched cleanly OR 404'd cleanly.
    robots_clean = (robots is not None and robots_err is None) or robots_unavailable
    if robots_clean:
        if partial:
            errored = ", ".join(sorted(errors.keys()))
            return "restricted", reasons + [
                f"partial policy fetch (errored: {errored}); strict policy downgrades to restricted"
            ]
        return "allowed", reasons

    # No clean signals at all.
    return "restricted", reasons + ["insufficient policy signal"]
