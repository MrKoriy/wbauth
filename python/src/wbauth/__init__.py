"""wbauth: Web Bot Auth (RFC 9421) Python SDK.

Phase 1 (current): identity + signer + JWKS + CLI keygen.
Phase 2: HTTP-client adapters + policy inspector.
"""
from .identity import Identity, KeyPair
from .normalized_request import NormalizedRequest
from .signer import SignatureHeaders, sign

__version__ = "0.1.0"

__all__ = [
    "Identity",
    "KeyPair",
    "NormalizedRequest",
    "SignatureHeaders",
    "__version__",
    "sign",
]
