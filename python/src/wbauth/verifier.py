"""Origin-side verification of Web Bot Auth signatures (RFC 9421 profile).

    from wbauth.verifier import Verifier

    verifier = Verifier()                       # JWKS cache + nonce replay store
    agent = await verifier.verify(method, url, headers, body)
    print(agent.kid, agent.signature_agent_url)

Checks performed:

* ``Signature-Input`` / ``Signature`` present; the ``tag="web-bot-auth"``
  signature is selected; ``alg`` (if given) is ``ed25519``.
* ``created`` / ``expires`` present, not in the future / not expired (with
  ``max_skew``), validity window ≤ ``MAX_EXPIRES_SECONDS``.
* ``@authority`` covered; ``signature-agent`` covered when the header is
  sent; ``content-digest`` covered **and** matching the body when a body is
  present.
* nonce not replayed (in-memory :class:`NonceStore`, pluggable).
* key resolved from the ``Signature-Agent`` directory (or a custom
  ``key_resolver``); its RFC 7638 thumbprint must equal ``keyid``.

Also ships an ASGI middleware (FastAPI / Starlette / any ASGI app):
:class:`WebBotAuthMiddleware`.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .signer import MAX_EXPIRES_SECONDS, WEB_BOT_AUTH_TAG, normalize_authority

DIRECTORY_PATH = "/.well-known/http-message-signatures-directory"
DIRECTORY_MAX_BYTES = 64 * 1024


class VerificationError(Exception):
    """The request does not carry a valid Web Bot Auth signature."""


@dataclass(frozen=True)
class VerifiedAgent:
    kid: str
    signature_agent_url: str | None
    label: str
    created: int
    expires: int
    nonce: str | None
    covered: tuple[str, ...]
    jwk: dict = field(repr=False)


# ---------- Structured-field parsing (just what the profile needs) ----------

_SF_STRING = r'"(?:[^"\\]|\\.)*"'
_PARAM = rf';\s*([a-z*][a-z0-9_.*-]*)(?:=({_SF_STRING}|-?\d+(?:\.\d+)?|\?[01]|[A-Za-z*][^;,\s]*))?'
_SIG_INPUT_RE = re.compile(
    rf'\s*([a-z*][a-z0-9_.*-]*)=(\((?:\s*{_SF_STRING}(?:;[^\s)"]+)*)*\s*\))((?:{_PARAM})*)'
)
_SIG_RE = re.compile(r"\s*([a-z*][a-z0-9_.*-]*)=:([A-Za-z0-9+/=]*):")


def _unquote(v: str) -> str:
    if v.startswith('"'):
        return re.sub(r"\\(.)", r"\1", v[1:-1])
    return v


def _parse_params(s: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for m in re.finditer(_PARAM, s):
        k, v = m.group(1), m.group(2)
        if v is None:
            out[k] = True
        elif v.startswith('"'):
            out[k] = _unquote(v)
        elif re.fullmatch(r"-?\d+", v):
            out[k] = int(v)
        else:
            out[k] = v
    return out


def parse_signature_input(value: str) -> list[tuple[str, str, list[str], dict[str, Any]]]:
    """→ ``[(label, raw_params_after_label, components, params), …]``."""
    out = []
    pos = 0
    while pos < len(value):
        m = _SIG_INPUT_RE.match(value, pos)
        if not m:
            raise VerificationError("malformed Signature-Input")
        label, inner, params = m.group(1), m.group(2), m.group(3)
        comps = [_unquote(c) for c in re.findall(_SF_STRING, inner)]
        if re.search(r'"\s*;', inner):
            raise VerificationError("component parameters are not supported")
        out.append((label, inner + params, comps, _parse_params(params)))
        pos = m.end()
        while pos < len(value) and value[pos] in " ,":
            pos += 1
    return out


def parse_signature(value: str) -> dict[str, bytes]:
    out = {}
    for m in _SIG_RE.finditer(value):
        out[m.group(1)] = base64.b64decode(m.group(2))
    return out


def _lower(headers: Mapping[str, str] | Any) -> dict[str, str]:
    items = headers.items() if hasattr(headers, "items") else headers
    out: dict[str, str] = {}
    for k, v in items:
        k = k.decode("latin-1") if isinstance(k, bytes) else k
        v = v.decode("latin-1") if isinstance(v, bytes) else v
        key = k.lower()
        out[key] = f"{out[key]}, {v.strip()}" if key in out else v.strip()
    return out


def _component_value(name: str, method: str, url: str, headers: dict[str, str],
                     authority: str | None) -> str:
    parts = httpx.URL(url)
    if name == "@authority":
        return authority or normalize_authority(url)
    if name == "@method":
        return method.upper()
    if name == "@scheme":
        return parts.scheme.lower()
    if name == "@target-uri":
        return str(parts)
    if name == "@path":
        return parts.raw_path.split(b"?", 1)[0].decode("ascii") or "/"
    if name == "@query":
        q = parts.query.decode("ascii")
        return f"?{q}"
    if name.startswith("@"):
        raise VerificationError(f"unsupported derived component {name!r}")
    if name not in headers:
        raise VerificationError(f"covered header {name!r} missing")
    return headers[name]


# ---------- Replay protection ----------


class NonceStore:
    """In-memory TTL set of seen nonces. Swap for Redis etc. in multi-process
    deployments (implement ``seen(nonce, expires_at) -> bool``)."""

    def __init__(self, maxsize: int = 100_000):
        self._seen: dict[str, float] = {}
        self._maxsize = maxsize

    def seen(self, nonce: str, expires_at: float) -> bool:
        now = time.time()
        if len(self._seen) >= self._maxsize:
            self._seen = {n: e for n, e in self._seen.items() if e > now}
            if len(self._seen) >= self._maxsize:  # still full: drop oldest
                for n in list(self._seen)[: self._maxsize // 10]:
                    del self._seen[n]
        if nonce in self._seen and self._seen[nonce] > now:
            return True
        self._seen[nonce] = expires_at
        return False


# ---------- Key resolution ----------


def _thumbprint(jwk: dict) -> str:
    canonical = json.dumps({"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"]},
                           sort_keys=True, separators=(",", ":"))
    return base64.urlsafe_b64encode(hashlib.sha256(canonical.encode()).digest()).rstrip(b"=").decode()


def _directory_url(signature_agent: str) -> str:
    u = httpx.URL(signature_agent)
    if u.scheme != "https":
        raise VerificationError("Signature-Agent must be an https:// URL")
    if u.path in ("", "/"):
        return str(u.copy_with(path=DIRECTORY_PATH, query=None, fragment=None))
    return str(u)


class JwksCache:
    """Fetches + caches signing directories (SSRF-guarded, size-capped)."""

    def __init__(self, ttl: float = 300.0, client: httpx.AsyncClient | None = None,
                 allow_private: bool = False):
        self._ttl = ttl
        self._client = client
        self._allow_private = allow_private
        self._entries: dict[str, tuple[float, list[dict]]] = {}

    async def keys(self, url: str) -> list[dict]:
        hit = self._entries.get(url)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        from .policy.inspector import _resolves_private

        host = httpx.URL(url).host
        if not self._allow_private and await _resolves_private(host):
            raise VerificationError(f"directory host {host!r} is private")
        client = self._client or httpx.AsyncClient(timeout=3.0)
        try:
            async with client.stream("GET", url, follow_redirects=False, headers={
                "accept": "application/http-message-signatures-directory+json, application/json",
            }) as r:
                if r.status_code != 200:
                    raise VerificationError(f"directory {url} answered {r.status_code}")
                buf = bytearray()
                async for chunk in r.aiter_bytes():
                    buf += chunk
                    if len(buf) > DIRECTORY_MAX_BYTES:
                        raise VerificationError("directory too large")
        except httpx.HTTPError as e:
            raise VerificationError(f"directory unreachable: {e}") from e
        finally:
            if self._client is None:
                await client.aclose()
        try:
            keys = json.loads(bytes(buf)).get("keys", [])
            assert isinstance(keys, list)
        except Exception as e:  # noqa: BLE001
            raise VerificationError("directory is not a JWKS") from e
        self._entries[url] = (time.monotonic() + self._ttl, keys)
        return keys


KeyResolver = Callable[[str, "str | None"], Awaitable["dict | None"]]


class Verifier:
    def __init__(
        self,
        *,
        key_resolver: KeyResolver | None = None,
        jwks_cache: JwksCache | None = None,
        nonce_store: NonceStore | None = None,
        max_skew: int = 5,
        require_nonce: bool = False,
    ):
        self._resolver = key_resolver
        self._jwks = jwks_cache or JwksCache()
        self._nonces = nonce_store if nonce_store is not None else NonceStore()
        self._skew = max_skew
        self._require_nonce = require_nonce

    async def _resolve(self, kid: str, signature_agent: str | None) -> dict:
        if self._resolver is not None:
            jwk = await self._resolver(kid, signature_agent)
            if jwk is None:
                raise VerificationError(f"unknown keyid {kid!r}")
            return jwk
        if not signature_agent:
            raise VerificationError("no Signature-Agent and no key_resolver configured")
        for k in await self._jwks.keys(_directory_url(signature_agent)):
            if isinstance(k, dict) and k.get("kty") == "OKP" and k.get("crv") == "Ed25519":
                try:
                    if _thumbprint(k) == kid:
                        return k
                except (KeyError, TypeError):
                    continue
        raise VerificationError(f"keyid {kid!r} not published by {signature_agent}")

    async def verify(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str] | Any,
        body: bytes | None = None,
        *,
        authority: str | None = None,
        now: float | None = None,
    ) -> VerifiedAgent:
        """Verify a request; raises :class:`VerificationError` on any failure.

        ``authority`` overrides the value derived from ``url`` (pass the
        ``Host`` header when the app sits behind a proxy that rewrites URLs).
        """
        h = _lower(headers)
        if "signature-input" not in h or "signature" not in h:
            raise VerificationError("request is not signed")
        sigs = parse_signature(h["signature"])
        candidates = [c for c in parse_signature_input(h["signature-input"])
                      if c[3].get("tag") == WEB_BOT_AUTH_TAG]
        if not candidates:
            raise VerificationError('no signature with tag="web-bot-auth"')
        label, raw_params, comps, params = candidates[0]
        if label not in sigs:
            raise VerificationError(f"Signature has no {label!r} member")
        if params.get("alg", "ed25519") != "ed25519":
            raise VerificationError("only alg=ed25519 is supported")
        created, expires, kid = params.get("created"), params.get("expires"), params.get("keyid")
        if not isinstance(created, int) or not isinstance(expires, int) or not isinstance(kid, str):
            raise VerificationError("created, expires and keyid are required")
        t = time.time() if now is None else now
        if created > t + self._skew:
            raise VerificationError("signature created in the future")
        if expires < t - self._skew:
            raise VerificationError("signature expired")
        if expires - created > MAX_EXPIRES_SECONDS or expires <= created:
            raise VerificationError("invalid validity window")
        if "@authority" not in comps:
            raise VerificationError("@authority must be covered")
        signature_agent = None
        if "signature-agent" in h:
            if "signature-agent" not in comps:
                raise VerificationError("Signature-Agent sent but not covered")
            signature_agent = _unquote(h["signature-agent"].strip())
        if body:
            if "content-digest" not in comps:
                raise VerificationError("request has a body but content-digest is not covered")
            m = re.search(r"(?:^|,)\s*sha-256=:([A-Za-z0-9+/=]+):", h.get("content-digest", ""))
            if not m or base64.b64decode(m.group(1)) != hashlib.sha256(body).digest():
                raise VerificationError("Content-Digest does not match the body")
        nonce = params.get("nonce")
        if self._require_nonce and not nonce:
            raise VerificationError("nonce required")

        lines = [f'"{c}": {_component_value(c, method, url, h, authority)}' for c in comps]
        lines.append(f'"@signature-params": {raw_params}')
        base = "\n".join(lines).encode()

        jwk = await self._resolve(kid, signature_agent)
        try:
            x = base64.urlsafe_b64decode(jwk["x"] + "=" * (-len(jwk["x"]) % 4))
            Ed25519PublicKey.from_public_bytes(x).verify(sigs[label], base)
        except (InvalidSignature, ValueError, KeyError) as e:
            raise VerificationError("signature does not verify") from e
        if nonce and self._nonces.seen(str(nonce), expires + self._skew):
            raise VerificationError("nonce replayed")
        return VerifiedAgent(kid=kid, signature_agent_url=signature_agent, label=label,
                             created=created, expires=expires,
                             nonce=str(nonce) if nonce else None,
                             covered=tuple(comps), jwk=dict(jwk))


async def verify_request(method: str, url: str, headers: Any, body: bytes | None = None,
                         **kwargs: Any) -> VerifiedAgent:
    """One-shot helper using a module-level :class:`Verifier`."""
    return await _DEFAULT.verify(method, url, headers, body, **kwargs)


_DEFAULT = Verifier()


class WebBotAuthMiddleware:
    """ASGI middleware. Puts the :class:`VerifiedAgent` (or ``None``) into
    ``scope["state"]["web_bot_auth"]`` (``request.state.web_bot_auth`` in
    Starlette/FastAPI). With ``required=True`` unsigned/invalid requests get 401.
    """

    def __init__(self, app, *, verifier: Verifier | None = None, required: bool = False,
                 max_body: int = 10 * 1024 * 1024):
        self.app = app
        self.verifier = verifier or Verifier()
        self.required = required
        self.max_body = max_body

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = [(k.decode("latin-1"), v.decode("latin-1")) for k, v in scope["headers"]]
        signed = any(k.lower() == "signature-input" for k, _ in headers)
        body = b""
        messages = []
        if signed:
            more = True
            while more:
                msg = await receive()
                messages.append(msg)
                body += msg.get("body", b"")
                more = msg.get("more_body", False)
                if len(body) > self.max_body:
                    return await self._reject(send, "body too large")
        agent = None
        if signed:
            host = next((v for k, v in headers if k.lower() == "host"), "")
            scheme = scope.get("scheme", "https")
            qs = scope.get("query_string", b"").decode("latin-1")
            url = f"{scheme}://{host}{scope.get('raw_path', scope['path'].encode()).decode('latin-1')}"
            if qs and "?" not in url:
                url += f"?{qs}"
            try:
                agent = await self.verifier.verify(
                    scope["method"], url, headers, body or None, authority=host.lower() or None
                )
            except VerificationError as e:
                if self.required:
                    return await self._reject(send, str(e))
        elif self.required:
            return await self._reject(send, "request is not signed")
        scope.setdefault("state", {})["web_bot_auth"] = agent

        async def replay():
            return messages.pop(0) if messages else await receive()

        return await self.app(scope, replay if signed else receive, send)

    @staticmethod
    async def _reject(send, reason: str):
        body = json.dumps({"error": "web_bot_auth", "reason": reason}).encode()
        await send({"type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
