"""requests ``AuthBase`` adapter: signs every prepared request.

    requests.get(url, auth=WebBotAuthAdapter(identity))
    session.auth = WebBotAuthAdapter(identity)

Streaming bodies (generators, file objects) are buffered once so the
Content-Digest can be computed; the buffered bytes are what gets sent.

**Redirects.** ``requests`` does not re-run per-request ``auth=`` on
redirect hops, so the first hop's signature (bound to the first host's
``@authority``) would be replayed to the redirect target. Use
:func:`signed_session` — or mount :class:`WebBotAuthTransport` yourself —
to re-sign every hop::

    session = signed_session(identity)
    session.get("https://example.com/")
"""
from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from requests.auth import AuthBase

from wbauth.adapters._utils import ensure_content_digest, should_apply_user_agent
from wbauth.normalized_request import NormalizedRequest
from wbauth.signer import sign


def _buffer_body(prepared_request) -> bytes | None:
    body = prepared_request.body
    if body is None or isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    if isinstance(body, (bytearray, memoryview)):
        return bytes(body)
    if hasattr(body, "read"):
        data = body.read()
    else:  # iterable of chunks (generator, list, …)
        data = b"".join(c.encode("utf-8") if isinstance(c, str) else bytes(c) for c in body)
    if isinstance(data, str):
        data = data.encode("utf-8")
    prepared_request.body = data
    prepared_request.headers.pop("Transfer-Encoding", None)
    prepared_request.headers["Content-Length"] = str(len(data))
    return data


class WebBotAuthAdapter(AuthBase):
    """Drop-in ``requests`` auth that adds Web Bot Auth signatures."""

    def __init__(self, identity):
        self._identity = identity

    def __call__(self, prepared_request):
        body = _buffer_body(prepared_request)
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
        if ua and should_apply_user_agent(prepared_request.headers.get("User-Agent")):
            prepared_request.headers["User-Agent"] = ua
        return prepared_request


class WebBotAuthTransport(HTTPAdapter):
    """Transport adapter that signs at send time — covers every redirect hop."""

    def __init__(self, identity, *args, **kwargs):
        self._auth = WebBotAuthAdapter(identity)
        super().__init__(*args, **kwargs)

    def send(self, request, *args, **kwargs):  # type: ignore[override]
        self._auth(request)
        return super().send(request, *args, **kwargs)


def signed_session(identity, session: requests.Session | None = None) -> requests.Session:
    """Return a ``requests.Session`` whose every request (and redirect) is signed."""
    s = session or requests.Session()
    transport = WebBotAuthTransport(identity)
    s.mount("https://", transport)
    s.mount("http://", transport)
    return s
