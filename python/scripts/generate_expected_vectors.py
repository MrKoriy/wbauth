"""Generate expected.json for each vector by running the Python signer.

Run: ``uv run python python/scripts/generate_expected_vectors.py``

Then COMMIT the generated ``expected.json`` files. CI will re-run the signer on
every push and assert byte-equality (``python/tests/test_vectors.py``). Re-run
this generator only if the signer's intentional behavior has changed (e.g.
RFC 9421 spec drift) — otherwise vectors should be byte-stable forever.

Vector inputs encode the JWK ``d`` field as base64url-no-pad (per RFC 7517).
We pad back to a multiple of 4 before decoding.
"""
from __future__ import annotations

import base64
import datetime
import json
import pathlib
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from wbauth import Identity, KeyPair, NormalizedRequest, sign
from wbauth.identity import _compute_kid

VECTORS_DIR = pathlib.Path(__file__).resolve().parents[2] / "spec" / "test-vectors"


def b64url_decode(s: str) -> bytes:
    """Pad b64url back to a multiple of 4 before decoding."""
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def identity_from_input(inp: dict) -> Identity:
    priv = Ed25519PrivateKey.from_private_bytes(
        b64url_decode(inp["identity"]["private_key_jwk"]["d"])
    )
    active = KeyPair(priv, _compute_kid(priv.public_key()))
    retiring = None
    if rj := inp["identity"].get("retiring_key_jwk"):
        rpriv = Ed25519PrivateKey.from_private_bytes(b64url_decode(rj["d"]))
        retiring = KeyPair(rpriv, _compute_kid(rpriv.public_key()))
    return Identity(
        active,
        inp["identity"]["signature_agent_url"],
        retiring=retiring,
    )


def generate_one(vector_dir: pathlib.Path) -> None:
    inp = json.loads((vector_dir / "input.json").read_text())
    ident = identity_from_input(inp)
    body_b64 = inp["request"].get("body")
    body = base64.b64decode(body_b64) if body_b64 else None
    req = NormalizedRequest(
        method=inp["request"]["method"],
        url=inp["request"]["url"],
        headers=dict(inp["request"]["headers"]),
        body=body,
    )
    created = datetime.datetime.fromtimestamp(
        inp["signing_params"]["created"], tz=datetime.timezone.utc
    )
    result = sign(
        req,
        ident,
        created=created,
        expires_after_seconds=inp["signing_params"]["expires_after_seconds"],
        nonce=inp["signing_params"]["nonce"],
        label=inp["signing_params"]["label"],
    )
    expected = {
        "kid": ident.kid,
        "signature_input_value": result.signature_input,
        "signature_value": result.signature,
        "signature_agent_value": result.signature_agent,
        "jwks_kid_thumbprint": ident.kid,
    }
    if inp["identity"].get("retiring_key_jwk"):
        expected["jwks_full"] = ident.export_jwks()
    (vector_dir / "expected.json").write_text(json.dumps(expected, indent=2) + "\n")
    print(f"wrote {vector_dir.name}/expected.json")


def main() -> int:
    dirs = sorted(
        d for d in VECTORS_DIR.iterdir()
        if d.is_dir() and (d / "input.json").exists()
    )
    for d in dirs:
        generate_one(d)
    print(f"\nGenerated {len(dirs)} expected.json files. COMMIT them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
