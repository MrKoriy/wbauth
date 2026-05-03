"""wbauth: Web Bot Auth (RFC 9421) Python SDK.

Phase 1 (current): identity + signer + JWKS + CLI keygen.
Phase 2: HTTP-client adapters + policy inspector.
"""
from .adapters import WebBotAuth, WebBotAuthAdapter, attach_signing
from .identity import Identity, KeyPair
from .normalized_request import NormalizedRequest
from .policy import (
    AiTxtResult,
    LlmsTxtResult,
    RobotsResult,
    SigningDirectoryResult,
    SitePolicy,
    inspect,
)
from .signer import SignatureHeaders, sign

__version__ = "0.1.0"

__all__ = [
    "AiTxtResult",
    "Identity",
    "KeyPair",
    "LlmsTxtResult",
    "NormalizedRequest",
    "RobotsResult",
    "SignatureHeaders",
    "SigningDirectoryResult",
    "SitePolicy",
    "WebBotAuth",
    "WebBotAuthAdapter",
    "__version__",
    "attach_signing",
    "inspect",
    "sign",
]
