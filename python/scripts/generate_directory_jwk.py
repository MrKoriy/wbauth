"""Generate an Ed25519 JWK (incl. private d) for the directory's signing secret.

Output: JSON-stringified JWK to stdout, ready to paste into:
    npx wrangler secret put DIRECTORY_PRIVATE_JWK

The JWK's kid is the RFC 7638 thumbprint per Phase 1 _compute_kid.

WARNING: prints a private key to stdout. Run in a private terminal.
After provisioning the secret, the local copy can be discarded -
Cloudflare stores it encrypted-at-rest.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Reuse Phase 1's RFC 7638 thumbprint helper. The script lives at
# python/scripts/ and the package source lives at python/src/wbauth/, so
# we add python/src/ to sys.path before the import.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "python" / "src"))
from wbauth.identity import _compute_kid  # type: ignore  # noqa: E402


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def main() -> int:
    key = Ed25519PrivateKey.generate()
    pub = key.public_key()
    d_bytes = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    x_bytes = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    kid = _compute_kid(pub)
    jwk = {
        "kty": "OKP",
        "crv": "Ed25519",
        "kid": kid,
        "d": b64url(d_bytes),
        "x": b64url(x_bytes),
    }
    # Single-line JSON pastes cleanly into the wrangler secret prompt.
    print(json.dumps(jwk))
    print(f"# kid (RFC 7638): {kid}", file=sys.stderr)
    print(
        "# Provision via: npx wrangler secret put DIRECTORY_PRIVATE_JWK",
        file=sys.stderr,
    )
    print("# (Paste the JSON line above when prompted.)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
