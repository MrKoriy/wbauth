"""wbauth: Web Bot Auth (RFC 9421) Python SDK.

Phase 1 (current): identity + signer + JWKS + CLI keygen.
Phase 2: HTTP-client adapters + policy inspector.
"""
__version__ = "0.1.0"

# Plan 03 will add:
# from .identity import Identity, KeyPair
# from .signer import sign, SignatureHeaders
# from .normalized_request import NormalizedRequest
# __all__ = ["Identity", "KeyPair", "sign", "SignatureHeaders", "NormalizedRequest", "__version__"]
