"""Public adapter surface for wbauth (Phase 2).

Re-exports the three drop-in adapters so users can write:
    from wbauth.adapters import WebBotAuth, WebBotAuthAdapter, attach_signing
"""
from .httpx_auth import (
    AsyncSigningTransport,
    RedirectNotSignedWarning,
    SigningTransport,
    WebBotAuth,
    signed_async_client,
    signed_client,
)
from .playwright import attach_signing
from .requests_adapter import WebBotAuthAdapter, WebBotAuthTransport, signed_session

__all__ = [
    "AsyncSigningTransport",
    "RedirectNotSignedWarning",
    "SigningTransport",
    "signed_async_client",
    "signed_client",
    "WebBotAuth",
    "WebBotAuthAdapter",
    "WebBotAuthTransport",
    "attach_signing",
    "signed_session",
]
