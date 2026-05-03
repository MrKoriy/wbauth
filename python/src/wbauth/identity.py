"""Identity, KeyPair, and key-file helpers for the wbauth SDK.

Implements IDENT-01 (keygen + 0o600 race-free), IDENT-02 (long-lived Identity),
IDENT-06 (RFC 7638 thumbprint as kid), IDENT-07 (active + retiring multi-key),
and IDENT-08 (REDACTED repr/str + pickle refusal).

Source-of-truth: 01-RESEARCH.md §3 ("Identity API Implementation Reference").
Security pitfalls addressed: PITFALLS Pitfall 4 (key leakage), Pitfall 8
(Windows chmod no-op).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from ._redaction import redacted_repr

# ---------- Module constants ----------

DEFAULT_KEY_PATH = Path("~/.config/wbauth/key.pem").expanduser()
"""Default path for the active signing key. Created with mode 0o600 on POSIX.

Follows XDG-ish convention: never `/tmp/`, never `~/.ssh/`. The CLI prints the
exact path on `wbauth keygen` so users always know where their key lives.
"""

# RFC 9421 Appendix B.1.4 publicly-known test key — NEVER use in production.
# Verified live 2026-05-03 against:
# https://http-message-signatures-example.research.cloudflare.com/.well-known/http-message-signatures-directory
_TEST_KEY_D = "n4Ni-HpISpVObnQMW0wOhCKROaIKqKtW_2ZYb2p9KcU"


# ---------- Public dataclass ----------


@dataclass(frozen=True)
class KeyPair:
    """A single Ed25519 keypair with its precomputed kid.

    `kid` is the RFC 7638 JWK thumbprint of the public key, base64url-no-pad.
    For the RFC 9421 Appendix B.1.4 test key, kid == 'poqkLGiymh_W0uP6PZFw-dvez3QJT5SolqXBCW38r0U'.
    """

    private_key: Ed25519PrivateKey
    kid: str

    def public_jwk(self) -> dict:
        """Return the public JWK dict (kty/crv/kid/x). Never includes 'd'."""
        raw = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return {
            "crv": "Ed25519",
            "kty": "OKP",
            "kid": self.kid,
            "x": base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii"),
        }


# ---------- Identity ----------


class Identity:
    """Long-lived agent identity. Holds Ed25519 keypair(s) + signature-agent URL.

    Constructed once at process start (typically via `Identity.load_or_generate`)
    and passed everywhere by reference. The `signer.sign()` function reads the
    active key via `_active.private_key` and the kid via `.kid`.

    Multi-key rotation (IDENT-07): an Identity may also hold a `_retiring`
    keypair. After `Identity.rotate(new_path)`, the new key becomes `_active`
    and the previous `_active` is demoted to `_retiring`. The retiring key is
    EXPORTED in the JWKS (so verifiers can still validate signatures from
    in-flight requests) but is NEVER used to sign new requests.
    """

    def __init__(
        self,
        active: KeyPair,
        signature_agent_url: str,
        *,
        user_agent: Optional[str] = None,
        retiring: Optional[KeyPair] = None,
    ):
        if not signature_agent_url.startswith("https://"):
            raise ValueError(
                f"signature_agent_url must be https://, got: {signature_agent_url!r}"
            )
        self._active = active
        self._retiring = retiring
        self.signature_agent_url = signature_agent_url
        self.user_agent = user_agent

    # ---------- Public read-only API ----------

    @property
    def kid(self) -> str:
        """The active key's kid (used as `keyid=` param in Signature-Input)."""
        return self._active.kid

    def export_jwks(self) -> dict:
        """Export the public JWKS document.

        Returns `{"keys": [active_jwk]}` if no retiring key is held, or
        `{"keys": [active_jwk, retiring_jwk]}` after a rotation. Active is
        always first. Verifiers select by `kid`.
        """
        keys = [self._active.public_jwk()]
        if self._retiring is not None:
            keys.append(self._retiring.public_jwk())
        return {"keys": keys}

    def rotate(self, new_path: Path | str | None = None) -> "Identity":
        """IDENT-07: generate a new active key, demote current to retiring.

        Returns a NEW Identity (immutable update — the old Identity is unchanged).
        Any previously-retiring key is dropped (only one overlap window).

        Args:
            new_path: where to write the new keypair. Defaults to DEFAULT_KEY_PATH.
                On rotation, callers typically want a path distinct from the
                current key (the old key file remains in place).
        """
        path = Path(new_path).expanduser() if new_path else DEFAULT_KEY_PATH
        new_pair = _generate_keypair_to(path)
        return Identity(
            active=new_pair,
            signature_agent_url=self.signature_agent_url,
            user_agent=self.user_agent,
            retiring=self._active,  # demote current → retiring (drop existing _retiring)
        )

    # ---------- Constructors ----------

    @classmethod
    def load_or_generate(
        cls,
        path: str | Path = DEFAULT_KEY_PATH,
        *,
        signature_agent_url: str,
        user_agent: Optional[str] = None,
    ) -> "Identity":
        """Primary entry point per D-09.

        If `path` exists, load it (refusing wider-than-0o600 mode on POSIX and
        rejecting non-Ed25519 keys). Otherwise generate a fresh keypair into
        `path` with 0o600 race-free creation.
        """
        path = Path(path).expanduser()
        if path.exists():
            pair = _load_keypair(path)
        else:
            pair = _generate_keypair_to(path)
        return cls(pair, signature_agent_url, user_agent=user_agent)

    @classmethod
    def from_test_key(cls, signature_agent_url: str) -> "Identity":
        """Construct from the RFC 9421 Appendix B.1.4 publicly-known test key.

        For tests + Cloudflare debug smoke checks. NEVER use in production —
        this private key is published in the RFC and known to everyone.

        Does NOT write any file to disk.
        """
        # Pad b64url back to multiple of 4 before decoding.
        padded = _TEST_KEY_D + "=" * (-len(_TEST_KEY_D) % 4)
        d = base64.urlsafe_b64decode(padded)
        key = Ed25519PrivateKey.from_private_bytes(d)
        return cls(KeyPair(key, _compute_kid(key.public_key())), signature_agent_url)

    # ---------- Redaction guarantees (IDENT-08) ----------

    def __repr__(self) -> str:
        return redacted_repr(
            "Identity",
            kid=self.kid,
            sig_agent=self.signature_agent_url,
        )

    # str() returns the same REDACTED form so f-strings + print() are safe.
    __str__ = __repr__

    def __reduce__(self):
        # Refuse pickling — would serialize the private key bytes.
        raise TypeError(
            "Identity is not pickleable (would leak private key material)"
        )


# ---------- Helpers (module-private) ----------


def _compute_kid(public_key: Ed25519PublicKey) -> str:
    """RFC 7638 JWK thumbprint of an Ed25519 public key.

    Steps:
    1. Build the canonical JWK dict with ONLY the required members
       (crv, kty, x) — no kid, no use, no alg.
    2. Serialize with `sort_keys=True` (alphabetical) and no whitespace.
    3. SHA-256 the UTF-8 bytes.
    4. base64url-encode without padding.
    """
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    jwk = {
        "crv": "Ed25519",
        "kty": "OKP",
        "x": base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii"),
    }
    canonical = json.dumps(jwk, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(canonical).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _load_keypair(path: Path) -> KeyPair:
    """Load an Ed25519 PEM keyfile, refusing wider-than-0o600 mode on POSIX.

    Raises:
        PermissionError: file mode is wider than 0o600 on POSIX. Message
            includes both the actual octal mode and the remediation command.
        TypeError: file is a valid PEM but not an Ed25519 key.
    """
    if sys.platform != "win32":
        mode = os.stat(path).st_mode & 0o777
        if mode & 0o077:
            raise PermissionError(
                f"Key file {path} has mode {oct(mode)}; expected 0o600. "
                f"Fix: chmod 600 {path}"
            )
    else:
        # Windows: chmod is a no-op (Pitfall 8). Warn loudly so the user knows
        # the SDK is not enforcing perms — they need NTFS ACLs / a vault.
        warnings.warn(
            f"Windows detected — file permissions on {path} cannot be enforced "
            "via POSIX mode. Use NTFS ACLs or store the key in a per-user "
            "secrets vault.",
            stacklevel=2,
        )
    pem = path.read_bytes()
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError(f"Expected Ed25519, got {type(key).__name__}")
    return KeyPair(key, _compute_kid(key.public_key()))


def _generate_keypair_to(path: Path) -> KeyPair:
    """Generate a fresh Ed25519 keypair and write it PEM-encoded to `path`.

    Uses `os.open(O_WRONLY | O_CREAT | O_EXCL, 0o600)` so:
    - The file is created at mode 0o600 in the syscall itself (no race window
      where it could be world-readable).
    - If the file already exists, FileExistsError is raised — refuses overwrite.

    The parent directory is created with the umask-default mode (typically
    0o700 with restrictive umask, 0o755 otherwise). This is the user's config
    dir; we do not chmod the parent because that may surprise users with
    multi-app config layouts.
    """
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        # Belt + suspenders: O_EXCL would catch this too, but raising here
        # gives a cleaner stack trace than a low-level OSError.
        raise FileExistsError(f"Key already exists at {path}; refuse overwrite")

    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, pem)
    finally:
        os.close(fd)
    return KeyPair(key, _compute_kid(key.public_key()))
