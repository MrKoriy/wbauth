"""wbauth.policy — pre-flight policy inspector (Phase 2).

Public surface:
  - inspect: async public entry point — ``await inspect(url) -> SitePolicy``
  - save_cache / load_cache: persist the policy cache across processes
  - SitePolicy (frozen dataclass envelope per D-17)
  - RobotsResult, AiTxtResult, LlmsTxtResult, SigningDirectoryResult
  - errors module (PolicyError, RobotsParseError, FetchError, VerdictError)
"""
from . import errors
from .inspector import inspect, load_cache, save_cache
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
    "inspect",
    "load_cache",
    "save_cache",
]
