"""wbauth: Web Bot Auth (RFC 9421) Python SDK.

Phase 1 (current): identity + signer + JWKS + CLI keygen.
Phase 2: HTTP-client adapters + policy inspector.
"""
from .adapters import (
    AsyncSigningTransport,
    SigningTransport,
    signed_async_client,
    signed_client,
    WebBotAuth,
    WebBotAuthAdapter,
    WebBotAuthTransport,
    attach_signing,
    signed_session,
)
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

from ._version import __version__

__all__ = [
    "AsyncSigningTransport",
    "SigningTransport",
    "signed_async_client",
    "signed_client",
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
    "WebBotAuthTransport",
    "__version__",
    "attach_signing",
    "inspect",
    "sign",
    "signed_session",
]
