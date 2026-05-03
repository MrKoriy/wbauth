"""requests.auth.AuthBase adapter for Web Bot Auth (ADAPT-02).

Delegates crypto to wbauth.sign() (L-02). Stateless per D-15. If
`identity.user_agent` is set AND the outgoing request has no User-Agent
header, the adapter sets it; otherwise UA is left untouched
(Plan 02-01 open question #4). For POST/PUT/PATCH with a body, computes
Content-Digest if absent (RFC 9530, sha-256).
"""
from __future__ import annotations
from requests.auth import AuthBase
from wbauth.adapters._utils import ensure_content_digest
from wbauth.normalized_request import NormalizedRequest
from wbauth.signer import sign


class WebBotAuthAdapter(AuthBase):
    """Drop-in requests Auth:
        session.get(url, auth=WebBotAuthAdapter(identity))
    """

    def __init__(self, identity):
        self._identity = identity

    def __call__(self, prepared_request):
        body = prepared_request.body
        if isinstance(body, str):
            body = body.encode("utf-8")
        headers = dict(prepared_request.headers)
        ensure_content_digest(prepared_request.method, headers, body)
        if "Content-Digest" in headers:
            prepared_request.headers["Content-Digest"] = headers["Content-Digest"]
        normalized = NormalizedRequest(
            method=prepared_request.method, url=prepared_request.url,
            headers=headers, body=body,
        )
        sig = sign(normalized, self._identity)
        prepared_request.headers["Signature"] = sig.signature
        prepared_request.headers["Signature-Input"] = sig.signature_input
        prepared_request.headers["Signature-Agent"] = sig.signature_agent
        ua = getattr(self._identity, "user_agent", None)
        if ua and "User-Agent" not in prepared_request.headers:
            prepared_request.headers["User-Agent"] = ua
        return prepared_request
