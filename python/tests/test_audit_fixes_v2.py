"""Regression tests for the second (25-item) audit."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys

import httpx
import pytest

from wbauth import Identity, NormalizedRequest, sign
from wbauth.adapters import signed_client
from wbauth.adapters._utils import ensure_content_digest, make_sign_decider
from wbauth.policy import inspector as insp
from wbauth.policy.cache import PolicyCache, _parse_cache_control
from wbauth.policy.parsers.llms_txt import parse_llms_txt
from wbauth.policy.parsers.robots import parse_content_signals, parse_robots, product_token
from wbauth.policy.parsers.signing_directory import parse_signing_directory
from wbauth.policy.verdict import restriction_applies
from wbauth.verifier import Verifier, VerificationError

URL = "https://agent.example/.well-known/http-message-signatures-directory"


@pytest.fixture(autouse=True)
def _reset():
    insp._reset_cache_for_tests()
    yield
    insp._reset_cache_for_tests()


# ---- #2 Signature-Agent validation ---------------------------------------

@pytest.mark.parametrize("bad", [
    'https://a.example/x"', "https://a.example/x\r\nX-Evil: 1",
    "https://a.example/a b", "https://a.example/\\", "https:///nohost",
])
def test_signature_agent_url_rejects_header_breaking_values(bad):
    with pytest.raises(ValueError):
        Identity.from_test_key(bad)


def test_signature_agent_url_is_read_only():
    ident = Identity.from_test_key(URL)
    with pytest.raises(AttributeError):
        ident.signature_agent_url = "http://evil"  # type: ignore[misc]


def test_user_agent_rejects_control_chars():
    with pytest.raises(ValueError):
        Identity.from_test_key(URL, user_agent="Bot/1\r\nX: y")


# ---- #3 keygen / register never lie or create keys silently ----------------

def _cli(*args):
    return subprocess.run([sys.executable, "-m", "wbauth.cli", *args],
                          capture_output=True, text=True)


def test_keygen_refuses_existing_key(tmp_path):
    p = tmp_path / "k.pem"
    assert _cli("keygen", "--output", str(p)).returncode == 0
    second = _cli("keygen", "--output", str(p))
    assert second.returncode == 2
    assert "already exists" in second.stderr
    assert "Wrote key" not in second.stdout


def test_register_does_not_generate_missing_key(tmp_path):
    p = tmp_path / "typo.pem"
    r = _cli("register", "--identity", str(p), "--client-name", "x",
             "--directory", "https://127.0.0.1:9")
    assert r.returncode == 1
    assert not p.exists()


# ---- #11 keyring rotation persists --------------------------------------

def test_keyring_rotation_survives_restart(tmp_path):
    a = Identity.load_keyring(tmp_path, signature_agent_url=URL)
    b = a.rotate_keyring(tmp_path)
    c = Identity.load_keyring(tmp_path, signature_agent_url=URL)
    assert c.kid == b.kid != a.kid
    assert [k["kid"] for k in c.export_jwks()["keys"]] == [b.kid, a.kid]


def test_rotate_default_path_does_not_collide(tmp_path, monkeypatch):
    import wbauth.identity as idm
    monkeypatch.setattr(idm, "DEFAULT_KEY_PATH", tmp_path / "key.pem")
    a = Identity.load_or_generate(tmp_path / "key.pem", signature_agent_url=URL)
    b = a.rotate()
    assert b.kid != a.kid


def test_encrypted_key_roundtrip(tmp_path, monkeypatch):
    p = tmp_path / "enc.pem"
    a = Identity.generate(p, signature_agent_url=URL, password=b"s3cret")
    assert b"ENCRYPTED" in p.read_bytes()
    with pytest.raises(TypeError):
        Identity.load(p, signature_agent_url=URL)
    monkeypatch.setenv("WBAUTH_KEY_PASSWORD", "s3cret")
    assert Identity.load(p, signature_agent_url=URL).kid == a.kid


def test_external_signer_backend():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    class FakeKms:
        def __init__(self):
            self._k = Ed25519PrivateKey.generate()
            self.calls = 0

        def sign(self, data):
            self.calls += 1
            return self._k.sign(data)

        def public_key(self):
            return self._k.public_key()

    kms = FakeKms()
    ident = Identity.from_signer(kms, URL)
    req = NormalizedRequest("GET", "https://site.example/", {})
    sign(req, ident)
    assert kms.calls == 1 and ident.kid in req.headers["Signature-Input"]


# ---- #8 adapters don't sign other hosts / plain http ----------------------

def test_sign_decider():
    d = make_sign_decider(hosts=["*.example.com"])
    assert d("https://a.example.com/x")
    assert not d("https://tracker.example.net/")
    assert not d("http://a.example.com/")  # plain http unsigned by default
    assert make_sign_decider(allow_insecure=True)("http://a.example.com/")


def test_redirect_to_foreign_host_is_not_signed():
    seen = {}

    def handler(request):
        seen[request.url.host] = "signature" in request.headers
        if request.url.host == "site.example":
            return httpx.Response(302, headers={"location": "https://cdn.other/x"})
        return httpx.Response(200)

    ident = Identity.from_test_key(URL)
    with signed_client(ident, transport=httpx.MockTransport(handler),
                       hosts=["site.example"], follow_redirects=True) as c:
        c.get("https://site.example/")
    assert seen == {"site.example": True, "cdn.other": False}


def test_stale_content_digest_is_replaced():
    h = {"Content-Digest": "sha-256=:AAAA:"}
    ensure_content_digest("POST", h, b"new body")
    assert h["Content-Digest"] != "sha-256=:AAAA:"


# ---- #9 SSRF ------------------------------------------------------------

@pytest.mark.parametrize("host", ["2130706433", "0x7f000001", "127.1", "0177.0.0.1",
                                  "[::ffff:127.0.0.1]", "169.254.169.254"])
def test_private_literals(host):
    assert insp._is_private_host(host)


def test_allow_private_false_refuses_loopback_origin():
    async def go():
        transport = httpx.MockTransport(lambda r: httpx.Response(200, text="User-agent: *\n"))
        async with httpx.AsyncClient(transport=transport) as c:
            return await insp.inspect("https://127.0.0.1/x", client=c, allow_private=False)

    pol = asyncio.run(go())
    assert all("private" in str(e) for e in pol.errors.values())
    assert pol.verdict == "forbidden"


# ---- #10 single-flight keyed by UA ---------------------------------------

def test_single_flight_does_not_mix_user_agents():
    uas = []

    async def handler(request):
        uas.append(request.headers["user-agent"])
        await asyncio.sleep(0.01)
        return httpx.Response(404)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            await asyncio.gather(
                insp.inspect("https://s.example/", user_agent="A/1", client=c,
                             endpoints=["robots"]),
                insp.inspect("https://s.example/", user_agent="B/1", client=c,
                             endpoints=["robots"]),
            )

    asyncio.run(go())
    assert sorted(uas) == ["A/1", "B/1"]


# ---- #14 parsers ------------------------------------------------------------

def test_restriction_is_segment_aware():
    assert restriction_applies("No AI on /admin", "/admin/x")
    assert not restriction_applies("No AI on /admin", "/administrator")


def test_llms_txt_multiline_quote_and_bullets():
    r = parse_llms_txt("# T\n> line one\n> line two\n\n## S\n* [W](https://w.org/A_(b)): n\n")
    assert r.description == "line one line two"
    assert r.sections[0].links[0].url == "https://w.org/A_(b)"


def test_signing_directory_ct_case_insensitive():
    r = parse_signing_directory('{"keys":[{"kty":"OKP"}]}',
                                "Application/HTTP-Message-Signatures-Directory+JSON; charset=utf-8")
    assert r.content_type_correct


def test_robots_truncated_at_line_boundary():
    async def go():
        body = ("User-agent: *\nDisallow: /private\n" + "#" * 600_000 + "\nDisallow: /x").encode()
        transport = httpx.MockTransport(lambda r: httpx.Response(200, content=body))
        async with httpx.AsyncClient(transport=transport) as c:
            return await insp._fetch_one(c, "robots", "https://s.example/robots.txt", "UA")

    resp = asyncio.run(go())
    assert resp.content.endswith(b"\n")


def test_product_token_and_content_signals():
    assert product_token("ExampleBot/1.0 (+https://x)") == "ExampleBot"
    txt = ("User-agent: *\nContent-Signal: search=yes, ai-train=no\nAllow: /\n\n"
           "User-agent: ExampleBot\nContent-Signal: ai-train=yes\n")
    assert parse_content_signals(txt, "ExampleBot/1.0") == {"search": "yes", "ai-train": "yes"}
    r = parse_robots(txt, "text/plain", "https://s.example/", "Other/1")
    assert r.content_signals == {"search": "yes", "ai-train": "no"}


# ---- #15 cache ----------------------------------------------------------------

def test_s_maxage_and_age():
    assert _parse_cache_control("public, s-maxage=50") == (True, 50)
    c = PolicyCache()
    c.set("h", "robots", "v", cache_control="max-age=100", age="90")
    assert 0 < c.get("h", "robots").ttl <= 10


def test_network_failures_are_negatively_cached():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ConnectError("down", request=request)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            for _ in range(3):
                await insp.inspect("https://down.example/", client=c)

    asyncio.run(go())
    assert len(calls) == 4  # one per endpoint, not 12


def test_save_cache_keeps_validators(tmp_path):
    insp._CACHE.set("s.example", "llms_txt", parse_llms_txt("# t"), etag='"e"',
                    raw="# t", cache_control="no-cache")
    p = tmp_path / "c.json"
    insp.save_cache(p)
    insp._reset_cache_for_tests()
    insp.load_cache(p)
    assert insp._CACHE.get_stale("s.example", "llms_txt").etag == '"e"'


# ---- #16/#17 serialization & CLI -----------------------------------------------

def test_to_dict_omits_raw_by_default():
    async def go():
        t = httpx.MockTransport(lambda r: httpx.Response(200, text="User-agent: *\nAllow: /\n"))
        async with httpx.AsyncClient(transport=t) as c:
            return await insp.inspect("https://s.example/", client=c, endpoints=["robots"])

    pol = asyncio.run(go())
    d = pol.to_dict()
    assert "raw" not in d["robots"] and pol.to_dict(include_raw=True)["robots"]["raw"]
    json.dumps(d)


# ---- #22 endpoints / stop_on_forbidden / inspect_sync ----------------------------

def test_stop_on_forbidden_skips_other_endpoints():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /\n")

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await insp.inspect("https://s.example/x", client=c, stop_on_forbidden=True)

    pol = asyncio.run(go())
    assert pol.verdict == "forbidden" and paths == ["/robots.txt"]


def test_inspect_sync_rejects_running_loop():
    async def go():
        insp.inspect_sync("https://s.example/")

    with pytest.raises(RuntimeError):
        asyncio.run(go())


# ---- #23 verifier --------------------------------------------------------------

def _signed(method="GET", url="https://site.example/a", body=None):
    ident = Identity.from_test_key(URL)
    req = NormalizedRequest(method, url, {}, body)
    ensure_content_digest(method, req.headers, body)
    sign(req, ident)
    return ident, req


def _verifier(ident, **kw):
    jwk = ident.export_jwks()["keys"][0]

    async def resolve(kid, _sa):
        return jwk if kid == jwk["kid"] else None

    return Verifier(key_resolver=resolve, **kw)


def test_verifier_accepts_and_rejects():
    ident, req = _signed("POST", body=b"{}")
    v = _verifier(ident)
    agent = asyncio.run(v.verify("POST", req.url, req.headers, req.body))
    assert agent.kid == ident.kid and agent.signature_agent_url == URL
    with pytest.raises(VerificationError, match="replayed"):
        asyncio.run(v.verify("POST", req.url, req.headers, req.body))
    with pytest.raises(VerificationError, match="Content-Digest"):
        asyncio.run(_verifier(ident).verify("POST", req.url, req.headers, b"[]"))
    with pytest.raises(VerificationError, match="expired"):
        asyncio.run(_verifier(ident).verify("POST", req.url, req.headers, req.body,
                                            now=10**10))


def test_verifier_resolves_directory():
    ident, req = _signed()

    def handler(request):
        assert request.url.path == "/.well-known/http-message-signatures-directory"
        return httpx.Response(200, json=ident.export_jwks())

    from wbauth.verifier import JwksCache

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            v = Verifier(jwks_cache=JwksCache(client=c, allow_private=True))
            return await v.verify("GET", req.url, req.headers)

    assert asyncio.run(go()).kid == ident.kid


def test_asgi_middleware():
    ident, req = _signed()
    v = _verifier(ident)
    from wbauth.verifier import WebBotAuthMiddleware

    async def app(scope, receive, send):
        agent = scope["state"]["web_bot_auth"]
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": (agent.kid if agent else "-").encode()})

    async def go(headers):
        mw = WebBotAuthMiddleware(app, verifier=v, required=True)
        sent = []
        scope = {"type": "http", "method": "GET", "path": "/a", "raw_path": b"/a",
                 "scheme": "https", "query_string": b"",
                 "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]}

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(m):
            sent.append(m)

        await mw(scope, receive, send)
        return sent

    ok = asyncio.run(go({**req.headers, "host": "site.example"}))
    assert ok[0]["status"] == 200 and ok[1]["body"] == ident.kid.encode()
    assert asyncio.run(go({"host": "site.example"}))[0]["status"] == 401


# ---- #25 PolicyGuard ----------------------------------------------------------

def test_policy_guard_blocks_and_paces():
    from wbauth.adapters import signed_async_client
    from wbauth.policy import PolicyForbiddenError, PolicyGuard

    robots = "User-agent: *\nCrawl-delay: 0.2\nDisallow: /private\n"

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        if request.url.path in ("/ai.txt", "/llms.txt",
                                "/.well-known/http-message-signatures-directory"):
            return httpx.Response(404)
        return httpx.Response(200)

    import time

    async def go():
        t = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=t) as ic:
            guard = PolicyGuard(inspect_kwargs={"client": ic})
            ident = Identity.from_test_key(URL)
            async with signed_async_client(ident, transport=t, policy_guard=guard) as c:
                t0 = time.monotonic()
                await c.get("https://s.example/a")
                await c.get("https://s.example/b")
                elapsed = time.monotonic() - t0
                with pytest.raises(PolicyForbiddenError):
                    await c.get("https://s.example/private/x")
                return elapsed

    assert asyncio.run(go()) >= 0.18
