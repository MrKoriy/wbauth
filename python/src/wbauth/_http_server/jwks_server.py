"""Tiny static JWKS server for self-hosters (D-50 — ≤30 LOC executable)."""
# Serves a single JWKS file at /.well-known/http-message-signatures-directory/{kid}
# with content-type per draft-meunier-http-message-signatures-directory-05.
# NO registration, NO list endpoints — the hosted Worker
# (https://wbauth.silov801.workers.dev) is the full directory.
from __future__ import annotations
import http.server
import json
import re
from pathlib import Path

CONTENT_TYPE = "application/http-message-signatures-directory+json"
PATH_RE = re.compile(r"^/\.well-known/http-message-signatures-directory/([^/]+)$")


def make_handler(jwks_path: Path):
    jwks_bytes = jwks_path.read_bytes()
    jwks = json.loads(jwks_bytes)
    served_kids = {k["kid"] for k in jwks.get("keys", [])}

    class JWKSHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            m = PATH_RE.match(self.path)
            if not m or m.group(1) not in served_kids:
                self.send_error(404, "kid not served by this JWKS")
                return
            self.send_response(200)
            self.send_header("content-type", CONTENT_TYPE)
            self.send_header("content-length", str(len(jwks_bytes)))
            self.send_header("cache-control", "public, max-age=300")
            self.end_headers()
            self.wfile.write(jwks_bytes)

        def log_message(self, format, *args):
            pass  # quiet stdlib request log

    return JWKSHandler


def serve(jwks_path: str | Path, port: int = 8080) -> None:
    handler = make_handler(Path(jwks_path))
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), handler)
    print(f"Serving JWKS from {jwks_path} on port {port}")
    server.serve_forever()
