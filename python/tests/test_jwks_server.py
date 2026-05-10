"""Tests for the wbauth._http_server.jwks_server module (CLI-05, D-50).

Spawns the stdlib ThreadingHTTPServer in a daemon background thread per test
and exercises it over loopback. ThreadingHTTPServer has no clean cross-thread
shutdown without a server reference; daemon=True ensures the server thread
dies with the test process. Each test picks a fresh ephemeral port via SO_REUSEADDR
to avoid port collisions on parallel test runs.
"""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request
from contextlib import closing

import pytest

from wbauth._http_server.jwks_server import CONTENT_TYPE, make_handler, serve
from wbauth.identity import Identity


def _free_port() -> int:
    """Pick an unused TCP port. Race-window is small (server binds within 0.3s)."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture
def jwks_file(tmp_path):
    """Generate a real Ed25519 keypair and write its public JWKS."""
    keypath = tmp_path / "k.pem"
    identity = Identity.load_or_generate(keypath, signature_agent_url="https://example.com")
    jwks_path = tmp_path / "k.jwks.json"
    jwks_path.write_text(json.dumps(identity.export_jwks()))
    return jwks_path, identity.kid


def _start_server(jwks_path, port):
    """Helper — start server in a daemon thread, give it 0.3s to bind."""
    t = threading.Thread(target=serve, args=(str(jwks_path), port), daemon=True)
    t.start()
    time.sleep(0.3)
    return t


def test_make_handler_returns_class(jwks_file):
    jwks_path, _ = jwks_file
    handler_cls = make_handler(jwks_path)
    assert handler_cls.__name__ == "JWKSHandler"


def test_serve_known_kid_returns_200(jwks_file):
    """Happy path: GET /.well-known/.../{served-kid} → 200 + correct content-type."""
    jwks_path, kid = jwks_file
    port = _free_port()
    _start_server(jwks_path, port)
    url = f"http://127.0.0.1:{port}/.well-known/http-message-signatures-directory/{kid}"
    with urllib.request.urlopen(url, timeout=2) as r:
        assert r.status == 200
        assert r.headers.get("content-type") == CONTENT_TYPE
        body = r.read()
    served = json.loads(body)
    assert any(k["kid"] == kid for k in served["keys"])


def test_serve_unknown_kid_returns_404(jwks_file):
    """Unknown kid → 404 (D-50: serve only serves the kids in the file)."""
    jwks_path, _ = jwks_file
    port = _free_port()
    _start_server(jwks_path, port)
    url = f"http://127.0.0.1:{port}/.well-known/http-message-signatures-directory/unknownkid"
    with pytest.raises(urllib.request.HTTPError) as exc:
        urllib.request.urlopen(url, timeout=2)
    assert exc.value.code == 404


def test_serve_random_path_returns_404(jwks_file):
    """Random path → 404."""
    jwks_path, _ = jwks_file
    port = _free_port()
    _start_server(jwks_path, port)
    url = f"http://127.0.0.1:{port}/random_path"
    with pytest.raises(urllib.request.HTTPError) as exc:
        urllib.request.urlopen(url, timeout=2)
    assert exc.value.code == 404


def test_serve_root_well_known_returns_404(jwks_file):
    """D-50: wbauth serve does NOT replicate the directory's-own-kid endpoint.

    The hosted Worker publishes its own JWKS at the root well-known path
    (no kid suffix); `wbauth serve` is single-JWKS only and returns 404 there.
    """
    jwks_path, _ = jwks_file
    port = _free_port()
    _start_server(jwks_path, port)
    url = f"http://127.0.0.1:{port}/.well-known/http-message-signatures-directory"
    with pytest.raises(urllib.request.HTTPError) as exc:
        urllib.request.urlopen(url, timeout=2)
    assert exc.value.code == 404


def test_served_jwks_has_correct_cache_control(jwks_file):
    """Cache-Control: public, max-age=300 — matches the hosted Worker's read endpoint."""
    jwks_path, kid = jwks_file
    port = _free_port()
    _start_server(jwks_path, port)
    url = f"http://127.0.0.1:{port}/.well-known/http-message-signatures-directory/{kid}"
    with urllib.request.urlopen(url, timeout=2) as r:
        cc = r.headers.get("cache-control", "")
    assert "max-age=300" in cc
