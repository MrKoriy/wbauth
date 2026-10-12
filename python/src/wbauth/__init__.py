"""wbauth: Web Bot Auth (RFC 9421) Python SDK.

Identity + signer + JWKS, HTTP-client adapters, pre-flight policy
inspector/guard, and origin-side verification (``Verifier``).
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
from .identity import Ed25519Signer, Identity, KeyPair
from .normalized_request import NormalizedRequest
from .policy import (
    AiTxtResult,
    LlmsTxtResult,
    RobotsResult,
    SigningDirectoryResult,
    PolicyForbiddenError,
    PolicyGuard,
    SitePolicy,
    inspect,
    inspect_sync,
)
from .signer import SignatureHeaders, sign
from .verifier import (
    VerificationError,
    VerifiedAgent,
    Verifier,
    WebBotAuthMiddleware,
    verify_request,
)

from ._version import __version__

__all__ = [
    "AsyncSigningTransport",
    "SigningTransport",
    "signed_async_client",
    "signed_client",
    "AiTxtResult",
    "Ed25519Signer",
    "Identity",
    "KeyPair",
    "LlmsTxtResult",
    "NormalizedRequest",
    "PolicyForbiddenError",
    "PolicyGuard",
    "RobotsResult",
    "SignatureHeaders",
    "SigningDirectoryResult",
    "SitePolicy",
    "VerificationError",
    "VerifiedAgent",
    "Verifier",
    "WebBotAuth",
    "WebBotAuthAdapter",
    "WebBotAuthMiddleware",
    "WebBotAuthTransport",
    "__version__",
    "attach_signing",
    "inspect",
    "inspect_sync",
    "sign",
    "signed_session",
    "verify_request",
]
