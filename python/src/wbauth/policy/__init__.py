"""wbauth.policy — pre-flight policy inspector (Phase 2).

Public surface (Task 1 — parsers + dataclasses):
  - SitePolicy (frozen dataclass envelope per D-17)
  - RobotsResult, AiTxtResult, LlmsTxtResult, SigningDirectoryResult
  - errors module (PolicyError, RobotsParseError, FetchError, VerdictError)

Task 3 will append:
  - inspect: async public entry point
"""
from . import errors
from .policy import (
    AiTxtResult,
    LlmsTxtLink,
    LlmsTxtResult,
    LlmsTxtSection,
    RobotsResult,
    SigningDirectoryResult,
    SitePolicy,
)

__all__ = [
    "AiTxtResult",
    "LlmsTxtLink",
    "LlmsTxtResult",
    "LlmsTxtSection",
    "RobotsResult",
    "SigningDirectoryResult",
    "SitePolicy",
    "errors",
]
