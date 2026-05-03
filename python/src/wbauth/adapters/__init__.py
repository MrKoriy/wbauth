"""Public adapter surface for wbauth (Phase 2).

Re-exports the three drop-in adapters so users can write:
    from wbauth.adapters import WebBotAuth, WebBotAuthAdapter, attach_signing
"""
from .httpx_auth import WebBotAuth
from .playwright import attach_signing
from .requests_adapter import WebBotAuthAdapter

__all__ = ["WebBotAuth", "WebBotAuthAdapter", "attach_signing"]
