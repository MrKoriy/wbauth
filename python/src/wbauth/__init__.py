"""wbauth: Web Bot Auth (RFC 9421) Python SDK.

Phase 1 (current): identity + signer + JWKS + CLI keygen.
Phase 2: HTTP-client adapters + policy inspector.
"""
from .identity import Identity, KeyPair
from .normalized_request import NormalizedRequest

__version__ = "0.1.0"

# Plan 03 Task 2 will add the signer re-exports:
# from .signer import sign, SignatureHeaders
# __all__ = ["Identity", "KeyPair", "sign", "SignatureHeaders", "NormalizedRequest", "__version__"]

__all__ = ["Identity", "KeyPair", "NormalizedRequest", "__version__"]
