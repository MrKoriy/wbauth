"""Small static JWKS server for self-hosters (D-50).

Serves the JWKS at both
``/.well-known/http-message-signatures-directory`` (the directory root the
draft defines) and ``/.well-known/http-message-signatures-directory/{kid}``,
with content-type per draft-meunier-http-message-signatures-directory.

* GET and HEAD; query strings are ignored.
* Optional response signatures (``sign_keys``): one ``binding<i>``
  signature per key over ``"@authority";req`` with
  ``tag="http-message-signatures-directory"`` — byte-compatible with
  web-bot-auth's ``directoryResponseHeaders``.
* Optional TLS (``tls_cert`` / ``tls_key``) — Signature-Agent must be https.
* Binds 127.0.0.1 by default.

NO registration, NO list endpoints — the hosted Worker is the full directory.
"""
from __future__ import annotations

import base64
import http.server
import json
import re
import ssl
import time
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit

CONTENT_TYPE = "application/http-message-signatures-directory+json"
DIRECTORY_TAG = "http-message-signatures-directory"
PATH_RE = re.compile(r"^/\.well-known/http-message-signatures-directory(?:/([^/]+))?/?$")
SIGNATURE_TTL = 300


def _load_signers(paths: Iterable[str | Path]):
    from ..identity import _load_keypair

    return [_load_keypair(Path(p).expanduser()) for p in paths]


def directory_signature_headers(authority: str, signers, now: int | None = None) -> dict:
    created = int(time.time()) if now is None else now
    expires = created + SIGNATURE_TTL
    sigs, inputs = [], []
    for i, pair in enumerate(signers):
        label = f"binding{i}"
        params = (
            f'("@authority";req);created={created};keyid="{pair.kid}";alg="ed25519"'
            f';expires={expires};tag="{DIRECTORY_TAG}"'
        )
        base = f'"@authority";req: {authority}\n"@signature-params": {params}'
        raw = pair.private_key.sign(base.encode())
        sigs.append(f"{label}=:{base64.b64encode(raw).decode()}:")
        inputs.append(f"{label}={params}")
    return {"Signature": ", ".join(sigs), "Signature-Input": ", ".join(inputs)}


def make_handler(jwks_path: Path, sign_keys: Iterable[str | Path] = ()):
    jwks_bytes = Path(jwks_path).read_bytes()
    jwks = json.loads(jwks_bytes)
    served_kids = {k["kid"] for k in jwks.get("keys", [])}
    signers = _load_signers(sign_keys)
    unknown = [p.kid for p in signers if p.kid not in served_kids]
    if unknown:
        raise ValueError(f"--sign-key kid(s) not in the JWKS: {unknown}")

    class JWKSHandler(http.server.BaseHTTPRequestHandler):
        def _respond(self, with_body: bool):
            m = PATH_RE.match(urlsplit(self.path).path)
            if not m or (m.group(1) is not None and m.group(1) not in served_kids):
                self.send_error(404, "kid not served by this JWKS")
                return
            self.send_response(200)
            self.send_header("content-type", CONTENT_TYPE)
            self.send_header("content-length", str(len(jwks_bytes)))
            self.send_header("cache-control", "public, max-age=300")
            if signers:
                authority = (self.headers.get("host") or "").lower()
                for k, v in directory_signature_headers(authority, signers).items():
                    self.send_header(k, v)
            self.end_headers()
            if with_body:
                self.wfile.write(jwks_bytes)

        def do_GET(self):
            self._respond(True)

        def do_HEAD(self):
            self._respond(False)

        def log_message(self, format, *args):
            pass  # quiet stdlib request log

    return JWKSHandler


def serve(
    jwks_path: str | Path,
    port: int = 8080,
    *,
    host: str = "127.0.0.1",
    sign_keys: Iterable[str | Path] = (),
    tls_cert: str | None = None,
    tls_key: str | None = None,
) -> None:
    handler = make_handler(Path(jwks_path), sign_keys)
    server = http.server.ThreadingHTTPServer((host, port), handler)
    scheme = "http"
    if tls_cert:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(tls_cert, tls_key)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        scheme = "https"
    print(f"Serving JWKS from {jwks_path} on {scheme}://{host}:{port}")
    server.serve_forever()
